import { request } from './request'

export type CouponStatus = 'available' | 'used' | 'expired'

export interface CouponItem {
  id: number
  campaign_id?: number | null
  product_id?: number | null
  name: string
  amount: number
  min_amount: number
  status: CouponStatus
  expires_at?: string | null
  redeemed_at?: string | null
  used_at?: string | null
  used_order_id?: number | null
  created_at?: string | null
}

export function redeemCoupon(code: string) {
  return request<CouponItem>({
    url: '/coupons/redeem',
    method: 'POST',
    data: { code },
  })
}

export function getAvailableCoupons(amount: number, product_id: number, purchase_type: 'usage' | 'holding' = 'usage') {
  return request<CouponItem[]>({
    url: '/coupons/available',
    data: { amount, product_id, purchase_type },
    silent: true,
  })
}

export function getCoupons(status: CouponStatus) {
  return request<CouponItem[]>({
    url: '/coupons',
    data: { status },
    silent: true,
  })
}
