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

function toRevenueSummary(result: any): RevenueSummary {
  return {
    today: 0,
    total: Number(result.settled || 0),
    rate: 0,
    revenue_settlement_enabled: Boolean(result.module?.available),
    historical_test_total: 0,
  }
}

function toRevenueChart(result: any): RevenuePoint[] {
  return (result.records || []).map((row: any) => ({
    date: row.date || row.created_at,
    amount: Number(row.amount || 0),
  }))
}

export function getRevenueSummary() {
  return request<any>({ url: '/account/revenue' }).then(toRevenueSummary)
}

export function getRevenueChart(rangeDays: RevenueRange | number = 30) {
  return request<any>({ url: '/account/revenue', data: { range_days: rangeDays } })
    .then(toRevenueChart)
}

export function getRevenueDashboard(rangeDays: RevenueRange | number = 7) {
  return request<any>({ url: '/account/revenue', data: { range_days: rangeDays } }).then(result => ({
    summary: toRevenueSummary(result),
    chart: toRevenueChart(result),
  }))
}

export function getRevenueRecords() {
  return request<any>({ url: '/account/revenue' }).then(result => result.records || [])
}
