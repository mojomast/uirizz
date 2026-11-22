import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { sliderInputAttrs, sliderProgress } from './slider-math.js'

const here = dirname(fileURLToPath(import.meta.url))

function stepAcceptsValue(step, min, value) {
  if (step === 'any' || step == null || step === '') return true
  const n = Number(step)
  if (!Number.isFinite(n) || n <= 0) return false
  const rem = (Number(value) - Number(min)) / n
  return Math.abs(rem - Math.round(rem)) < 1e-9
}

describe('sliderProgress', () => {
  it('places the thumb at (value-min)/(max-min) when min is greater than 0', () => {
    // Regression for the live Desktop bug: min=1, max=12, value=3 must sit at
    // 2/11 of the track, not at 0 (far left) and not at 3/12 (value/max).
    expect(sliderProgress({ min: 1, max: 12, value: 3 })).toBeCloseTo(2 / 11, 8)
    expect(sliderProgress({ min: 1, max: 12, value: 1 })).toBeCloseTo(0, 8)
    expect(sliderProgress({ min: 1, max: 12, value: 12 })).toBeCloseTo(1, 8)
    expect(sliderProgress({ min: 0, max: 100, value: 33 })).toBeCloseTo(0.33, 8)
  })
})

describe('sliderInputAttrs', () => {
  it('keeps value 3 visible when min is 1, max is 12, and steps is 1', () => {
    // Official A2UI "steps" is the number of divisions, so steps=1 becomes
    // HTML step=(12-1)/1=11. Browsers then snap the thumb to min. The
    // bound value must still be 3 and the HTML step must accept 3.
    const a = sliderInputAttrs({ min: 1, max: 12, value: 3, steps: 1 })
    expect(Number(a.min)).toBe(1)
    expect(Number(a.max)).toBe(12)
    expect(Number(a.value)).toBe(3)
    expect(stepAcceptsValue(a.step, a.min, a.value)).toBe(true)
    expect(sliderProgress({ min: 1, max: 12, value: Number(a.value) })).toBeCloseTo(2 / 11, 8)
  })

  it('maps official steps as divisions when the value already sits on a tick', () => {
    const a = sliderInputAttrs({ min: 0, max: 100, value: 20, steps: 5 })
    expect(Number(a.step)).toBe(20)
    expect(Number(a.value)).toBe(20)
    expect(stepAcceptsValue(a.step, a.min, a.value)).toBe(true)
  })

  it('omitting steps leaves a unit increment for an integer range', () => {
    const a = sliderInputAttrs({ min: 1, max: 12, value: 3 })
    expect(Number(a.value)).toBe(3)
    expect(stepAcceptsValue(a.step || 1, a.min, a.value)).toBe(true)
  })
})

describe('catalog wiring', () => {
  it('catalog.js uses sliderInputAttrs or sliderProgress so the fix is actually rendered', () => {
    const src = readFileSync(resolve(here, 'catalog.js'), 'utf8')
    expect(src).toMatch(/sliderInputAttrs|sliderProgress/)
  })
})
