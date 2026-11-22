/** Extract a surface id and payload fields from a tool call, defensively. */

export function parseResult(result) {
  if (result == null) return null
  if (typeof result === 'object' && !Array.isArray(result)) return result
  if (typeof result === 'string') {
    const text = result.trim()
    if (!text) return null
    try {
      const parsed = JSON.parse(text)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return null
}

export function surfaceIdFrom(args, result) {
  const parsed = parseResult(result)
  const fromResult = parsed && typeof parsed.surface_id === 'string' ? parsed.surface_id.trim() : ''
  const fromArgs = args && typeof args.surface_id === 'string' ? args.surface_id.trim() : ''
  return fromResult || fromArgs || null
}

export function messagesFromPayload(payload) {
  return payload && Array.isArray(payload.messages) ? payload.messages : []
}

export function newMessagesSince(messages, already) {
  if (!Array.isArray(messages)) return []
  if (!Number.isFinite(already) || already < 0) return messages
  return messages.slice(already)
}
