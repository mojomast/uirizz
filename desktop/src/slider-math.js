function stepAcceptsValue(step, min, value) {
  if (step == null || step === '' || step === 'any') return true
  const size = Number(step)
  const offset = Number(value) - Number(min)
  if (!Number.isFinite(size) || size <= 0 || !Number.isFinite(offset)) return false
  const remainder = offset / size
  return Math.abs(remainder - Math.round(remainder)) < 1e-9
}

export function sliderProgress({ min = 0, max, value } = {}) {
  const lo = Number(min)
  const hi = Number(max)
  const current = Number(value)
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || !Number.isFinite(current)) return 0
  if (hi === lo) return 0
  const progress = (current - lo) / (hi - lo)
  return Number.isFinite(progress) ? progress : 0
}

export function sliderInputAttrs({ min = 0, max, value, steps } = {}) {
  const lo = min === undefined || min === null ? 0 : min
  const hi = max
  const officialStep =
    typeof steps === 'number' && steps > 0 && Number(hi) > Number(lo) ? (Number(hi) - Number(lo)) / steps : undefined

  let step = officialStep
  if (step !== undefined && !stepAcceptsValue(step, lo, value)) step = undefined

  if (step === undefined) {
    const integerRange = Number.isInteger(Number(lo)) && Number.isInteger(Number(hi))
    const candidate = integerRange ? 1 : 'any'
    step = stepAcceptsValue(candidate, lo, value) ? candidate : 'any'
  }

  return { min: lo, max: hi, value, step }
}
