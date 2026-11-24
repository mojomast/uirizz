import { describe, expect, it } from 'vitest'
import { formatValue } from './format.js'

describe('formatValue', () => {
  it('formats numbers', () => {
    expect(formatValue(1234.567, 'number')).toBe('1,234.57')
    expect(formatValue('42', 'number')).toBe('42')
  })
  it('treats 0.42 as 42 percent', () => {
    expect(formatValue(0.42, 'percent')).toBe('42%')
  })
  it('formats currency with a code and falls back to USD', () => {
    expect(formatValue(1234.5, 'currency', 'USD')).toBe('$1,234.50')
    expect(formatValue(5, 'currency')).toBe('$5.00')
    expect(formatValue(5, 'currency', 'nope')).toBe('$5.00')
    expect(formatValue(5, 'currency', 'EUR')).toContain('€')
  })
  it('formats compact', () => {
    expect(formatValue(1500, 'compact')).toBe('1.5K')
    expect(formatValue(2000000, 'compact')).toBe('2M')
  })
  it('formats text as-is', () => {
    expect(formatValue('hello', 'text')).toBe('hello')
    expect(formatValue(7, 'text')).toBe('7')
  })
  it('formats dates in UTC', () => {
    expect(formatValue('2024-03-05', 'date')).toContain('2024')
    expect(formatValue('garbage', 'date')).toBe('—')
  })
  it('returns an em dash for missing or non-finite values', () => {
    for (const f of ['number', 'percent', 'currency', 'compact', 'text', 'date']) {
      expect(formatValue(null, f)).toBe('—')
      expect(formatValue(undefined, f)).toBe('—')
    }
    expect(formatValue(NaN, 'number')).toBe('—')
    expect(formatValue(Infinity, 'currency')).toBe('—')
    expect(formatValue('abc', 'percent')).toBe('—')
  })
})
