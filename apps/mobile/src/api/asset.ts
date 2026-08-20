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
  return Promise.reject(new Error('服务器租约不支持转售')) as Promise<{
    id: number; status: string; sell_price: number; buy_price: number; pnl: number
  }>
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
  return request<Array<{
    id: number
    product_id: number
    order_id: number
    amount: string
    duration_hours: number
    status: string
    starts_at?: string | null
    expires_at?: string | null
    created_at?: string
    server_name: string
    gpu_model: string
    renewable: boolean
  }>>({ url: '/account/leases' }).then((leases) => {
    const filtered = status_filter ? leases.filter(item => item.status === status_filter) : leases
    const items = filtered.map<AssetItem>(lease => ({
      id: lease.id,
      product_id: lease.product_id,
      order_id: lease.order_id,
      quantity: 1,
      value: Number(lease.amount),
      unit_value: Number(lease.amount),
      daily_rate: 0,
      status: lease.status,
      start_at: lease.starts_at || undefined,
      end_at: lease.expires_at || undefined,
      created_at: lease.created_at,
      product_name: lease.server_name,
      gpu_model: lease.gpu_model,
      can_sell: false,
      revenue_settlement_enabled: false,
      reward_service_enabled: false,
      trading_unavailable_reason: 'lease_not_tradeable',
    }))
    return {
      total_value: items.reduce((sum, item) => sum + item.value, 0),
      wallet_balance: 0,
      pending_revenue: 0,
      revenue_rate: 0,
      revenue_settlement_enabled: false,
      historical_test_revenue: 0,
      items,
    }
  })
}

export function getAsset(id: number) {
  return getAssets().then(summary => {
    const asset = summary.items.find(item => item.id === id)
    if (!asset) throw new Error('服务器租约不存在')
    return asset
  })
}
