import { request, requestEnvelope } from './request'
import { makeIdempotencyKey } from '@/utils/idempotency'

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
  balance_after?: number
  remark?: string
  ref_order_id?: number
  ref_payment_order_id?: number
  created_at?: string
}

export interface PaymentConfig {
  provider: string
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
  provider: string
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

function paymentStatus(value: string): RechargePaymentOrder['status'] {
  if (value === 'succeeded') return 'paid'
  if (value === 'provider_pending' || value === 'created') return 'pending'
  if (value === 'expired') return 'expired'
  return 'failed'
}

function toRecharge(row: any): RechargePaymentOrder {
  return {
    order_no: row.payment_no,
    provider: row.provider,
    status: paymentStatus(row.status),
    amount_cny: Number(row.amount || 0),
    card_hours: Number(row.amount || 0),
    card_hour_rmb_rate: 1,
    checkout_url: row.checkout_url,
    expires_at: row.expires_at,
    created_at: row.created_at,
    can_pay: row.status === 'provider_pending',
    can_query: ['provider_pending', 'created'].includes(row.status),
  }
}

function toPaymentConfig(provider: any): PaymentConfig {
  const enabled = Boolean(provider?.configured)
  return {
    provider: provider?.provider || 'not_configured',
    enabled,
    pid_configured: enabled,
    sign_version: 'provider_managed',
    card_hour_rmb_rate: 1,
    min_amount_cny: 0.01,
    max_amount_cny: 50000,
    checkout_mode: 'hosted_page',
    checkout_ttl_seconds: 900,
    payment_types: enabled ? ['alipay', 'wxpay'] : [],
  }
}

export function getWallet() {
  return request<any>({ url: '/account/wallet' }).then(result => {
    const cny = (result.balances || []).find((item: any) => item.currency === 'CNY') || result.balances?.[0] || {}
    const paymentConfig = toPaymentConfig(result.provider)
    return {
      balance: Number(cny.available || 0),
      frozen: Number(cny.frozen || 0),
      // The canonical wallet currently exposes spendable funds, not a
      // verified earnings sub-ledger. Do not present deposits/test credit as
      // withdrawable while settlement and withdrawals are disabled.
      withdrawable_balance: 0,
      withdraw_frozen: 0,
      total_income: 0,
      payment_service_enabled: paymentConfig.enabled,
      recharge_service_enabled: paymentConfig.enabled,
      withdraw_service_enabled: false,
      payment_config: paymentConfig,
      revenue_settlement_enabled: false,
      reward_service_enabled: false,
      reward_mode: 'disabled',
    } as WalletInfo
  })
}

export function getPaymentConfig() {
  return request<any>({ url: '/account/integrations', silent: true })
    .then(result => toPaymentConfig(result.payment))
}

export function createRechargePayment(amount_cny: number, payment_type: RechargePaymentType) {
  return request<any>({
    url: '/payments/intents',
    method: 'POST',
    headers: { 'Idempotency-Key': makeIdempotencyKey('wallet-recharge') },
    data: {
      amount: amount_cny,
      currency: 'CNY',
      purpose: 'wallet_recharge',
      return_path: '/pages/wallet/index',
      payment_channel: payment_type === 'alipay' ? 'alipay_wap' : 'wx_wap',
    },
  }).then(toRecharge)
}

export function getRechargePayment(orderNo: string, silent = true) {
  return request<any>({ url: '/account/wallet', silent }).then(result => {
    const row = (result.payment_intents || []).find((item: any) => item.payment_no === orderNo)
    if (!row) throw new Error('支付单不存在或不在最近记录中')
    return toRecharge(row)
  })
}

export function queryRechargePayment(orderNo: string, silent = true) {
  return request<any>({
    url: `/payments/${encodeURIComponent(orderNo)}/reconcile`,
    method: 'POST',
    silent,
  }).then(toRecharge)
}

export function getLedger(params?: { type_filter?: string; page?: number; page_size?: number }) {
  const page = params?.page || 1
  const pageSize = params?.page_size || 20
  return requestEnvelope<any[], { total?: number }>({
    url: '/account/wallet/ledger',
    data: {
      page,
      page_size: pageSize,
      ...(params?.type_filter ? { type_filter: params.type_filter } : {}),
    },
  }).then(({ data, meta }) => ({
    total: Number(meta.total || 0),
    page,
    page_size: pageSize,
    items: data.map(row => ({
      id: row.id,
      type: row.event_type,
      direction: row.balance_effect === 'increase' ? 'in' : 'out',
      amount: Number(row.amount || 0),
      remark: row.metadata?.note || row.event_type,
      created_at: row.created_at,
    })),
  }))
}
