import { request } from './request'

export type WithdrawalStatus =
  | 'reviewing'
  | 'manual_payment_pending'
  | 'paid'
  | 'rejected'
  | 'failed'
  | 'canceled'

export interface WithdrawalBankCardSnapshot {
  id: number
  bank_name: string
  card_number: string
  card_last4?: string
  holder: string
  status?: 'registered' | 'pending_review' | 'active' | 'rejected' | 'disabled'
  verification_mode?: 'format_only' | 'manual_review'
  bank_verified?: false
}

export interface WithdrawalOrder {
  id: number
  order_no: string
  status: WithdrawalStatus
  amount_card_hours: number
  locked_rate_cny: number
  gross_amount_cny: number
  fee_cny: number
  net_amount_cny: number
  bank_card: WithdrawalBankCardSnapshot
  review_note?: string | null
  failure_reason?: string | null
  bank_reference?: string | null
  paid_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface WithdrawalConfig {
  enabled: boolean
  manual_transfer: true
  rate_cny_per_card_hour: number
  fee_rate: number
  min_card_hours: number
  max_card_hours: number
  statuses?: WithdrawalStatus[]
  bank_verified?: false
  notice?: string
}

export interface WithdrawalPage {
  total: number
  page: number
  page_size: number
  items: WithdrawalOrder[]
}

export function getWithdrawalConfig() {
  return request<WithdrawalConfig>({ url: '/withdrawals/config', silent: true })
}

export function createWithdrawal(data: {
  amount_card_hours: number | string
  bank_card_id: number
  client_request_id: string
}) {
  return request<WithdrawalOrder>({ url: '/withdrawals', method: 'POST', data })
}

export function getWithdrawals(params?: { page?: number; page_size?: number; status_filter?: WithdrawalStatus }) {
  return request<WithdrawalPage>({ url: '/withdrawals', data: params || {} })
}

export function getWithdrawal(id: number | string) {
  return request<WithdrawalOrder>({ url: `/withdrawals/${id}` })
}

export function cancelWithdrawal(id: number | string) {
  return request<WithdrawalOrder>({ url: `/withdrawals/${id}/cancel`, method: 'POST' })
}
