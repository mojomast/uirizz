import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsx } from 'react/jsx-runtime'
import { SurfaceCard } from './card.jsx'

vi.mock('./uirizz-catalog.js', () => ({ rendererCatalogs: () => [] }))

vi.mock('@a2ui/react', () => ({
  A2uiSurface: (props) =>
    jsx('div', { 'data-testid': 'a2ui-surface', 'data-id': props.surface && props.surface.id }),
}))

function fakeProcessor(surfaceId = 'demo') {
  const surface = { id: surfaceId }
  const listeners = []
  return {
    getSurface: (id) => (id === surfaceId ? surface : undefined),
    getSurfaces: () => new Map([[surfaceId, surface]]),
    onSurfaceCreated: (fn) => {
      listeners.push(fn)
      return { unsubscribe() {} }
    },
    onSurfaceDeleted: () => ({ unsubscribe() {} }),
    processMessages: vi.fn(),
    dispose: vi.fn(),
  }
}

vi.mock('@a2ui/web_core/v1_0', () => {
  const instances = []
  class MessageProcessor {
    constructor(catalogs, actionHandler) {
      this.actionHandler = actionHandler
      const fake = fakeProcessor('demo')
      Object.assign(this, fake)
      this.processMessages = vi.fn((msgs) => {
        fake.processMessages(msgs)
        for (const fn of []) {
          fn(this.getSurface('demo'))
        }
      })
      instances.push(this)
    }
  }
  MessageProcessor._instances = instances
  return {
    MessageProcessor,
    basicCatalog: { functions: { get: () => null }, derive: () => ({}) },
    createFunctionImplementation: () => ({}),
  }
})

import { MessageProcessor } from '@a2ui/web_core/v1_0'

afterEach(() => {
  cleanup()
  MessageProcessor._instances.length = 0
})

// Fake timers: `intervals[0]()` fires the most recently scheduled poll.
function fakeTimers() {
  const timers = new Map()
  let n = 0
  const fire = () => {
    const last = [...timers].pop()
    if (!last) return undefined
    timers.delete(last[0])
    return last[1]()
  }
  return {
    timers,
    intervals: { 0: fire },
    setTimeout: (fn) => {
      n += 1
      timers.set(n, fn)
      return n
    },
    clearTimeout: (id) => timers.delete(id),
  }
}

function makeCtx(payloads) {
  const calls = []
  let i = 0
  const ft = fakeTimers()
  const intervals = ft.intervals
  const ctx = {
    rest: vi.fn(async (path, init = {}) => {
      calls.push({ path, init })
      if (path.startsWith('/surfaces/')) {
        const body = payloads[Math.min(i, payloads.length - 1)]
        i += 1
        return body
      }
      return { ok: true }
    }),
    setTimeout: ft.setTimeout,
    clearTimeout: ft.clearTimeout,
  }
  return { ctx, calls, intervals }
}

describe('SurfaceCard', () => {
  it('returns the host fallback when no surface_id is present', () => {
    const { ctx } = makeCtx([])
    const { container } = render(
      jsx(SurfaceCard, {
        file: { path: '/tmp/x.md', resolveUrl: () => Promise.resolve('data:') },
        args: {},
        result: { ok: true },
        sessionId: 's',
        fallback: jsx('div', { 'data-testid': 'host-fallback', children: 'fb' }),
        ctx,
      }),
    )
    expect(container.querySelector('[data-testid="host-fallback"]')).toBeTruthy()
    expect(ctx.rest).not.toHaveBeenCalled()
  })

  it('loads a surface over ctx.rest and refreshes in place when the revision changes', async () => {
    const first = {
      ok: true,
      surface_id: 'demo',
      revision: 1,
      fallback_text: 'Hello',
      messages: [{ version: '1.0', createSurface: { surfaceId: 'demo' } }],
    }
    const second = {
      ok: true,
      surface_id: 'demo',
      revision: 2,
      fallback_text: 'Hello',
      messages: [
        { version: '1.0', createSurface: { surfaceId: 'demo' } },
        { version: '1.0', updateDataModel: { surfaceId: 'demo', path: '/', value: { n: 2 } } },
      ],
    }
    const { ctx, intervals } = makeCtx([first, second])
    render(
      jsx(SurfaceCard, {
        file: { path: '/never-open', resolveUrl: vi.fn() },
        args: { surface_id: 'demo', op: 'present' },
        result: { ok: true, surface_id: 'demo', revision: 1, fallback_text: 'Hello' },
        sessionId: 'sess-1',
        fallback: jsx('div', { 'data-testid': 'host-fallback' }),
        ctx,
      }),
    )
    await waitFor(() => expect(ctx.rest).toHaveBeenCalled())
    expect(ctx.rest.mock.calls[0][0]).toBe('/surfaces/demo')
    const proc = MessageProcessor._instances[0]
    await waitFor(() => expect(proc.processMessages).toHaveBeenCalled())
    expect(proc.processMessages.mock.calls[0][0]).toHaveLength(1)

    await act(async () => {
      intervals[0]()
    })
    await waitFor(() => expect(proc.processMessages.mock.calls.length).toBeGreaterThanOrEqual(2))
    const secondBatch = proc.processMessages.mock.calls[1][0]
    expect(secondBatch).toHaveLength(1)
    expect(secondBatch[0].updateDataModel).toBeTruthy()
    expect(ctx.rest.mock.calls.every((c) => !String(c[0]).startsWith('http'))).toBe(true)
  })

  it('posts structured actions through ctx.rest and does not attach authorization headers', async () => {
    const { ctx } = makeCtx([
      {
        ok: true,
        surface_id: 'demo',
        revision: 1,
        messages: [{ version: '1.0', createSurface: { surfaceId: 'demo' } }],
      },
    ])
    render(
      jsx(SurfaceCard, {
        file: { path: '/never-open' },
        args: { surface_id: 'demo' },
        result: { surface_id: 'demo' },
        sessionId: 'sess-1',
        fallback: null,
        ctx,
      }),
    )
    await waitFor(() => expect(MessageProcessor._instances[0]).toBeTruthy())
    const proc = MessageProcessor._instances[0]
    await act(async () => {
      await proc.actionHandler({
        name: 'submit',
        surfaceId: 'demo',
        sourceComponentId: 'btn',
        timestamp: '2026-11-22T14:00:00.000Z',
        context: { name: 'Ada' },
      })
    })
    const post = ctx.rest.mock.calls.find((c) => c[0] === '/actions')
    expect(post).toBeTruthy()
    expect(post[1].method).toBe('POST')
    // ctx.rest serialises the body itself: it must be an object, not a JSON string.
    expect(typeof post[1].body).toBe('object')
    const body = post[1].body
    expect(body.event).toBe('submit')
    expect(body.session_id).toBe('sess-1')
    expect(body.surface_id).toBe('demo')
    expect(body.context).toEqual({ name: 'Ada' })
    expect(JSON.stringify(post[1].headers || {}).toLowerCase()).not.toContain('authorization')
  })

  function gateCtx(auditStatuses, actionResponse) {
    const calls = []
    const ft = fakeTimers()
  const intervals = ft.intervals
    let auditIndex = 0
    const surface = {
      ok: true,
      surface_id: 'demo',
      revision: 1,
      messages: [{ version: '1.0', createSurface: { surfaceId: 'demo' } }],
    }
    const ctx = {
      rest: vi.fn(async (path, init = {}) => {
        calls.push({ path, init })
        if (path.startsWith('/surfaces/')) return surface
        if (path === '/actions') return actionResponse
        if (path.startsWith('/audit')) {
          const status = auditStatuses[Math.min(auditIndex, auditStatuses.length - 1)]
          auditIndex += 1
          return { ok: true, actions: [{ action_id: 'act-1', status }] }
        }
        return { ok: true }
      }),
      setTimeout: ft.setTimeout,
      clearTimeout: ft.clearTimeout,
    }
    return { ctx, calls, intervals }
  }

  async function clickDeploy(ctx) {
    const utils = render(
      jsx(SurfaceCard, {
        file: { path: '/never-open' },
        args: { surface_id: 'demo' },
        result: { surface_id: 'demo' },
        sessionId: 'sess-1',
        fallback: null,
        ctx,
      }),
    )
    await waitFor(() => expect(MessageProcessor._instances[0]).toBeTruthy())
    await act(async () => {
      await MessageProcessor._instances[0].actionHandler({
        name: 'deploy',
        surfaceId: 'demo',
        sourceComponentId: 'btn',
        timestamp: '2026-11-22T14:00:00.000Z',
        context: { side_effect: true },
      })
    })
    return utils
  }

  it('shows a waiting notice after a gated click and never shows approval from the click itself', async () => {
    const { ctx } = gateCtx(['pending_confirmation'], {
      ok: true,
      action_id: 'act-1',
      requires_confirmation: true,
      status: 'pending_confirmation',
      approved: false,
    })
    const { container } = await clickDeploy(ctx)
    await waitFor(() =>
      expect(container.querySelector('[data-uirizz-gate="pending_confirmation"]')).toBeTruthy(),
    )
    const notice = container.querySelector('[data-uirizz-gate]')
    expect(notice.textContent).toContain('Clicking is not approval')
    expect(container.querySelector('[data-uirizz-gate="approved"]')).toBeNull()
  })

  it('follows the server-side status from the audit log and shows no notice for plain clicks', async () => {
    const { ctx, intervals } = gateCtx(['approved'], {
      ok: true,
      action_id: 'act-1',
      requires_confirmation: true,
      status: 'pending_confirmation',
    })
    const { container } = await clickDeploy(ctx)
    await act(async () => {
      intervals[0]()
    })
    await waitFor(() => expect(container.querySelector('[data-uirizz-gate="approved"]')).toBeTruthy())

    MessageProcessor._instances.length = 0
    const plain = gateCtx(['approved'], { ok: true, action_id: 'act-2', requires_confirmation: false })
    const second = await clickDeploy(plain.ctx)
    expect(second.container.querySelectorAll('[data-uirizz-gate]').length).toBe(0)
  })

  const BINDING = {
    action: 'deploy_service',
    title: 'Deploy checkout-api v24 to production',
    tool: 'mcp_github_dispatch_workflow',
    args: { repo: 'acme/checkout-api' },
    risk: 'high',
    auto_approve: false,
    code_required: true,
  }

  function boundCtx(auditEntries, actionResponse) {
    const ft = fakeTimers()
  const intervals = ft.intervals
    let i = 0
    const surface = {
      ok: true,
      surface_id: 'demo',
      revision: 1,
      messages: [{ version: '1.0', createSurface: { surfaceId: 'demo' } }],
    }
    const ctx = {
      rest: vi.fn(async (path) => {
        if (path.startsWith('/surfaces/')) return surface
        if (path === '/actions') return actionResponse
        if (path.startsWith('/audit')) {
          const entry = auditEntries[Math.min(i, auditEntries.length - 1)]
          i += 1
          return { ok: true, actions: [entry] }
        }
        return { ok: true }
      }),
      setTimeout: ft.setTimeout,
      clearTimeout: ft.clearTimeout,
    }
    return { ctx, intervals }
  }

  it('shows the plugin-owned confirm panel for a declared action, with the code for high risk', async () => {
    const { ctx } = boundCtx([{ action_id: 'act-abc123def456', status: 'pending_confirmation', binding: BINDING }], {
      ok: true,
      action_id: 'act-abc123def456',
      requires_confirmation: true,
      status: 'pending_confirmation',
      binding: BINDING,
      approved: false,
    })
    const { container } = await clickDeploy(ctx)
    await waitFor(() => expect(container.querySelector('[data-uirizz-bound]')).toBeTruthy())
    expect(container.querySelector('[data-uirizz-confirm-title]').textContent).toBe(BINDING.title)
    expect(container.querySelector('[data-uirizz-confirm-meta]').textContent).toContain('mcp_github_dispatch_workflow')
    const panel = container.querySelector('[data-uirizz-gate="pending_confirmation"]')
    expect(panel.textContent).toContain('yes abc123')
    expect(panel.textContent).toContain('Clicking is not approval')
  })

  it('follows a bound call through executing to completed from the audit log', async () => {
    const { ctx, intervals } = boundCtx(
      [
        { action_id: 'act-abc123def456', status: 'executing', binding: BINDING },
        { action_id: 'act-abc123def456', status: 'completed', binding: BINDING },
      ],
      { ok: true, action_id: 'act-abc123def456', requires_confirmation: true, status: 'pending_confirmation', binding: BINDING },
    )
    const { container } = await clickDeploy(ctx)
    await act(async () => {
      intervals[0]()
    })
    await waitFor(() => expect(container.querySelector('[data-uirizz-gate="executing"]')).toBeTruthy())
    await act(async () => {
      intervals[0]()
    })
    await waitFor(() => expect(container.querySelector('[data-uirizz-gate="completed"]')).toBeTruthy())
    expect(container.querySelector('[data-uirizz-confirm-title]').textContent).toBe(BINDING.title)
  })

  it('explains a rejected declared click and never shows it as pending', async () => {
    const { ctx } = boundCtx([{ action_id: 'act-1', status: 'rejected', binding: BINDING, rejected: 'invalid params: env: must be one of' }], {
      ok: true,
      action_id: 'act-1',
      requires_confirmation: false,
      status: 'rejected',
      binding: BINDING,
      rejected: 'invalid params: env: must be one of',
    })
    const { container } = await clickDeploy(ctx)
    await waitFor(() => expect(container.querySelector('[data-uirizz-gate="rejected"]')).toBeTruthy())
    expect(container.textContent).toContain('Nothing will run')
    expect(container.querySelector('[data-uirizz-gate="pending_confirmation"]')).toBeNull()
  })

  const SURFACE = (rev, text = 'Hello there\nsecond line') => ({
    ok: true,
    surface_id: 'demo',
    revision: rev,
    fallback_text: text,
    messages: [{ version: '1.0', createSurface: { surfaceId: 'demo' } }],
  })

  function mountCard(ctx, extra = {}, revision = 1) {
    return render(
      jsx(SurfaceCard, {
        file: { path: '/never-open' },
        args: { surface_id: 'demo' },
        result: { surface_id: 'demo', revision, fallback_text: 'Hello there\nsecond line' },
        sessionId: 'sess-1',
        fallback: null,
        ctx,
        ...extra,
      }),
    )
  }

  it('opens ctx.socket on the surfaces ws path, refreshes on a newer revision, and disposes on unmount', async () => {
    const ft = fakeTimers()
    let onMessage
    const dispose = vi.fn()
    const payloads = [SURFACE(1), SURFACE(2)]
    let i = 0
    const ctx = {
      rest: vi.fn(async (path) => (path.startsWith('/surfaces/') ? payloads[Math.min(i++, 1)] : { ok: true })),
      setTimeout: ft.setTimeout,
      clearTimeout: ft.clearTimeout,
      socket: vi.fn((path, cb) => {
        onMessage = cb
        return dispose
      }),
    }
    const { unmount } = mountCard(ctx)
    await waitFor(() => expect(ctx.socket).toHaveBeenCalled())
    expect(ctx.socket.mock.calls[0][0]).toBe('/surfaces/ws?surface_id=demo')
    await waitFor(() => expect(ctx.rest).toHaveBeenCalledTimes(1))
    // stale and foreign messages do nothing
    await act(async () => {
      onMessage(JSON.stringify({ type: 'revision', surface_id: 'demo', revision: 1 }))
      onMessage({ type: 'revision', surface_id: 'other', revision: 9 })
      onMessage('not json')
    })
    expect(ctx.rest).toHaveBeenCalledTimes(1)
    await act(async () => {
      onMessage(JSON.stringify({ type: 'revision', surface_id: 'demo', revision: 2 }))
    })
    await waitFor(() => expect(ctx.rest).toHaveBeenCalledTimes(2))
    unmount()
    expect(dispose).toHaveBeenCalledTimes(1)
  })

  it('collapses an older mount to a stub and expands it again when the newer one unmounts', async () => {
    const { ctx } = makeCtx([SURFACE(2)])
    const older = mountCard(ctx, {}, 1)
    await waitFor(() => expect(older.container.querySelector('[data-uirizz="ready"]')).toBeTruthy())
    const newer = mountCard(ctx, {}, 2)
    await waitFor(() => {
      const stub = older.container.querySelector('[data-uirizz="superseded"]')
      expect(stub).toBeTruthy()
      expect(stub.textContent).toBe('Updated below (revision 2)')
    })
    await waitFor(() => expect(newer.container.querySelector('[data-uirizz="ready"]')).toBeTruthy())
    expect(newer.container.querySelector('[data-uirizz="superseded"]')).toBeNull()
    newer.unmount()
    await waitFor(() => expect(older.container.querySelector('[data-uirizz="ready"]')).toBeTruthy())
  })

  it('shows Open in canvas only with host.openWorkspace and opens a canvas variant', async () => {
    const { ctx } = makeCtx([SURFACE(1)])
    const none = mountCard(ctx, { host: {} })
    await waitFor(() => expect(none.container.querySelector('[data-uirizz="ready"]')).toBeTruthy())
    expect(none.container.querySelector('[data-uirizz-open-canvas]')).toBeNull()
    none.unmount()

    const host = { openWorkspace: vi.fn(() => () => {}) }
    const { container } = mountCard(ctx, { host })
    await waitFor(() => expect(container.querySelector('[data-uirizz-open-canvas]')).toBeTruthy())
    const btn = container.querySelector('[data-uirizz-open-canvas]')
    expect(btn.getAttribute('aria-label')).toBe('Open in canvas')
    fireEvent.click(btn)
    expect(host.openWorkspace).toHaveBeenCalledTimes(1)
    const [id, opts] = host.openWorkspace.mock.calls[0]
    expect(id).toBe('uirizz-demo')
    expect(opts.title).toBe('Hello there')
    const canvas = render(opts.render())
    await waitFor(() => expect(canvas.container.querySelector('[data-uirizz="ready"]')).toBeTruthy())
    const root = canvas.container.querySelector('[data-uirizz="ready"]')
    expect(root.getAttribute('data-variant')).toBe('canvas')
    expect(root.style.maxHeight).toBe('')
    expect(canvas.container.querySelector('[data-uirizz-open-canvas]')).toBeNull()
    // the in-chat card is not collapsed by its own canvas copy
    expect(container.querySelector('[data-uirizz="ready"]')).toBeTruthy()
  })

  async function click(ctx, host, action) {
    mountCard(ctx, { host })
    await waitFor(() => expect(MessageProcessor._instances[0]).toBeTruthy())
    await act(async () => {
      await MessageProcessor._instances[0].actionHandler({
        name: 'ask',
        surfaceId: 'demo',
        sourceComponentId: 'btn',
        timestamp: 't',
        context: {},
        ...action,
      })
    })
  }

  it('submits a [card] chat message for a recorded plain click that carries userMessage', async () => {
    const { ctx } = gateCtx(['approved'], { ok: true, action_id: 'act-1', status: 'recorded' })
    const host = { composer: { submit: vi.fn(() => true) } }
    await click(ctx, host, { userMessage: 'x'.repeat(600) })
    expect(host.composer.submit).toHaveBeenCalledTimes(1)
    expect(host.composer.submit).toHaveBeenCalledWith('sess-1', '[card] ' + 'x'.repeat(500))
  })

  it('never submits for gated, declared, message-less or non-recorded clicks', async () => {
    const cases = [
      [{ ok: true, action_id: 'act-1', status: 'pending_confirmation', requires_confirmation: true }, { userMessage: 'hi' }],
      [{ ok: true, action_id: 'act-1', status: 'recorded', binding: BINDING }, { userMessage: 'hi' }],
      [{ ok: true, action_id: 'act-1', status: 'recorded' }, {}],
      [{ ok: true, action_id: 'act-1', status: 'rejected' }, { userMessage: 'hi' }],
    ]
    for (const [response, action] of cases) {
      MessageProcessor._instances.length = 0
      cleanup()
      const { ctx } = gateCtx(['approved'], response)
      const host = { composer: { submit: vi.fn(() => true) } }
      await click(ctx, host, action)
      expect(host.composer.submit).not.toHaveBeenCalled()
    }
  })
})
