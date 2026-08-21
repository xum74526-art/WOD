import { request } from './request'

export type RevenueRange = 7 | 30 | 90

export interface RevenueSummary {
  today: number
  total: number
  rate: number
  revenue_settlement_enabled: boolean
  historical_test_total: number
}

export interface RevenuePoint {
  date: string
  amount: number
}

export interface RevenueRecord {
  id: number
  asset_id?: number
  amount: number
  date?: string
  created_at?: string
}

export function getRevenueSummary() {
  return request<RevenueSummary>({ url: '/revenue' })
}

export function getRevenueChart(rangeDays: RevenueRange | number = 30) {
  return request<RevenuePoint[]>({ url: '/revenue/chart', data: { range_days: rangeDays } })
}

export function getRevenueRecords() {
  return request<RevenueRecord[]>({ url: '/revenue/records' })
}
