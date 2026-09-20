export const PRODUCTION_API_BASE = 'https://wod.kai.com/api'

/** Native builds must target the one canonical cloud API, never a local DB. */
export function normalizeNativeApiBase(value?: string | null): string {
  const candidate = String(value || PRODUCTION_API_BASE).trim()
  if (!/^https:\/\//i.test(candidate)) {
    throw new Error('VITE_KAI_APP_API_BASE must use HTTPS')
  }

  // app-plus runs in a native JS engine where the browser URL global is not
  // available. Parse this deliberately narrow configuration value without it:
  // an HTTPS hostname, an optional valid port, and exactly the /api path.
  const match = /^https:\/\/([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::(\d{1,5}))?\/api\/?$/i.exec(candidate)
  const port = match?.[2] ? Number(match[2]) : null
  if (!match || (port !== null && (port < 1 || port > 65535))) {
    throw new Error('VITE_KAI_APP_API_BASE must be an HTTPS origin ending in /api')
  }

  const normalizedPort = port && port !== 443 ? `:${port}` : ''
  return `https://${match[1].toLowerCase()}${normalizedPort}/api`
}

/** Build a Web page URL for the same deployment as the configured App API. */
export function resolvePublicWebUrl(path: string, apiBase?: string | null): string {
  const normalizedPath = String(path || '').trim()
  if (!/^\/[a-z0-9][a-z0-9/_-]*$/i.test(normalizedPath)) {
    throw new Error('Public Web path must be an absolute application path')
  }

  const normalizedApiBase = normalizeNativeApiBase(apiBase)
  return `${normalizedApiBase.slice(0, -4)}${normalizedPath}`
}
