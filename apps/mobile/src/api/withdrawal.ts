import { request } from './request'
import { makeIdempotencyKey } from '@/utils/idempotency'

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
  version?: number
}

function statusOf(value: string): WithdrawalStatus {
  return ({ requested: 'reviewing', approved: 'manual_payment_pending', cancelled: 'canceled' } as Record<string, WithdrawalStatus>)[value] || value as WithdrawalStatus
}

function toWithdrawal(row: any): WithdrawalOrder {
  return {
    id: row.id,
    order_no: row.withdrawal_no,
    status: statusOf(row.status),
    amount_card_hours: Number(row.amount || 0),
    locked_rate_cny: 1,
    gross_amount_cny: Number(row.amount || 0),
    fee_cny: 0,
    net_amount_cny: Number(row.amount || 0),
    bank_card: {
      id: 0,
      bank_name: row.payout?.bank_name || '',
      card_number: row.payout?.account_no || '',
      holder: row.payout?.beneficiary_name || '',
    },
    review_note: row.review_note,
    bank_reference: row.payment_reference,
    paid_at: row.paid_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
    version: row.version,
  }
}

function currentUser() {
  return request<{ user: { role?: string } }>({ url: '/auth/token/me', silent: true })
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
  return currentUser().then(({ user }) => {
    if (user.role !== 'supplier') {
      return request<any>({ url: '/account/modules', silent: true }).then(result => ({
        enabled: false,
        manual_transfer: true,
        rate_cny_per_card_hour: 1,
        fee_rate: 0,
        min_card_hours: 0,
        max_card_hours: 0,
        notice: result.revenue?.reason || '个人账户提现服务尚未配置',
      } as WithdrawalConfig))
    }
    return request<any>({ url: '/supplier/revenue', silent: true }).then(result => ({
      enabled: true,
      manual_transfer: true,
      rate_cny_per_card_hour: 1,
      fee_rate: Number(result.policy?.commission_rate || 0),
      min_card_hours: 0.01,
      max_card_hours: 1000000,
      notice: '商家收入使用统一后端人工银行转账结算',
    } as WithdrawalConfig))
  })
}

export function createWithdrawal(data: {
  amount_card_hours: number | string
  bank_card_id: number
  client_request_id: string
}) {
  return request<any>({
    url: '/account/withdrawals',
    method: 'POST',
    headers: { 'Idempotency-Key': makeIdempotencyKey('account-withdrawal', data.client_request_id) },
    data: { amount: data.amount_card_hours, currency: 'CNY', bank_account_id: data.bank_card_id },
  }).then(toWithdrawal)
}

export function getWithdrawals(params?: { page?: number; page_size?: number; status_filter?: WithdrawalStatus }) {
  const page = params?.page || 1
  const pageSize = params?.page_size || 20
  return currentUser().then(({ user }) => {
    if (user.role !== 'supplier') return { total: 0, page, page_size: pageSize, items: [] }
    return request<any[]>({ url: '/supplier/withdrawals' }).then(rows => {
      const items = rows.map(toWithdrawal).filter(row => !params?.status_filter || row.status === params.status_filter)
      const start = (page - 1) * pageSize
      return { total: items.length, page, page_size: pageSize, items: items.slice(start, start + pageSize) }
    })
  })
}

export function getWithdrawal(id: number | string) {
  return request<any[]>({ url: '/supplier/withdrawals' }).then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return toWithdrawal(row)
  })
}

export function cancelWithdrawal(id: number | string) {
  return request<any[]>({ url: '/supplier/withdrawals', silent: true }).then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return request<any>({
      url: `/supplier/withdrawals/${id}/cancel`, method: 'POST', data: { version: row.version },
    })
  }).then(toWithdrawal)
}
