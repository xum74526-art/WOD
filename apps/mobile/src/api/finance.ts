import { request } from './request'
import type { BankCardItem } from './bank-card'
import type { VerificationOcrFields } from './verification'
import type { WithdrawalOrder, WithdrawalPage, WithdrawalStatus } from './withdrawal'

export interface FinanceAccess {
  is_finance_admin: boolean
  manual_bank_card_enabled: boolean
  manual_payout_enabled: boolean
}

export interface FinanceBankCardPage {
  total: number
  page: number
  page_size: number
  items: BankCardItem[]
}

export interface PaymentInstructions {
  holder: string
  bank_name: string
  card_number: string
  phone?: string | null
  verification_mode?: 'format_only' | 'manual_review'
  bank_verified?: false
  notice?: string
  reveal_token: string
  reveal_expires_at: string
}

export interface FinanceVerification extends VerificationOcrFields {
  id: number
  user_id: number
  username: string
  real_name: string
  id_card_masked: string
  status: 'pending' | 'verified' | 'rejected'
  reject_reason?: string | null
  front_photo_uploaded: boolean
  back_photo_uploaded: boolean
  created_at?: string | null
  updated_at?: string | null
  version?: number
}

function toVerification(row: any): FinanceVerification {
  const identifier = row.subject?.identifier_number || ''
  return {
    id: row.id,
    user_id: row.applicant?.id,
    username: row.applicant?.display_name || '',
    real_name: row.subject?.legal_name || '',
    id_card_masked: identifier,
    status: row.status === 'approved' ? 'verified' : row.status,
    reject_reason: row.review_note,
    front_photo_uploaded: false,
    back_photo_uploaded: false,
    created_at: row.created_at,
    updated_at: row.updated_at,
    version: row.version,
    ocr_status: 'unavailable',
    ocr_message: '统一后端使用加密资料人工审核',
  }
}

function withdrawalStatus(value: string): WithdrawalStatus {
  return ({ requested: 'reviewing', approved: 'manual_payment_pending', cancelled: 'canceled' } as Record<string, WithdrawalStatus>)[value] || value as WithdrawalStatus
}

function toWithdrawal(row: any): WithdrawalOrder {
  return {
    id: row.id,
    order_no: row.withdrawal_no,
    status: withdrawalStatus(row.status),
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

function listAdminWithdrawals(status?: string) {
  return request<any[]>({ url: '/admin/withdrawals', data: status ? { status } : {} })
}

export interface FinanceVerificationPage {
  total: number
  page: number
  page_size: number
  items: FinanceVerification[]
}

export function getFinanceAccess(silent = true) {
  return request<any>({ url: '/account/summary', silent }).then(result => ({
    is_finance_admin: result.user?.role === 'admin',
    manual_bank_card_enabled: false,
    manual_payout_enabled: result.user?.role === 'admin',
  }))
}

export function getFinanceBankCards(params?: { status_filter?: BankCardItem['status']; page?: number; page_size?: number }) {
  void params
  return Promise.resolve({ total: 0, page: 1, page_size: 50, items: [] })
}

export function getFinanceVerifications(params?: { status_filter?: FinanceVerification['status']; page?: number; page_size?: number }) {
  const page = params?.page || 1
  const pageSize = params?.page_size || 20
  const status = params?.status_filter === 'verified' ? 'approved' : params?.status_filter
  return request<any[]>({ url: '/admin/kyc', data: status ? { status } : {} }).then(rows => {
    const items = rows.map(toVerification)
    const start = (page - 1) * pageSize
    return { total: items.length, page, page_size: pageSize, items: items.slice(start, start + pageSize) }
  })
}

export function getFinanceVerification(id: number) {
  return request<any[]>({ url: '/admin/kyc' }).then(rows => {
    const row = rows.find(item => item.id === id)
    if (!row) throw new Error('实名认证申请不存在')
    return toVerification(row)
  })
}

export function reviewFinanceVerification(id: number, approved: boolean, reason?: string) {
  return request<any[]>({ url: '/admin/kyc', silent: true }).then(rows => {
    const row = rows.find(item => item.id === id)
    if (!row) throw new Error('实名认证申请不存在')
    if (approved) {
      return request<any>({
        url: `/admin/kyc/${id}/approve`,
        method: 'POST',
        data: { version: row.version, note: reason || undefined },
      })
    }
    return request<any>({
      url: `/admin/kyc/${id}/reject`,
      method: 'POST',
      data: { version: row.version, note: reason || '管理员驳回' },
    })
  }).then(toVerification)
}

export function reviewFinanceBankCard(id: number, approved: boolean, reason?: string) {
  void id
  void approved
  void reason
  return Promise.reject<BankCardItem>(new Error('统一后端未启用人工银行卡审核'))
}

export function getFinanceWithdrawals(params?: { status_filter?: WithdrawalStatus; page?: number; page_size?: number }) {
  const page = params?.page || 1
  const pageSize = params?.page_size || 20
  const status = params?.status_filter
    ? ({ reviewing: 'requested', manual_payment_pending: 'approved', canceled: 'cancelled' } as Record<string, string>)[params.status_filter] || params.status_filter
    : undefined
  return listAdminWithdrawals(status).then(rows => {
    const items = rows.map(toWithdrawal)
    const start = (page - 1) * pageSize
    return { total: items.length, page, page_size: pageSize, items: items.slice(start, start + pageSize) }
  })
}

export function getFinanceWithdrawal(id: number | string) {
  return listAdminWithdrawals().then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return toWithdrawal(row)
  })
}

export function approveFinanceWithdrawal(id: number | string, note?: string) {
  return listAdminWithdrawals().then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return request<any>({
      url: `/admin/withdrawals/${id}/approve`, method: 'POST', data: { version: row.version, note },
    })
  }).then(toWithdrawal)
}

export function rejectFinanceWithdrawal(id: number | string, reason: string) {
  return listAdminWithdrawals().then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return request<any>({
      url: `/admin/withdrawals/${id}/reject`, method: 'POST', data: { version: row.version, note: reason },
    })
  }).then(toWithdrawal)
}

export function markFinanceWithdrawalFailed(id: number | string, reason: string) {
  return rejectFinanceWithdrawal(id, reason)
}

export function getPaymentInstructions(id: number | string) {
  return listAdminWithdrawals().then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return {
      holder: row.payout?.beneficiary_name || '',
      bank_name: row.payout?.bank_name || '',
      card_number: row.payout?.account_no || '',
      notice: '仅用于本次管理员人工转账',
      reveal_token: `admin-session-${id}`,
      reveal_expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
    } as PaymentInstructions
  })
}

export function markFinanceWithdrawalPaid(
  id: number | string,
  filePath: string,
  data: { bank_reference: string; paid_amount_cny: string; paid_at: string; payee_confirmed: 'true'; reveal_token: string },
) {
  void filePath
  return listAdminWithdrawals().then(rows => {
    const row = rows.find(item => String(item.id) === String(id))
    if (!row) throw new Error('提现申请不存在')
    return request<any>({
      url: `/admin/withdrawals/${id}/complete`,
      method: 'POST',
      data: {
        version: row.version,
        payment_reference: data.bank_reference,
        note: `人工确认付款 ${data.paid_amount_cny} CNY，时间 ${data.paid_at}`,
      },
    })
  }).then(toWithdrawal)
}
