import { act, render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsx } from 'react/jsx-runtime'
import { SurfaceCard } from './card.jsx'

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
  MessageProcessor._instances.length = 0
})

function makeCtx(payloads) {
  const calls = []
  let i = 0
  const intervals = []
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
    setInterval: (fn, ms) => {
      intervals.push(fn)
      return 1
    },
    clearInterval: vi.fn(),
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
    const intervals = []
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
      setInterval: (fn) => {
        intervals.push(fn)
        return 1
      },
      clearInterval: vi.fn(),
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
    const intervals = []
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
      setInterval: (fn) => {
        intervals.push(fn)
        return 1
      },
      clearInterval: vi.fn(),
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
})
