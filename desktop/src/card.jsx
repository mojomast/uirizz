import { useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { A2uiSurface } from '@a2ui/react'
import { MessageProcessor } from '@a2ui/web_core/v1_0'
import { catalogWithOpenUrlOff } from './catalog.js'
import { messagesFromPayload, newMessagesSince, parseResult, surfaceIdFrom } from './ids.js'
import { restJson } from './rest.js'
import { createRefresher } from './live.js'

// Highest revision wins: surfaceId -> entries for every mounted (non-canvas) card.
const registry = new Map()
const registryListeners = new Set()

function registryMax(surfaceId) {
  const entries = registry.get(surfaceId)
  if (!entries) return 0
  let max = 0
  for (const e of entries) if (e.revision > max) max = e.revision
  return max
}

function registryAdd(surfaceId, entry) {
  if (!registry.has(surfaceId)) registry.set(surfaceId, new Set())
  registry.get(surfaceId).add(entry)
  registryListeners.forEach((fn) => fn())
}

function registryRemove(surfaceId, entry) {
  const entries = registry.get(surfaceId)
  if (!entries) return
  entries.delete(entry)
  if (!entries.size) registry.delete(surfaceId)
  registryListeners.forEach((fn) => fn())
}

function revisionOf(parsed) {
  const n = parsed && Number(parsed.revision)
  return Number.isFinite(n) && n > 0 ? n : 1
}

function firstLine(text, max) {
  if (typeof text !== 'string') return ''
  const line = text.split('\n').find((l) => l.trim()) || ''
  return line.trim().slice(0, max)
}

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

export function SurfaceCard({ file, args, result, sessionId, fallback, ctx, host, variant }) {
  const surfaceId = lookUpSurfaceId(args, result)
  const parsedResult = parseResult(result)
  const canvas = variant === 'canvas'
  const myRevision = revisionOf(parsedResult)
  const hostRef = useRef(host)
  hostRef.current = host
  const pokeRef = useRef(null)
  const [, bump] = useState(0)
  const [payload, setPayload] = useState(null)
  const [surface, setSurface] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const processed = useRef(0)
  const processorRef = useRef(null)
  const [gate, setGate] = useState(null)
  const gateIdRef = useRef(null)

  useEffect(() => {
    if (!surfaceId || canvas) return undefined
    const entry = { revision: myRevision }
    const listener = () => bump((n) => n + 1)
    registryListeners.add(listener)
    registryAdd(surfaceId, entry)
    return () => {
      registryListeners.delete(listener)
      registryRemove(surfaceId, entry)
    }
  }, [surfaceId, canvas, myRevision])

  const supersededBy = surfaceId && !canvas ? registryMax(surfaceId) : 0
  const superseded = supersededBy > myRevision

  const processor = useMemo(() => {
    if (!surfaceId) return null
    const next = new MessageProcessor(
      [catalogWithOpenUrlOff()],
      (action) => {
        if (!ctx || typeof ctx.rest !== 'function') return
        const userMessage = typeof action.userMessage === 'string' ? action.userMessage : ''
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
          } else if (
            res &&
            res.ok !== false &&
            res.status === 'recorded' &&
            !res.requires_confirmation &&
            !res.binding &&
            userMessage.trim()
          ) {
            // A plain click that carries a userMessage starts a chat turn. Gated and
            // declared actions never do; they wait for the user's reply in chat.
            const h = hostRef.current
            if (h && h.composer && typeof h.composer.submit === 'function') {
              try {
                h.composer.submit(sessionId, '[card] ' + userMessage.slice(0, 500))
              } catch {
                // fail closed
              }
            }
          }
          if (pokeRef.current) pokeRef.current()
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
    if (!surfaceId || !ctx || typeof ctx.rest !== 'function' || superseded) return undefined
    let cancelled = false
    let appliedRevision = 0

    const apply = (body) => {
      if (cancelled || !body) return false
      setPayload(body)
      if (body.ok === false || body.code === 'not_found') {
        setLoadError(body.code || 'not_found')
        return false
      }
      setLoadError(null)
      const rev = Number(body.revision)
      if (Number.isFinite(rev) && rev > appliedRevision) appliedRevision = rev
      const msgs = messagesFromPayload(body)
      const incoming = newMessagesSince(msgs, processed.current)
      if (!incoming.length || !processorRef.current) return false
      try {
        processorRef.current.processMessages(incoming)
        processed.current += incoming.length
      } catch {
        setLoadError('render_error')
      }
      return true
    }

    const refresh = async () => {
      let changed = false
      try {
        const body = await restJson(ctx, `/surfaces/${encodeURIComponent(surfaceId)}`)
        changed = apply(body)
      } catch {
        if (!cancelled) setLoadError('rest_error')
      }
      const gateId = gateIdRef.current
      if (!gateId) return changed
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
          if (entry.status !== lastGateStatus.current) changed = true
          lastGateStatus.current = entry.status
          setGate((prev) => gateFromEntry(entry, prev))
        }
      } catch {
        // keep the last known status
      }
      return changed
    }

    const lastGateStatus = { current: null }
    const setTimer = (fn, ms) =>
      typeof ctx.setTimeout === 'function' ? ctx.setTimeout(fn, ms) : setTimeout(fn, ms)
    const clearTimer = (h) =>
      typeof ctx.clearTimeout === 'function' ? ctx.clearTimeout(h) : clearTimeout(h)
    const hasDoc = typeof document !== 'undefined'
    const refresher = createRefresher({
      refresh,
      setTimer,
      clearTimer,
      isHidden: () => hasDoc && document.hidden === true,
      onVisibility: (cb) => {
        if (!hasDoc) return undefined
        document.addEventListener('visibilitychange', cb)
        return () => document.removeEventListener('visibilitychange', cb)
      },
    })
    pokeRef.current = () => refresher.poke()
    refresher.start()

    let stopSocket = () => {}
    if (typeof ctx.socket === 'function') {
      try {
        const dispose = ctx.socket(
          '/surfaces/ws?surface_id=' + encodeURIComponent(surfaceId),
          (raw) => {
            if (cancelled) return
            let msg = raw
            if (typeof raw === 'string') {
              try {
                msg = JSON.parse(raw)
              } catch {
                return
              }
            }
            if (!msg || typeof msg !== 'object') return
            refresher.setSocketConnected(true)
            if (msg.type !== 'revision') return
            if (msg.surface_id && msg.surface_id !== surfaceId) return
            const rev = Number(msg.revision)
            if (Number.isFinite(rev) && rev > appliedRevision) refresher.refreshNow()
          },
        )
        if (typeof dispose === 'function') stopSocket = dispose
      } catch {
        // polling still works
      }
    }

    return () => {
      cancelled = true
      pokeRef.current = null
      refresher.stop()
      stopSocket()
    }
  }, [surfaceId, ctx, superseded])

  // Never open file.path. The media file is only a transcript hook.
  void file

  if (!surfaceId) return fallback || null

  if (superseded) {
    return jsx('div', {
      className: 'uirizz-card',
      'data-uirizz': 'superseded',
      style: { fontSize: '12px', opacity: 0.7 },
      children: `Updated below (revision ${supersededBy})`,
    })
  }

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

  const fallbackText =
    (payload && typeof payload.fallback_text === 'string' && payload.fallback_text) ||
    (parsedResult && typeof parsedResult.fallback_text === 'string' && parsedResult.fallback_text) ||
    ''
  const canOpenCanvas = !canvas && host && typeof host.openWorkspace === 'function'
  const openCanvas = () => {
    try {
      host.openWorkspace('uirizz-' + surfaceId, {
        title: firstLine(fallbackText, 60) || 'uirizz card',
        render: () =>
          jsx(SurfaceCard, { file, args, result, sessionId, fallback, ctx, host, variant: 'canvas' }),
      })
    } catch {
      // canvas is optional
    }
  }

  return jsxs('div', {
    className: 'uirizz-card',
    'data-uirizz': 'ready',
    'data-variant': canvas ? 'canvas' : undefined,
    'data-surface-id': surfaceId,
    'data-revision': payload && payload.revision != null ? String(payload.revision) : undefined,
    style: {
      color: 'var(--ui-foreground, var(--foreground))',
      border: '1px solid var(--ui-border, var(--border))',
      borderRadius: '8px',
      padding: '8px',
      ...(canvas ? { width: '100%', boxSizing: 'border-box' } : { maxHeight: '480px', overflow: 'auto' }),
    },
    children: [
      canOpenCanvas
        ? jsx('div', {
            'data-uirizz-header': '',
            style: { display: 'flex', justifyContent: 'flex-end', marginBottom: '4px' },
            children: jsx('button', {
              type: 'button',
              'data-uirizz-open-canvas': '',
              'aria-label': 'Open in canvas',
              title: 'Open in canvas',
              onClick: openCanvas,
              style: {
                fontSize: '11px',
                padding: '2px 8px',
                borderRadius: '6px',
                border: '1px solid var(--ui-border, var(--border))',
                background: 'transparent',
                color: 'inherit',
                cursor: 'pointer',
              },
              children: 'Open in canvas',
            }),
          })
        : null,
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
