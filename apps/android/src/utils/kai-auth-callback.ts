export interface KaiAuthCallback {
  ticket?: string
  bindTicket?: string
  deletionToken?: string
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

function parseKaiAuthValues(query: Record<string, unknown> | null | undefined, allowDeletionToken: boolean): KaiAuthCallback | null {
  if (!query) return null
  const ticket = typeof query.kai_ticket === 'string' ? query.kai_ticket.trim() : ''
  const bindTicket = typeof query.kai_bind_ticket === 'string' ? query.kai_bind_ticket.trim() : ''
  const deletionToken = allowDeletionToken && typeof query.kai_deletion_token === 'string' ? query.kai_deletion_token.trim() : ''
  const error = typeof query.kai_error === 'string' ? query.kai_error.trim() : ''
  return deletionToken ? { deletionToken } : bindTicket ? { bindTicket } : ticket ? { ticket } : error ? { error } : null
}

export function parseKaiAuthQuery(query: Record<string, unknown> | null | undefined): KaiAuthCallback | null {
  return parseKaiAuthValues(query, false)
}

export function parseKaiAuthUrl(input: unknown): KaiAuthCallback | null {
  if (typeof input !== 'string') return null
  const raw = input.trim()
  const isFullCallback = /^kai:\/\/auth(?:[/?#]|$)/i.test(raw)
  const isRuntimeQuery = !raw.includes('://') && /(?:^|[?&#])kai_(?:(?:bind_)?ticket|deletion_token|error)=/.test(raw)
  if (!isFullCallback && !isRuntimeQuery) return null
  const queryStart = raw.indexOf('?')
  const hashStart = raw.indexOf('#')
  const queryString = queryStart < 0
    ? (isRuntimeQuery ? raw.replace(/^[?&#]/, '') : '')
    : raw.slice(queryStart + 1, hashStart < 0 ? undefined : hashStart)
  const fragmentString = hashStart < 0 ? '' : raw.slice(hashStart + 1)
  const parsePairs = (value: string) => {
    const result: Record<string, string> = {}
    for (const pair of value.split('&')) {
      if (!pair) continue
      const separator = pair.indexOf('=')
      const key = decodeQueryValue(separator < 0 ? pair : pair.slice(0, separator))
      const pairValue = decodeQueryValue(separator < 0 ? '' : pair.slice(separator + 1))
      result[key] = pairValue
    }
    return result
  }
  if (isFullCallback) {
    // The deletion proof is returned in the fragment so browsers never send it
    // to the server or a referrer. Do not silently accept it from a query URL.
    const fragment = parseKaiAuthValues(parsePairs(fragmentString), true)
    if (fragment?.deletionToken) return fragment
    return parseKaiAuthValues(parsePairs(queryString), false)
  }
  const query: Record<string, string> = {}
  for (const pair of queryString.split('&')) {
    if (!pair) continue
    const separator = pair.indexOf('=')
    const key = decodeQueryValue(separator < 0 ? pair : pair.slice(0, separator))
    const value = decodeQueryValue(separator < 0 ? '' : pair.slice(separator + 1))
    query[key] = value
  }
  // Some native runtimes expose only the argument tail, losing whether it was
  // originally a query or fragment. It is still trusted app callback input.
  return parseKaiAuthValues(query, true)
}

export function kaiAuthCallbackFingerprint(callback: KaiAuthCallback) {
  const value = callback.bindTicket
    ? `bind:${callback.bindTicket}`
    : callback.deletionToken
      ? `delete:${callback.deletionToken}`
    : callback.ticket
      ? `ticket:${callback.ticket}`
      : `error:${callback.error || ''}`
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}
