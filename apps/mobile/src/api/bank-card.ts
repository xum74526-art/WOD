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
  reject_reason?: string | null
  created_at?: string | null
  reviewed_at?: string | null
}

export function getBankCards() {
  return request<{ bank_accounts: BankCardItem[] }>({ url: '/account/bank-accounts' })
    .then(result => result.bank_accounts || [])
}
export function getBankCardConfig() {
  return request<Record<string, { available: boolean; reason?: string }>>({
    url: '/account/modules',
  }).then(result => {
    const module = result.bank_accounts
    return {
      binding_enabled: Boolean(module?.available),
      mode: 'manual_review' as const,
      bank_verified: false as const,
      notice: module?.reason || '银行卡服务尚未配置',
    }
  }) as Promise<{
    binding_enabled: boolean
    mode: 'format_only' | 'manual_review'
    bank_verified: false
    notice?: string
  }>
}
export function addBankCard(data: { bank_name?: string; card_number: string; holder: string; phone?: string; is_default?: boolean }) {
  return request<BankCardItem>({
    url: '/account/bank-accounts/bind',
    method: 'POST',
    data: {
      bank_name: data.bank_name,
      account_number: data.card_number,
      account_name: data.holder,
    },
  })
}
export function setDefaultCard(id: number) {
  return Promise.reject(new Error('统一后端不支持客户端切换默认收款账户'))
}
export function deleteCard(id: number) {
  return request({ url: `/account/bank-accounts/${id}`, method: 'DELETE' })
}
