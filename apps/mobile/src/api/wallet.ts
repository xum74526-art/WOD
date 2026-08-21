import { request } from './request'

export interface WalletInfo {
  balance: number
  frozen: number
  withdrawable_balance?: number
  withdraw_frozen?: number
  total_income: number
  has_bank_card?: boolean
  payment_service_enabled?: boolean
  recharge_service_enabled?: boolean
  withdraw_service_enabled?: boolean
  payment_config?: PaymentConfig
  revenue_settlement_enabled?: boolean
  historical_test_revenue?: number
  reward_service_enabled?: boolean
  reward_mode?: 'disabled' | 'test_card_hours' | 'live'
  historical_test_rewards?: number
}

export interface LedgerItem {
  id: number
  type: string
  direction: string
  amount: number
  balance_after: number
  remark?: string
  ref_order_id?: number
  ref_payment_order_id?: number
  created_at?: string
}

export interface PaymentConfig {
  provider: 'mapay' | 'qixiangpay'
  enabled: boolean
  pid_configured: boolean
  sign_version: string
  card_hour_rmb_rate: number
  min_amount_cny: number
  max_amount_cny: number
  checkout_mode: 'hosted_page'
  checkout_ttl_seconds?: number
  payment_types?: RechargePaymentType[]
}

export interface RechargePaymentOrder {
  order_no: string
  provider: 'mapay' | 'qixiangpay'
  provider_trade_no?: string | null
  channel?: string | null
  status: 'pending' | 'paid' | 'expired' | 'failed' | 'review' | 'late_paid_review'
  amount_cny: number
  card_hours: number
  card_hour_rmb_rate: number
  checkout_url?: string | null
  expires_at?: string | null
  server_time?: string | null
  created_at?: string | null
  remaining_seconds?: number | null
  is_expired?: boolean
  can_pay?: boolean
  can_query?: boolean
  failure_reason?: string | null
  provider_status?: string | null
  paid_at?: string | null
  credited_at?: string | null
}

export type RechargePaymentType = 'alipay' | 'wxpay'

export interface LedgerPage {
  total: number
  page: number
  page_size: number
  items: LedgerItem[]
}

export function getWallet() {
  return request<WalletInfo>({ url: '/wallet' })
}

export function getPaymentConfig() {
  return request<PaymentConfig>({ url: '/payments/qixiangpay/config', silent: true })
}

export function createRechargePayment(amount_cny: number, payment_type: RechargePaymentType) {
  return request<RechargePaymentOrder>({
    url: '/payments/qixiangpay/recharge-orders',
    method: 'POST',
    data: { amount_cny, payment_type },
  })
}

export function getRechargePayment(orderNo: string, silent = true) {
  return request<RechargePaymentOrder>({
    url: `/payments/qixiangpay/orders/${encodeURIComponent(orderNo)}`,
    silent,
  })
}

export function queryRechargePayment(orderNo: string, silent = true) {
  return request<RechargePaymentOrder>({
    url: `/payments/qixiangpay/orders/${encodeURIComponent(orderNo)}/query`,
    method: 'POST',
    silent,
  })
}

export function getLedger(params?: { type_filter?: string; page?: number; page_size?: number }) {
  return request<LedgerPage>({ url: '/wallet/ledger', data: params || {} })
}
