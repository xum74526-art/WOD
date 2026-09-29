import { request } from './request'

export type DisplayCurrencyCode = 'CNY' | 'HKD' | 'USD'

export interface DisplayCurrencyConfig {
  base_currency: 'CNY'
  settlement_currency: 'CNY'
  fraction_digits: 3
  card_hour_cny_rate: number
  rates: Record<DisplayCurrencyCode, number>
  rate_mode: 'daily_reference'
  rate_source: string
  rate_date: string | null
  rates_stale: boolean
  conversion_scope: 'display_only'
}

/**
 * Public, non-secret runtime capabilities returned by the business API.
 * The client treats missing or malformed fields as disabled.
 */
export interface PlatformCapabilities {
  commerce_mode: 'matchmaking' | 'direct_trade' | string
  matchmaking_enabled: boolean
  direct_trade_enabled: boolean
  holding_trade_enabled: boolean
  payment_enabled: boolean
  recharge_enabled: boolean
  withdraw_enabled: boolean
  history_read_enabled: boolean
  display_currency: DisplayCurrencyConfig
}

export type MobilePlatform = 'android' | 'ios'
export const MOBILE_APPLICATION_ID = 'com.kai.ztwstarmap'

export interface AppReleaseInfo {
  platform: MobilePlatform
  application_id: string | null
  available: boolean
  latest_version_name: string | null
  latest_version_code: number | null
  update_url: string | null
  release_notes_zh: string[]
  release_notes_en: string[]
}

export function getPlatformCapabilities() {
  return request<PlatformCapabilities>({
    url: '/platform/capabilities',
    silent: true,
  })
}

export function getAppRelease(platform: MobilePlatform) {
  return request<AppReleaseInfo>({
    url: '/platform/app-release',
    data: { platform, application_id: MOBILE_APPLICATION_ID },
    silent: true,
    auth: 'none',
  })
}
