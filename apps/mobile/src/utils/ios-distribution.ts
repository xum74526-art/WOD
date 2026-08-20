export type IosDistribution = 'app-store' | 'enterprise'

export function normalizeIosDistribution(value: unknown): IosDistribution {
  return String(value || '').trim().toLowerCase() === 'enterprise'
    ? 'enterprise'
    : 'app-store'
}

export function shouldRestrictCommerce(
  platform: unknown,
  distribution: unknown,
): boolean {
  return String(platform || '').trim().toLowerCase() === 'ios'
    && normalizeIosDistribution(distribution) === 'app-store'
}

export const IOS_DISTRIBUTION = normalizeIosDistribution(
  (import.meta as any).env?.VITE_KAI_IOS_DISTRIBUTION,
)

export function currentNativePlatform(): string {
  try {
    const info = uni.getSystemInfoSync() as UniNamespace.GetSystemInfoResult & {
      osName?: string
    }
    return String(info.osName || info.platform || '').toLowerCase()
  } catch {
    return ''
  }
}

export function isIosAppStoreCompanion(): boolean {
  return shouldRestrictCommerce(currentNativePlatform(), IOS_DISTRIBUTION)
}

export function isDirectCommerceEnabled(): boolean {
  return !isIosAppStoreCompanion()
}

const DIRECT_COMMERCE_ROUTES = [
  '/pages/buy-request/index',
  '/pages/offline-purchase/index',
  '/pages/supplier/product-create',
]

export function isDistributionRouteAllowed(
  url: unknown,
  directCommerceEnabled = isDirectCommerceEnabled(),
): boolean {
  if (directCommerceEnabled) return true
  const path = String(url || '').split('?')[0]
  return !DIRECT_COMMERCE_ROUTES.includes(path)
}
