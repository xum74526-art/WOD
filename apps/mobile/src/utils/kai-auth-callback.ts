export interface KaiAuthCallback {
  ticket?: string
  error?: string
}

export const KAI_AUTH_APP_RETURN_URL = 'kai://auth'

function decodeQueryValue(value: string) {
  try {
    return decodeURIComponent(value.replace(/\+/g, ' '))
  } catch {
    return value
  }
}

export function parseKaiAuthQuery(query: Record<string, unknown> | null | undefined): KaiAuthCallback | null {
  if (!query) return null
  const ticket = typeof query.kai_ticket === 'string' ? query.kai_ticket.trim() : ''
  const error = typeof query.kai_error === 'string' ? query.kai_error.trim() : ''
  return ticket ? { ticket } : error ? { error } : null
}

export function parseKaiAuthUrl(input: unknown): KaiAuthCallback | null {
  if (typeof input !== 'string') return null
  const raw = input.trim()
  if (!/^kai:\/\/auth(?:[/?#]|$)/i.test(raw)) return null
  const queryStart = raw.indexOf('?')
  if (queryStart < 0) return null
  const hashStart = raw.indexOf('#', queryStart)
  const queryString = raw.slice(queryStart + 1, hashStart < 0 ? undefined : hashStart)
  const query: Record<string, string> = {}
  for (const pair of queryString.split('&')) {
    if (!pair) continue
    const separator = pair.indexOf('=')
    const key = decodeQueryValue(separator < 0 ? pair : pair.slice(0, separator))
    const value = decodeQueryValue(separator < 0 ? '' : pair.slice(separator + 1))
    query[key] = value
  }
  return parseKaiAuthQuery(query)
}

export function kaiAuthCallbackFingerprint(callback: KaiAuthCallback) {
  const value = callback.ticket ? `ticket:${callback.ticket}` : `error:${callback.error || ''}`
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}
