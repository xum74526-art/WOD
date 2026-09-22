import { request } from './request'

export type RevenueRange = 7 | 30 | 90

export interface RevenueSummary {
  today: number
  total: number
  rate: number
  settled_rebate_total: number
  settled_rebate_today: number
  pending_rebate: number
  holding_realized_pnl: number
  holding_realized_pnl_today: number
  holding_unrealized_pnl: number
  holding_unrealized_pnl_rate: number
  holding_active_assets: number
  holding_priced_assets: number
  audited_earnings_enabled: boolean
  revenue_settlement_enabled: boolean
  historical_test_total: number
}

export interface RevenuePoint {
  date: string
  amount: number
}

export interface RevenueRecord {
  id: number
  record_key?: string
  source_type?: 'consumer_rebate' | 'holding_sale'
  asset_id?: number
  amount: number
  date?: string
  created_at?: string
}

export interface RevenueChartOptions {
  silent?: boolean
}

export function getRevenueSummary() {
  return request<RevenueSummary>({ url: '/revenue' })
}

export function getRevenueChart(rangeDays: RevenueRange | number = 30, options: RevenueChartOptions = {}) {
  return request<RevenuePoint[]>({ url: '/revenue/chart', data: { range_days: rangeDays }, silent: options.silent })
}

export function getRevenueRecords() {
  return request<RevenueRecord[]>({ url: '/revenue/records' })
}
