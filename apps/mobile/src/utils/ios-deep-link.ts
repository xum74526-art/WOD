export interface KaiAuthDeepLink {
  ticket?: string
  error?: 'access_denied' | 'missing_code' | 'invalid_issuer' | 'account_not_found' | 'identity_conflict' | 'authorization_failed'
}

const ALLOWED_ERRORS = new Set<KaiAuthDeepLink['error']>([
  'access_denied',
  'missing_code',
  'invalid_issuer',
  'account_not_found',
  'identity_conflict',
  'authorization_failed',
])

export function parseKaiAuthDeepLink(value: unknown): KaiAuthDeepLink | null {
  const source = String(value || '').trim()
  if (!source || source.length > 2048 || !/^kai:\/\/auth(?:[/?#]|$)/i.test(source)) return null

  try {
    const url = new URL(source)
    if (url.protocol.toLowerCase() !== 'kai:' || url.hostname.toLowerCase() !== 'auth') return null
    const ticket = String(url.searchParams.get('kai_ticket') || '').trim()
    const rawError = String(url.searchParams.get('kai_error') || '').trim() as KaiAuthDeepLink['error']
    if (ticket && rawError) return null
    if (ticket) {
      if (ticket.length < 16 || ticket.length > 512 || !/^[A-Za-z0-9._~-]+$/.test(ticket)) return null
      return { ticket }
    }
    if (rawError) {
      return { error: ALLOWED_ERRORS.has(rawError) ? rawError : 'authorization_failed' }
    }
  } catch {}
  return null
}

export function authDeepLinkRoute(link: KaiAuthDeepLink): string {
  if (link.ticket) return `/pages/login/index?kai_ticket=${encodeURIComponent(link.ticket)}`
  return `/pages/login/index?kai_error=${encodeURIComponent(link.error || 'authorization_failed')}`
}

let lastHandledArgument = ''
let listenerInstalled = false

export function handleNativeAuthDeepLink(argument?: unknown): boolean {
  let source = String(argument || '').trim()
  // #ifdef APP-PLUS
  if (!source) source = String(plus.runtime.arguments || '').trim()
  // #endif
  if (!source || source === lastHandledArgument) return false
  const link = parseKaiAuthDeepLink(source)
  if (!link) return false
  lastHandledArgument = source
  uni.reLaunch({ url: authDeepLinkRoute(link) })
  return true
}

export function installNativeAuthDeepLinkListener(): void {
  if (listenerInstalled) return
  listenerInstalled = true
  // #ifdef APP-PLUS
  ;(globalThis as any).plus?.globalEvent?.addEventListener('newintent', () => {
    handleNativeAuthDeepLink()
  })
  // #endif
}
