import { describe, expect, it, vi } from 'vitest'
import { createRefresher } from './live.js'

function harness(results) {
  const timers = new Map()
  let n = 0
  let hidden = false
  let visCb = null
  const delays = []
  const queue = [...results]
  const refresh = vi.fn(async () => (queue.length ? queue.shift() : false))
  const r = createRefresher({
    refresh,
    setTimer: (fn, ms) => {
      n += 1
      timers.set(n, fn)
      delays.push(ms)
      return n
    },
    clearTimer: (id) => timers.delete(id),
    isHidden: () => hidden,
    onVisibility: (cb) => {
      visCb = cb
      return () => {
        visCb = null
      }
    },
  })
  const fire = async () => {
    const entry = [...timers].pop()
    timers.delete(entry[0])
    await entry[1]()
    await Promise.resolve()
  }
  return {
    r, refresh, timers, delays, fire,
    setHidden: (v) => { hidden = v; visCb && visCb() },
    hasVis: () => visCb !== null,
  }
}

const flush = () => new Promise((res) => setTimeout(res, 0))

describe('createRefresher', () => {
  it('backs off 4s, 8s, 16s, 30s cap while nothing changes', async () => {
    const h = harness([])
    h.r.start()
    await flush()
    for (let i = 0; i < 5; i++) {
      await h.fire()
      await flush()
    }
    expect(h.delays).toEqual([8000, 16000, 30000, 30000, 30000, 30000])
    h.r.stop()
  })

  it('resets to 4s on a change and on poke', async () => {
    const h = harness([false, false, true])
    h.r.start()
    await flush()
    await h.fire()
    await flush()
    await h.fire()
    await flush()
    expect(h.delays.slice(-1)).toEqual([4000])
    h.r.poke()
    await flush()
    expect(h.delays.slice(-1)).toEqual([4000])
    await h.fire()
    await flush()
    expect(h.delays.slice(-1)).toEqual([8000])
    h.r.stop()
  })

  it('pauses while hidden and resumes on visibility', async () => {
    const h = harness([])
    h.r.start()
    await flush()
    h.setHidden(true)
    expect(h.timers.size).toBe(0)
    const calls = h.refresh.mock.calls.length
    h.setHidden(false)
    await flush()
    expect(h.refresh.mock.calls.length).toBe(calls + 1)
    expect(h.timers.size).toBe(1)
    h.r.stop()
    expect(h.timers.size).toBe(0)
    expect(h.hasVis()).toBe(false)
  })

  it('uses 30s as a safety net once the socket is connected', async () => {
    const h = harness([])
    h.r.setSocketConnected(true)
    h.r.start()
    await flush()
    expect(h.delays).toEqual([30000])
    h.r.stop()
  })

  it('refreshNow runs a refresh immediately', async () => {
    const h = harness([])
    h.r.start()
    await flush()
    h.r.refreshNow()
    await flush()
    expect(h.refresh).toHaveBeenCalledTimes(2)
    h.r.stop()
  })
})
