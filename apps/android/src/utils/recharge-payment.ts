export type RechargeUiState =
  | 'pending'
  | 'processing'
  | 'success'
  | 'refund_pending'
  | 'refund_unknown'
  | 'refunded'
  | 'failed'
  | 'expired'
  | 'canceled'

export interface RechargeTimingSource {
  status?: string | null
  credited_at?: string | null
  expires_at?: string | null
  server_time?: string | null
  created_at?: string | null
  remaining_seconds?: number | null
  can_query?: boolean | null
  can_cancel?: boolean | null
  provider?: string | null
}

export interface RechargeRefundRequestSource {
  status?: string | null
}

export interface StoredRechargeSession {
  version: 1
  orderNo: string
  checkoutUrl: string
  fallbackExpiresAtMs: number | null
  successNotified: boolean
}

export type RechargePaymentChannel = 'alipay' | 'wxpay'

export interface RechargeRestartSource extends RechargeTimingSource {
  amount_cny?: number | string | null
  channel?: string | null
}

export interface RechargePrefill {
  amount: string
  paymentType: RechargePaymentChannel | null
}

export interface RechargeHistoryPresentation {
  state: RechargeUiState
  labelKey: string
  tone: 'pending' | 'reviewing' | 'success' | 'danger'
}

export const DEFAULT_RECHARGE_TTL_SECONDS = 5 * 60
export const MINIMUM_RECHARGE_CNY = 10
export const MINIMUM_WITHDRAW_CARD_HOURS = 10

function configuredMinimum(value: unknown, floor: number): number {
  const amount = Number(value)
  return Number.isFinite(amount) ? Math.max(floor, amount) : floor
}

export function effectiveRechargeMinimum(value: unknown): number {
  return configuredMinimum(value, MINIMUM_RECHARGE_CNY)
}

export function effectiveWithdrawalMinimum(value: unknown): number {
  return configuredMinimum(value, MINIMUM_WITHDRAW_CARD_HOURS)
}

/**
 * The API currently serializes UTC datetimes without a suffix. Treat those
 * values as UTC while still accepting future ISO values with an explicit
 * offset. This avoids a device timezone changing a five-minute checkout into
 * an eight-hour checkout.
 */
export function parseBackendTimestamp(value?: string | null): number | null {
  const source = String(value || '').trim()
  if (!source) return null
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(source) ? source : `${source}Z`
  const parsed = Date.parse(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Return the remaining duration instead of an absolute client timestamp.
 * server_time/remaining_seconds are authoritative and make the countdown
 * robust when the phone clock is wrong.
 */
export function paymentRemainingMs(
  order: RechargeTimingSource,
  clientNowMs = Date.now(),
  fallbackExpiresAtMs: number | null = null,
): number | null {
  const remainingSeconds = Number(order.remaining_seconds)
  if (order.remaining_seconds != null && Number.isFinite(remainingSeconds) && remainingSeconds >= 0) {
    return Math.max(0, Math.ceil(remainingSeconds * 1000))
  }

  const expiresAt = parseBackendTimestamp(order.expires_at)
  if (expiresAt !== null) {
    const serverNow = parseBackendTimestamp(order.server_time)
    return Math.max(0, expiresAt - (serverNow ?? clientNowMs))
  }

  const createdAt = parseBackendTimestamp(order.created_at)
  if (createdAt !== null) {
    return Math.max(0, createdAt + DEFAULT_RECHARGE_TTL_SECONDS * 1000 - clientNowMs)
  }

  if (fallbackExpiresAtMs !== null && Number.isFinite(fallbackExpiresAtMs)) {
    return Math.max(0, fallbackExpiresAtMs - clientNowMs)
  }
  return null
}

export function rechargeUiState(
  order: RechargeTimingSource,
  remainingMs: number | null,
): RechargeUiState {
  const status = String(order.status || '').trim().toLowerCase()
  if (status === 'refund_pending') return 'refund_pending'
  if (status === 'refund_unknown') return 'refund_unknown'
  if (status === 'refunded') return 'refunded'
  if (order.credited_at) return 'success'
  if (status === 'paid' || status === 'review' || status === 'late_paid_review') return 'processing'
  if (status === 'failed') return 'failed'
  if (status === 'expired') return 'expired'
  if (status === 'canceled' || status === 'cancelled') return 'canceled'
  if (status === 'pending' && remainingMs !== null && remainingMs <= 0) return 'expired'
  return 'pending'
}

export function rechargeHistoryPresentation(order: RechargeTimingSource): RechargeHistoryPresentation {
  const state = rechargeUiState(order, null)
  const status = String(order.status || '').trim().toLowerCase()
  const labelKey = status === 'review' || status === 'late_paid_review'
    ? 'rechargeReviewing'
    : {
      pending: 'statusPendingPayment',
      processing: 'statusProcessing',
      success: 'statusCompleted',
      refund_pending: 'rechargeRefundPending',
      refund_unknown: 'rechargeRefundUnknown',
      refunded: 'rechargeRefunded',
      failed: 'statusFailed',
      expired: 'statusExpired',
      canceled: 'statusCanceled',
    }[state]
  const tone = state === 'success'
    ? 'success'
    : state === 'pending'
      ? 'pending'
      : state === 'processing' || state === 'refund_pending'
        ? 'reviewing'
        : 'danger'
  return { state, labelKey, tone }
}

export function rechargeCanRequestRefund(order: RechargeTimingSource): boolean {
  if (String(order.provider || '').trim().toLowerCase() !== 'qixiangpay') return false
  const status = String(order.status || '').trim().toLowerCase()
  if (status === 'review' || status === 'late_paid_review') return true
  return status === 'paid' && Boolean(order.credited_at)
}

export function rechargeRefundRequestPresentation(request: RechargeRefundRequestSource): {
  labelKey: string
  tone: 'pending' | 'reviewing' | 'success' | 'danger'
} {
  const status = String(request.status || '').trim().toLowerCase()
  const labelKey = {
    pending_review: 'refundRequestPendingReview',
    approved: 'refundRequestApproved',
    processing: 'refundRequestProcessing',
    rejected: 'refundRequestRejected',
    canceled: 'refundRequestCanceled',
    succeeded: 'refundRequestSucceeded',
    failed: 'refundRequestFailed',
  }[status] || 'notAvailableShort'
  const tone = status === 'succeeded'
    ? 'success'
    : status === 'rejected' || status === 'canceled' || status === 'failed'
      ? 'danger'
      : status === 'pending_review'
        ? 'pending'
        : 'reviewing'
  return { labelKey, tone }
}

export function rechargeCanQuery(order: RechargeTimingSource): boolean {
  if (order.can_query !== true) return false
  const state = rechargeUiState(order, null)
  return state !== 'success'
    && state !== 'refund_pending'
    && state !== 'refund_unknown'
    && state !== 'refunded'
    && state !== 'canceled'
}

export function rechargeCanCancel(order: RechargeTimingSource): boolean {
  if (order.can_cancel !== true || order.credited_at) return false
  const status = String(order.status || '').trim().toLowerCase()
  return status !== 'paid'
    && status !== 'review'
    && status !== 'late_paid_review'
    && status !== 'refund_pending'
    && status !== 'refund_unknown'
    && status !== 'refunded'
    && status !== 'canceled'
    && status !== 'cancelled'
}

export function rechargeCanRestart(order: RechargeTimingSource, remainingMs: number | null): boolean {
  const state = rechargeUiState(order, remainingMs)
  return state === 'failed' || state === 'expired' || state === 'canceled'
}

function normalizeRechargeAmount(value: unknown): string | null {
  const source = String(value ?? '').trim()
  if (!/^\d+(?:\.\d{1,2})?$/.test(source)) return null
  const amount = Number(source)
  return Number.isFinite(amount) && amount >= MINIMUM_RECHARGE_CNY ? String(amount) : null
}

function normalizeRechargeChannel(value: unknown): RechargePaymentChannel | null {
  const channel = String(value ?? '').trim().toLowerCase()
  return channel === 'alipay' || channel === 'wxpay' ? channel : null
}

/**
 * Build the only supported history-to-wallet restart route. The old order is
 * never changed here: only terminal failed/expired/canceled orders can offer
 * a fresh checkout, while the wallet page still enforces any active session.
 */
export function createRechargeRestartRoute(order: RechargeRestartSource): string | null {
  if (!rechargeCanRestart(order, null)) return null
  const amount = normalizeRechargeAmount(order.amount_cny)
  if (!amount) return null
  const channel = normalizeRechargeChannel(order.channel)
  const params = [`rechargeAmount=${encodeURIComponent(amount)}`]
  if (channel) params.push(`rechargeChannel=${encodeURIComponent(channel)}`)
  return `/pages/wallet/index?${params.join('&')}`
}

/** Parse and validate the shared restart query before it reaches form state. */
export function readRechargePrefillQuery(query: Record<string, unknown> | undefined): RechargePrefill | null {
  if (!query) return null
  const amount = normalizeRechargeAmount(query.rechargeAmount)
  if (!amount) return null
  return {
    amount,
    paymentType: normalizeRechargeChannel(query.rechargeChannel),
  }
}

export function rechargeClearsCurrentSession(order: RechargeTimingSource): boolean {
  const status = String(order.status || '').trim().toLowerCase()
  return status === 'canceled' || status === 'cancelled'
}

export function formatPaymentCountdown(remainingMs: number | null): string {
  if (remainingMs === null) return '--:--'
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function readStoredRechargeSession(value: unknown): StoredRechargeSession | null {
  // Backward compatibility with the original implementation, which stored
  // only the order number.
  if (typeof value === 'string' && value.trim()) {
    return {
      version: 1,
      orderNo: value.trim(),
      checkoutUrl: '',
      fallbackExpiresAtMs: null,
      successNotified: false,
    }
  }
  if (!value || typeof value !== 'object') return null
  const raw = value as Partial<StoredRechargeSession>
  const orderNo = String(raw.orderNo || '').trim()
  if (!orderNo) return null
  return {
    version: 1,
    orderNo,
    checkoutUrl: String(raw.checkoutUrl || '').trim(),
    fallbackExpiresAtMs: raw.fallbackExpiresAtMs != null && Number.isFinite(Number(raw.fallbackExpiresAtMs))
      ? Number(raw.fallbackExpiresAtMs)
      : null,
    successNotified: raw.successNotified === true,
  }
}
