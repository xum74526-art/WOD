export type RechargeUiState = 'pending' | 'processing' | 'success' | 'failed' | 'expired'

export interface RechargeTimingSource {
  status?: string | null
  credited_at?: string | null
  expires_at?: string | null
  server_time?: string | null
  created_at?: string | null
  remaining_seconds?: number | null
}

export interface StoredRechargeSession {
  version: 1
  orderNo: string
  checkoutUrl: string
  fallbackExpiresAtMs: number | null
  successNotified: boolean
}

export const DEFAULT_RECHARGE_TTL_SECONDS = 5 * 60

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
  if (order.credited_at) return 'success'
  if (status === 'paid' || status === 'review' || status === 'late_paid_review') return 'processing'
  if (status === 'failed') return 'failed'
  if (status === 'expired') return 'expired'
  if (status === 'pending' && remainingMs !== null && remainingMs <= 0) return 'expired'
  return 'pending'
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
