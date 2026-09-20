import { request } from './request'

export interface BankCardItem {
  id: number
  bank_name: string
  card_number: string
  card_last4?: string
  holder: string
  phone?: string
  is_default: boolean
  status: 'registered' | 'pending_review' | 'active' | 'rejected' | 'disabled'
  verification_mode: 'format_only' | 'manual_review' | 'legacy_unvalidated'
  bank_verified: false
  consent_recorded: boolean
  consent_version: string | null
  reject_reason?: string | null
  created_at?: string | null
  reviewed_at?: string | null
}

export function getBankCards() {
  return request<BankCardItem[]>({ url: '/bank-cards' })
}
export function getBankCardConfig() {
  return request<{
    binding_enabled: boolean
    mode: 'format_only' | 'manual_review'
    bank_verified: false
    consent_version: string
    notice?: string
  }>({ url: '/bank-cards/config' })
}
export function addBankCard(data: { bank_name?: string; card_number: string; holder: string; phone?: string; is_default?: boolean; sensitive_consent: boolean }) {
  return request<BankCardItem>({ url: '/bank-cards', method: 'POST', data })
}
export function setDefaultCard(id: number) {
  return request({ url: `/bank-cards/${id}/default`, method: 'POST' })
}
export function deleteCard(id: number) {
  return request({ url: `/bank-cards/${id}`, method: 'DELETE' })
}
