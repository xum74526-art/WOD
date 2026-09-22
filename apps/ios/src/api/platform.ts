import { request } from './request'

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
