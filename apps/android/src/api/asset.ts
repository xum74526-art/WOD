import { request } from './request'

export interface AssetItem {
  id: number
  product_id: number
  order_id?: number
  quantity: number
  value: number
  unit_value?: number
  daily_rate: number
  status: string
  start_at?: string
  end_at?: string
  created_at?: string
  product_name?: string
  gpu_model?: string
  today_revenue?: number
  accumulated_revenue?: number
  remaining_days?: number
  purchase_type?: string
  current_price?: number
  pnl?: number
  pnl_pct?: number
  can_sell?: boolean
  rebate_status?: string
  rebate_amount?: number
  rebate_info?: { month_spent: number; month_rebated: number; current_rate: number; next_tier_hint: string; pending_rebate: number; monthly_cap: number }
  revenue_settlement_enabled?: boolean
  historical_test_revenue?: number
  reward_service_enabled?: boolean
  historical_test_reward?: number
  trading_unavailable_reason?: string
}

export function sellAsset(id: number) {
  return request<{ id: number; status: string; sell_price: number; buy_price: number; pnl: number }>({ url: `/assets/${id}/sell`, method: 'POST' })
}

export interface AssetSummary {
  total_value: number
  wallet_balance: number
  pending_revenue: number
  revenue_rate: number
  revenue_settlement_enabled: boolean
  historical_test_revenue: number
  items: AssetItem[]
}

export function getAssets(status_filter?: string) {
  return request<AssetSummary>({ url: '/assets', data: status_filter ? { status_filter } : {} })
}

export function getAsset(id: number) {
  return request<AssetItem>({ url: `/assets/${id}` })
}
