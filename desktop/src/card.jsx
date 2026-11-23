import { useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { A2uiSurface } from '@a2ui/react'
import { MessageProcessor } from '@a2ui/web_core/v1_0'
import { catalogWithOpenUrlOff } from './catalog.js'
import { messagesFromPayload, newMessagesSince, parseResult, surfaceIdFrom } from './ids.js'
import { restJson } from './rest.js'

const POLL_MS = 4000

// A click is a request, never approval. The host (not the model) tells the
// user what is still waiting, using the plugin's audit log.
const GATE_COPY = {
  pending_confirmation: 'Waiting for your yes in chat. Clicking is not approval.',
  approved: 'Approved by your reply in chat.',
  denied: 'Cancelled. You said no.',
  expired: 'Request expired. Click again to retry.',
  superseded: 'Replaced by a newer click.',
  completed: 'Done. Logged in the audit log.',
  failed: 'Failed. Logged in the audit log.',
  cancelled: 'Cancelled. Logged in the audit log.',
  executing: 'Running the approved call…',
  unknown: 'Outcome unknown. Check the target system before trying again.',
  rejected: 'Not accepted, so nothing will run.',
}

// Declared actions: the confirm panel is drawn from the plugin's own record of
// the bound call (title, tool, risk), never from model-authored card text.
function shortCode(actionId) {
  return typeof actionId === 'string' ? actionId.replace('act-', '').slice(0, 6) : ''
}

function boundCopy(gate) {
  const b = gate.binding || {}
  const code = shortCode(gate.actionId)
  const reply = b.code_required ? `yes ${code}` : 'yes'
  switch (gate.status) {
    case 'pending_confirmation':
      return (
        (gate.needsCode ? `This one needs the code. ` : '') +
        `Reply "${reply}" in chat to approve, or "no". Clicking is not approval.`
      )
    case 'approved':
      return gate.decisionBy === 'policy:auto_approve'
        ? 'Approved by your auto-approve rule. Only this exact call may run, once.'
        : 'Approved by your reply in chat. Only this exact call may run, once.'
    case 'rejected':
      return `Not accepted: ${gate.rejected || 'invalid request'}. Nothing will run.`
    case 'failed':
      return `Failed${gate.errorType ? ` (${gate.errorType})` : ''}. Logged in the audit log.`
    default:
      return GATE_COPY[gate.status] || null
  }
}

function gateFromEntry(entry, prev) {
  return {
    actionId: entry.action_id || (prev && prev.actionId),
    status: entry.status,
    binding: entry.binding || (prev && prev.binding) || null,
    rejected: entry.rejected || null,
    errorType: entry.error_type || null,
    needsCode: Boolean(entry.needs_code),
    decisionBy: entry.decision_by || null,
  }
}

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
  const [gate, setGate] = useState(null)
  const gateIdRef = useRef(null)

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
        }).then((res) => {
          // Only the server decides whether a click needs confirmation, and the
          // card never marks anything approved.
          if (
            res &&
            res.ok !== false &&
            typeof res.action_id === 'string' &&
            (res.requires_confirmation || res.binding)
          ) {
            gateIdRef.current = res.action_id
            const status =
              typeof res.status === 'string' && GATE_COPY[res.status] ? res.status : 'pending_confirmation'
            setGate(gateFromEntry({ ...res, status }, null))
          }
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
      const gateId = gateIdRef.current
      if (!gateId) return
      try {
        const audit = await restJson(
          ctx,
          `/audit?surface_id=${encodeURIComponent(surfaceId)}&limit=20`,
        )
        const entry =
          audit && Array.isArray(audit.actions)
            ? audit.actions.find((a) => a && a.action_id === gateId)
            : null
        if (!cancelled && entry && typeof entry.status === 'string') {
          setGate((prev) => gateFromEntry(entry, prev))
        }
      } catch {
        // keep the last known status
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
    children: [
      gate && gate.binding
        ? jsxs('div', {
            'data-uirizz-gate': gate.status,
            'data-uirizz-bound': gate.binding.action || 'true',
            role: 'status',
            'aria-live': 'polite',
            style: {
              fontSize: '12px',
              padding: '8px 10px',
              marginBottom: '6px',
              borderRadius: '6px',
              border: '1px solid var(--ui-border, var(--border))',
              color: 'var(--ui-foreground, var(--foreground))',
            },
            children: [
              jsx('div', {
                'data-uirizz-confirm-title': '',
                style: { fontWeight: 600, fontSize: '13px' },
                children: gate.binding.title,
              }),
              jsx('div', {
                'data-uirizz-confirm-meta': '',
                style: { opacity: 0.75, margin: '2px 0 4px' },
                children: `${gate.binding.tool} · ${gate.binding.risk} risk · uirizz confirm`,
              }),
              jsx('div', { children: boundCopy(gate) }),
            ],
          })
        : gate && GATE_COPY[gate.status]
          ? jsx('div', {
              'data-uirizz-gate': gate.status,
              role: 'status',
              style: {
                fontSize: '12px',
                padding: '6px 8px',
                marginBottom: '6px',
                borderRadius: '6px',
                border: '1px solid var(--ui-border, var(--border))',
                color: 'var(--ui-foreground, var(--foreground))',
              },
              children: GATE_COPY[gate.status],
            })
          : null,
      jsx(A2uiSurface, { surface }),
    ],
  })
}
