/** Adaptive poll scheduler. Pure (timers and visibility are injected) so it is easy to test. */

export const BASE_MS = 4000
export const MAX_MS = 30000

export function createRefresher({ refresh, setTimer, clearTimer, isHidden, onVisibility }) {
  let delay = BASE_MS
  let timer = null
  let stopped = true
  let running = false
  let rerun = false
  let socketConnected = false
  let unsubscribe = null

  const hidden = () => (typeof isHidden === 'function' ? Boolean(isHidden()) : false)

  function cancel() {
    if (timer !== null) {
      clearTimer(timer)
      timer = null
    }
  }

  function schedule() {
    cancel()
    if (stopped || hidden()) return
    timer = setTimer(() => {
      timer = null
      void tick()
    }, delay)
  }

  async function tick() {
    if (stopped) return
    if (hidden()) return // resumed by the visibility callback
    if (running) {
      rerun = true
      return
    }
    running = true
    let changed = false
    try {
      changed = Boolean(await refresh())
    } catch {
      changed = false
    }
    running = false
    if (stopped) return
    if (rerun) {
      rerun = false
      delay = BASE_MS
      void tick()
      return
    }
    if (changed) delay = BASE_MS
    else delay = Math.min(delay * 2, MAX_MS)
    if (socketConnected && !changed) delay = MAX_MS
    schedule()
  }

  return {
    /** Refresh now, then keep polling. */
    start() {
      if (!stopped) return
      stopped = false
      delay = BASE_MS
      if (typeof onVisibility === 'function') {
        const off = onVisibility(() => {
          if (stopped) return
          if (hidden()) {
            cancel()
          } else {
            delay = BASE_MS
            cancel()
            void tick()
          }
        })
        unsubscribe = typeof off === 'function' ? off : null
      }
      void tick()
    },
    /** Something probably changed (a click, a push): reset to the fast rate. */
    poke() {
      if (stopped) return
      delay = BASE_MS
      schedule()
    },
    /** Refresh immediately (socket revision) and reset to the fast rate. */
    refreshNow() {
      if (stopped) return
      delay = BASE_MS
      cancel()
      void tick()
    },
    setSocketConnected(value) {
      socketConnected = Boolean(value)
      if (socketConnected && !running && timer !== null && delay < MAX_MS) {
        delay = MAX_MS
        schedule()
      }
    },
    stop() {
      stopped = true
      cancel()
      if (unsubscribe) unsubscribe()
      unsubscribe = null
    },
  }
}
