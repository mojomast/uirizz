const DASH = '—'

function toNumber(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return NaN
  if (typeof value === 'number') return value
  if (typeof value === 'string') return Number(value.trim())
  return NaN
}

function safeCurrency(currency) {
  const code = typeof currency === 'string' ? currency.trim().toUpperCase() : ''
  return /^[A-Z]{3}$/.test(code) ? code : 'USD'
}

function intl(options) {
  return new Intl.NumberFormat(undefined, options)
}

export function formatValue(value, format, currency) {
  if (value === null || value === undefined || value === '') return DASH
  try {
    switch (format) {
      case 'text':
        return typeof value === 'object' ? JSON.stringify(value) : String(value)
      case 'date': {
        const d = value instanceof Date ? value : new Date(value)
        if (Number.isNaN(d.getTime())) return DASH
        return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(d)
      }
      case 'percent': {
        const n = toNumber(value)
        return Number.isFinite(n) ? intl({ style: 'percent', maximumFractionDigits: 1 }).format(n) : DASH
      }
      case 'currency': {
        const n = toNumber(value)
        if (!Number.isFinite(n)) return DASH
        return intl({ style: 'currency', currency: safeCurrency(currency) }).format(n)
      }
      case 'compact': {
        const n = toNumber(value)
        return Number.isFinite(n) ? intl({ notation: 'compact', maximumFractionDigits: 1 }).format(n) : DASH
      }
      case 'number':
      default: {
        const n = toNumber(value)
        if (Number.isFinite(n)) return intl({ maximumFractionDigits: 2 }).format(n)
        return format === 'number' || format === undefined ? DASH : String(value)
      }
    }
  } catch {
    return DASH
  }
}
