import { useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { A2uiSurface } from '@a2ui/react'
import { MessageProcessor } from '@a2ui/web_core/v1_0'
import { catalogWithOpenUrlOff } from './catalog.js'
import { messagesFromPayload, newMessagesSince, parseResult, surfaceIdFrom } from './ids.js'
import { restJson } from './rest.js'

const POLL_MS = 4000

function lookUpSurfaceId(args, result) {
  return surfaceIdFrom(args, result)
}

export function SurfaceCard({ file, args, result, sessionId, fallback, ctx }) {
  const surfaceId = lookUpSurfaceId(args, result)
  const parsedResult = parseResult(result)
  const [payload, setPayload] = useState(null)
  const [surface, setSurface] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const processed = useRef(0)
  const processorRef = useRef(null)

  const processor = useMemo(() => {
    if (!surfaceId) return null
    const next = new MessageProcessor(
      [catalogWithOpenUrlOff()],
      (action) => {
        if (!ctx || typeof ctx.rest !== 'function') return
        void restJson(ctx, '/actions', {
          method: 'POST',
          body: {
            surface_id: action.surfaceId || surfaceId,
            session_id: sessionId,
            event: action.name,
            context: action.context || {},
            source_component_id: action.sourceComponentId,
            timestamp: action.timestamp,
          },
        })
      },
      { version: '1.0', reportErrorsOnly: true },
    )
    return next
  }, [surfaceId, ctx, sessionId])

  useEffect(() => {
    processorRef.current = processor
    processed.current = 0
    setSurface(null)
    return () => {
      try {
        processor && processor.dispose && processor.dispose()
      } catch {
        // ignore
      }
    }
  }, [processor])

  useEffect(() => {
    if (!processor) return undefined
    const sync = () => {
      const id = surfaceId
      const model = id ? processor.getSurface(id) : undefined
      const first = model || (processor.getSurfaces && [...processor.getSurfaces().values()][0])
      setSurface(first || null)
    }
    const created = processor.onSurfaceCreated ? processor.onSurfaceCreated(sync) : { unsubscribe() {} }
    const deleted = processor.onSurfaceDeleted
      ? processor.onSurfaceDeleted(() => {
          sync()
        })
      : { unsubscribe() {} }
    sync()
    return () => {
      created.unsubscribe && created.unsubscribe()
      deleted.unsubscribe && deleted.unsubscribe()
    }
  }, [processor, surfaceId])

  useEffect(() => {
    if (!surfaceId || !ctx || typeof ctx.rest !== 'function') return undefined
    let cancelled = false

    const apply = (body) => {
      if (cancelled || !body) return
      setPayload(body)
      if (body.ok === false || body.code === 'not_found') {
        setLoadError(body.code || 'not_found')
        return
      }
      setLoadError(null)
      const msgs = messagesFromPayload(body)
      const incoming = newMessagesSince(msgs, processed.current)
      if (!incoming.length || !processorRef.current) return
      try {
        processorRef.current.processMessages(incoming)
        processed.current += incoming.length
      } catch {
        setLoadError('render_error')
      }
    }

    const refresh = async () => {
      try {
        const body = await restJson(ctx, `/surfaces/${encodeURIComponent(surfaceId)}`)
        apply(body)
      } catch {
        if (!cancelled) setLoadError('rest_error')
      }
    }

    void refresh()

    let stopPoll = () => {}
    if (typeof ctx.setInterval === 'function') {
      const handle = ctx.setInterval(() => {
        void refresh()
      }, POLL_MS)
      stopPoll = () => {
        if (typeof ctx.clearInterval === 'function') ctx.clearInterval(handle)
      }
    } else if (typeof ctx.setTimeout === 'function') {
      let timer
      const loop = () => {
        timer = ctx.setTimeout(() => {
          void refresh().finally(() => {
            if (!cancelled) loop()
          })
        }, POLL_MS)
      }
      loop()
      stopPoll = () => {
        if (typeof ctx.clearTimeout === 'function') ctx.clearTimeout(timer)
      }
    }

    let stopSocket = () => {}
    if (ctx.socket && typeof ctx.socket.on === 'function') {
      const off = ctx.socket.on('surfaces', () => {
        void refresh()
      })
      stopSocket = () => {
        if (typeof off === 'function') off()
        else if (ctx.socket && typeof ctx.socket.off === 'function') ctx.socket.off('surfaces')
      }
    }

    return () => {
      cancelled = true
      stopPoll()
      stopSocket()
    }
  }, [surfaceId, ctx])

  // Never open file.path. The media file is only a transcript hook.
  void file

  if (!surfaceId) return fallback || null

  if (loadError && !surface) {
    const text =
      (payload && typeof payload.fallback_text === 'string' && payload.fallback_text) ||
      (parsedResult && typeof parsedResult.fallback_text === 'string' && parsedResult.fallback_text) ||
      null
    if (text) {
      return jsx('div', {
        className: 'uirizz-card',
        'data-uirizz': 'fallback',
        children: text,
      })
    }
    return fallback || null
  }

  if (!surface) {
    return jsx('div', {
      className: 'uirizz-card',
      'data-uirizz': 'loading',
      children: (parsedResult && parsedResult.fallback_text) || 'Loading surface…',
    })
  }

  return jsxs('div', {
    className: 'uirizz-card',
    'data-uirizz': 'ready',
    'data-surface-id': surfaceId,
    'data-revision': payload && payload.revision != null ? String(payload.revision) : undefined,
    style: {
      color: 'var(--ui-foreground, var(--foreground))',
      border: '1px solid var(--ui-border, var(--border))',
      borderRadius: '8px',
      padding: '8px',
    },
    children: [jsx(A2uiSurface, { surface })],
  })
}
