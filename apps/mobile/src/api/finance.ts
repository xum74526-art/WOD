import { request, upload } from './request'
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
}

export interface FinanceVerificationPage {
  total: number
  page: number
  page_size: number
  items: FinanceVerification[]
}

export function getFinanceAccess(silent = true) {
  return request<FinanceAccess>({ url: '/finance/me', silent })
}

export function getFinanceBankCards(params?: { status_filter?: BankCardItem['status']; page?: number; page_size?: number }) {
  return request<FinanceBankCardPage>({ url: '/finance/bank-cards', data: params || {} })
}

export function getFinanceVerifications(params?: { status_filter?: FinanceVerification['status']; page?: number; page_size?: number }) {
  return request<FinanceVerificationPage>({ url: '/finance/verifications', data: params || {} })
}

export function getFinanceVerification(id: number) {
  return request<FinanceVerification>({ url: `/finance/verifications/${id}` })
}

export function reviewFinanceVerification(id: number, approved: boolean, reason?: string) {
  return request<FinanceVerification>({
    url: `/finance/verifications/${id}/review`, method: 'POST', data: { approved, reason: reason || undefined },
  })
}

export function reviewFinanceBankCard(id: number, approved: boolean, reason?: string) {
  return request<BankCardItem>({
    url: `/finance/bank-cards/${id}/review`,
    method: 'POST',
    data: { approved, reason: reason || undefined },
  })
}

export function getFinanceWithdrawals(params?: { status_filter?: WithdrawalStatus; page?: number; page_size?: number }) {
  return request<WithdrawalPage>({ url: '/finance/withdrawals', data: params || {} })
}

export function getFinanceWithdrawal(id: number | string) {
  return request<WithdrawalOrder>({ url: `/finance/withdrawals/${id}` })
}

export function approveFinanceWithdrawal(id: number | string, note?: string) {
  return request<WithdrawalOrder>({
    url: `/finance/withdrawals/${id}/approve`, method: 'POST', data: { note: note || undefined },
  })
}

export function rejectFinanceWithdrawal(id: number | string, reason: string) {
  return request<WithdrawalOrder>({
    url: `/finance/withdrawals/${id}/reject`, method: 'POST', data: { reason },
  })
}

export function markFinanceWithdrawalFailed(id: number | string, reason: string) {
  return request<WithdrawalOrder>({
    url: `/finance/withdrawals/${id}/mark-failed`, method: 'POST', data: { reason },
  })
}

export function getPaymentInstructions(id: number | string) {
  return request<PaymentInstructions>({
    url: `/finance/withdrawals/${id}/payment-instructions`, data: { reveal: true },
  })
}

export function markFinanceWithdrawalPaid(
  id: number | string,
  filePath: string,
  data: { bank_reference: string; paid_amount_cny: string; paid_at: string; payee_confirmed: 'true'; reveal_token: string },
) {
  return upload<WithdrawalOrder>({
    url: `/finance/withdrawals/${id}/mark-paid`,
    filePath,
    name: 'receipt',
    formData: data,
    timeout: 60000,
  })
}
