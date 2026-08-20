import { request } from './request'

export interface CouponItem { id: number; name: string; amount: number; min_amount: number; status: string; expires_at?: string }
export function getCoupons(status?: string) {
  return request<{ coupons: CouponItem[] }>({ url: '/account/coupons', data: status ? { status } : {} })
    .then(result => result.coupons || [])
}
export function redeemCoupon(code: string) {
  return request<CouponItem>({ url: '/account/coupons/redeem', method: 'POST', data: { code } })
}
