import { request } from './request'

/**
 * Public, non-secret runtime capabilities returned by the business API.
 * The client treats missing or malformed fields as disabled.
 */
export interface PlatformCapabilities {
  commerce_mode: 'matchmaking' | 'direct_trade' | string
  matchmaking_enabled: boolean
  direct_trade_enabled: boolean
  payment_enabled: boolean
  recharge_enabled: boolean
  withdraw_enabled: boolean
  history_read_enabled: boolean
}

export function getPlatformCapabilities() {
  return request<PlatformCapabilities>({
    url: '/platform/capabilities',
    silent: true,
  })
}
