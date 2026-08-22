export const PRODUCTION_API_BASE = 'https://wod.kai.com/api'

/** Native builds must target the one canonical cloud API, never a local DB. */
export function normalizeNativeApiBase(value?: string | null): string {
  const candidate = String(value || PRODUCTION_API_BASE).trim()
  const url = new URL(candidate)
  if (url.protocol !== 'https:') throw new Error('VITE_KAI_APP_API_BASE must use HTTPS')
  if (url.username || url.password || url.search || url.hash || url.pathname.replace(/\/$/, '') !== '/api') {
    throw new Error('VITE_KAI_APP_API_BASE must be an HTTPS origin ending in /api')
  }
  return `${url.origin}/api`
}
