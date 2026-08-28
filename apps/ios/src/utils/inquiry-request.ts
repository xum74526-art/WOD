export type InquiryRequestPrefill = {
  product_id: number
  supplier_id?: number | null
  seller_name?: string
  source?: string
  gpu_model: string
  gpu_variant?: string
  quantity: number
  gpu_hours: number
  region?: string
  product_name?: string
  created_at: number
}

const INQUIRY_PREFILL_KEY = 'wod-inquiry-request-prefill-v1'
const INQUIRY_PREFILL_TTL_MS = 24 * 60 * 60 * 1000

export function saveInquiryRequestPrefill(value: Omit<InquiryRequestPrefill, 'created_at'>) {
  uni.setStorageSync(INQUIRY_PREFILL_KEY, { ...value, created_at: Date.now() })
}

export function readInquiryRequestPrefill(): InquiryRequestPrefill | null {
  const value = uni.getStorageSync(INQUIRY_PREFILL_KEY) as InquiryRequestPrefill | null
  if (!value || !Number.isFinite(Number(value.product_id)) || !String(value.gpu_model || '').trim()) return null
  if (!Number.isFinite(Number(value.created_at)) || Date.now() - Number(value.created_at) > INQUIRY_PREFILL_TTL_MS) {
    clearInquiryRequestPrefill()
    return null
  }
  return value
}

export function hasInquiryRequestPrefill() {
  return readInquiryRequestPrefill() !== null
}

export function clearInquiryRequestPrefill() {
  uni.removeStorageSync(INQUIRY_PREFILL_KEY)
}
