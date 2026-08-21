import { request } from './request'

export interface CouponItem { id: number; name: string; amount: number; min_amount: number; status: string; expires_at?: string }
export function getCoupons(status?: string) { return request<CouponItem[]>({ url: '/coupons', data: status ? { status } : {} }) }
export function redeemCoupon(code: string) { return request<CouponItem>({ url: '/coupons/redeem', method: 'POST', data: { code } }) }
