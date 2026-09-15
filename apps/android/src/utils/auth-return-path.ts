export const AUTH_RETURN_PATH_TTL_MS = 10 * 60 * 1000
export const AUTH_RETURN_PATH_STORAGE_KEY = 'ztw-auth-return-path-v1'

const MAX_RETURN_PATH_LENGTH = 512
const MAX_QUERY_VALUE_LENGTH = 64
const UNSAFE_TEXT = /[\u0000-\u001f\u007f\\]/

const RETURNABLE_ROUTES = new Set([
  'pages/index/index',
  'pages/market/index',
  'pages/community/index',
  'pages/community/publish',
  'pages/community/detail',
  'pages/assets/index',
  'pages/profile/index',
  'pages/product/detail',
  'pages/asset/detail',
  'pages/devices/index',
  'pages/revenue/index',
  'pages/orders/index',
  'pages/order/detail',
  'pages/wallet/index',
  'pages/wallet/ledger',
  'pages/wallet/recharges',
  'pages/withdrawals/index',
  'pages/withdrawals/detail',
  'pages/settings/index',
  'pages/notifications/index',
  'pages/profile-edit/index',
  'pages/invite/index',
  'pages/coupons/index',
  'pages/addresses/index',
  'pages/buy-request/index',
  'pages/compute-onboarding/index',
  'pages/supplier/dashboard',
  'pages/supplier/apply',
  'pages/supplier/devices',
  'pages/supplier/product-create',
  'pages/supplier/orders',
  'pages/supplier/revenue',
  'pages/supplier/stats',
  'pages/supplier/settings',
  'pages/supplier/rebate',
  'pages/rebate/index',
  'pages/store/index',
  'pages/quote/index',
  'pages/kefu/index',
])

const QUERY_KEYS = ['id', 'panel', 'compose', 'view', 'scope', 'status', 'model', 'variant'] as const
type QueryKey = typeof QUERY_KEYS[number]
const ROUTE_QUERY_KEYS: Readonly<Record<string, readonly QueryKey[]>> = {
  'pages/community/detail': ['id'],
  'pages/product/detail': ['id'],
  'pages/asset/detail': ['id'],
  'pages/order/detail': ['id'],
  'pages/withdrawals/detail': ['id'],
  'pages/store/index': ['id'],
  'pages/assets/index': ['panel'],
  'pages/devices/index': ['status'],
  'pages/buy-request/index': ['compose', 'view', 'scope'],
  'pages/quote/index': ['model', 'variant'],
}
const REQUIRED_QUERY_KEYS_BY_ROUTE: Readonly<Record<string, readonly QueryKey[]>> = {
  'pages/community/detail': ['id'],
  'pages/product/detail': ['id'],
  'pages/asset/detail': ['id'],
  'pages/order/detail': ['id'],
  'pages/withdrawals/detail': ['id'],
  'pages/store/index': ['id'],
}
const PANEL_VALUES = new Set([
  'asset-overview',
  'compute-assets',
  'device-hosting',
  'device-status',
  'hosting-earnings',
  'action-required',
  'expiry-maintenance',
])
const DEVICE_STATUS_VALUES = new Set(['pending_review', 'reviewing', 'deploying', 'running', 'action_required'])
const GPU_QUERY_VALUE = /^[A-Za-z0-9\u3400-\u9fff][A-Za-z0-9\u3400-\u9fff ._+()\/-]{0,63}$/

interface StoredAuthReturnPath {
  path: string
  expiresAt: number
}

function routeName(value: unknown) {
  if (typeof value !== 'string') return ''
  return value.startsWith('/') ? value.slice(1) : value
}

function queryValue(key: QueryKey, raw: unknown): string | null {
  if (typeof raw !== 'string' && typeof raw !== 'number' && typeof raw !== 'boolean') return null
  const value = String(raw).trim()
  if (!value || value.length > MAX_QUERY_VALUE_LENGTH || UNSAFE_TEXT.test(value)) return null
  if (key === 'id') return /^[1-9]\d{0,11}$/.test(value) && Number.isSafeInteger(Number(value)) ? value : null
  if (key === 'compose') return value === '1' ? value : null
  if (key === 'view') return value === 'buyer' || value === 'seller' ? value : null
  if (key === 'scope') return value === 'all' || value === 'quoted' ? value : null
  if (key === 'panel') return PANEL_VALUES.has(value) ? value : null
  if (key === 'status') return DEVICE_STATUS_VALUES.has(value) ? value : null
  return GPU_QUERY_VALUE.test(value) ? value : null
}

function isEmptyOptionalQueryValue(key: QueryKey, raw: unknown) {
  return (key === 'model' || key === 'variant')
    && (typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean')
    && String(raw).trim() === ''
}

export function buildAuthReturnPath(route: unknown, options: Record<string, unknown> = {}): string | null {
  const normalizedRoute = routeName(route)
  if (!RETURNABLE_ROUTES.has(normalizedRoute)) return null
  const requiredKeys = REQUIRED_QUERY_KEYS_BY_ROUTE[normalizedRoute] || []
  if (requiredKeys.some((key) => !Object.prototype.hasOwnProperty.call(options, key))) return null

  const query: string[] = []
  const includedKeys = new Set<QueryKey>()
  for (const key of ROUTE_QUERY_KEYS[normalizedRoute] || []) {
    if (!Object.prototype.hasOwnProperty.call(options, key)) continue
    const value = queryValue(key, options[key])
    if (value === null) {
      if (isEmptyOptionalQueryValue(key, options[key])) continue
      return null
    }
    includedKeys.add(key)
    query.push(`${key}=${encodeURIComponent(value)}`)
  }
  if (normalizedRoute === 'pages/quote/index' && includedKeys.has('variant') && !includedKeys.has('model')) return null
  const path = `/${normalizedRoute}${query.length ? `?${query.join('&')}` : ''}`
  return path.length <= MAX_RETURN_PATH_LENGTH ? path : null
}

export function normalizeAuthReturnPath(value: unknown): string | null {
  if (typeof value !== 'string' || !value || value.length > MAX_RETURN_PATH_LENGTH || UNSAFE_TEXT.test(value) || value.includes('#')) return null
  const parts = value.split('?')
  if (parts.length > 2 || (parts.length === 2 && !parts[1])) return null
  const normalizedRoute = routeName(parts[0])
  if (!RETURNABLE_ROUTES.has(normalizedRoute)) return null
  const allowedKeys = ROUTE_QUERY_KEYS[normalizedRoute] || []
  const allowedKeySet = new Set<string>(allowedKeys)
  const seenKeys = new Set<string>()
  const options: Record<string, unknown> = {}
  if (parts[1]) {
    const pairs = parts[1].split('&')
    if (pairs.length > allowedKeys.length) return null
    for (const pair of pairs) {
      const separator = pair.indexOf('=')
      if (separator <= 0 || pair.indexOf('=', separator + 1) >= 0) return null
      let key: string
      let decoded: string
      try {
        key = decodeURIComponent(pair.slice(0, separator))
        decoded = decodeURIComponent(pair.slice(separator + 1))
      } catch {
        return null
      }
      if (!allowedKeySet.has(key) || seenKeys.has(key)) return null
      seenKeys.add(key)
      const safeValue = queryValue(key as QueryKey, decoded)
      if (safeValue === null) {
        if (isEmptyOptionalQueryValue(key as QueryKey, decoded)) continue
        return null
      }
      options[key] = safeValue
    }
  }
  return buildAuthReturnPath(normalizedRoute, options)
}

function currentPageReturnPath(): string | null {
  try {
    if (typeof getCurrentPages !== 'function') return null
    const pages = getCurrentPages()
    const page = pages[pages.length - 1] as unknown as {
      route?: unknown
      options?: Record<string, unknown>
      $page?: { fullPath?: unknown; options?: Record<string, unknown> }
    } | undefined
    if (!page) return null
    const fullPath = normalizeAuthReturnPath(page.$page?.fullPath)
    return fullPath || buildAuthReturnPath(page.route, page.options || page.$page?.options || {})
  } catch {
    return null
  }
}

export function stageAuthReturnPath(now = Date.now()): string | null {
  const path = currentPageReturnPath()
  if (!path || !Number.isFinite(now)) return null
  try {
    const record: StoredAuthReturnPath = { path, expiresAt: now + AUTH_RETURN_PATH_TTL_MS }
    uni.setStorageSync(AUTH_RETURN_PATH_STORAGE_KEY, record)
    return path
  } catch {
    return null
  }
}

export function consumeAuthReturnPath(now = Date.now()): string | null {
  let raw: unknown
  try {
    raw = uni.getStorageSync(AUTH_RETURN_PATH_STORAGE_KEY)
    uni.removeStorageSync(AUTH_RETURN_PATH_STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw || typeof raw !== 'object') return null
  const record = raw as Partial<StoredAuthReturnPath>
  if (typeof record.expiresAt !== 'number') return null
  const remaining = record.expiresAt - now
  if (!Number.isFinite(remaining) || remaining <= 0 || remaining > AUTH_RETURN_PATH_TTL_MS) return null
  return normalizeAuthReturnPath(record.path)
}
