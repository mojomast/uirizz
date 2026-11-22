import { describe, expect, it } from 'vitest'
import { messagesFromPayload, newMessagesSince, parseResult, surfaceIdFrom } from './ids.js'

describe('surfaceIdFrom', () => {
  it('prefers a parsed result surface_id over args', () => {
    expect(surfaceIdFrom({ surface_id: 'args' }, '{"ok":true,"surface_id":"from-result"}')).toBe(
      'from-result',
    )
  })

  it('falls back to args and treats objects and junk defensively', () => {
    expect(surfaceIdFrom({ surface_id: 'demo' }, 'not-json')).toBe('demo')
    expect(surfaceIdFrom({}, { surface_id: 'obj' })).toBe('obj')
    expect(surfaceIdFrom({}, null)).toBe(null)
    expect(parseResult('')).toBe(null)
  })
})

describe('newMessagesSince', () => {
  it('returns only messages after the already-processed count', () => {
    const msgs = messagesFromPayload({ messages: [{ a: 1 }, { a: 2 }, { a: 3 }] })
    expect(newMessagesSince(msgs, 1)).toEqual([{ a: 2 }, { a: 3 }])
    expect(newMessagesSince(msgs, 3)).toEqual([])
  })
})
