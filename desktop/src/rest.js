/** ctx.rest helper. Host attaches auth; never add authorization headers. */

export async function restJson(ctx, path, options = {}) {
  if (!ctx || typeof ctx.rest !== 'function') {
    return { ok: false, code: 'rest_unavailable', error: 'ctx.rest is not available.' }
  }
  const init = { method: options.method || 'GET' }
  if (options.body !== undefined) {
    init.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body)
    init.headers = { 'content-type': 'application/json' }
  }
  const response = await ctx.rest(path, init)
  if (response == null) return { ok: false, code: 'empty_response' }
  if (typeof response === 'object' && !Array.isArray(response)) {
    // Some hosts return a fetch Response; others already return JSON.
    if (typeof response.json === 'function' && typeof response.ok === 'boolean' && response.headers) {
      let body = null
      try {
        body = await response.json()
      } catch {
        body = null
      }
      if (body && typeof body === 'object') return body
      return { ok: response.ok, code: response.ok ? undefined : 'http_error', status: response.status }
    }
    return response
  }
  if (typeof response === 'string') {
    try {
      return JSON.parse(response)
    } catch {
      return { ok: false, code: 'invalid_response' }
    }
  }
  return { ok: false, code: 'invalid_response' }
}
