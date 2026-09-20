import { request } from './request'

export type CouponStatus = 'available' | 'used' | 'expired'

export interface CouponItem {
  id: number
  name: string
  amount: number
  min_amount: number
  status: CouponStatus
  expires_at?: string | null
  created_at?: string | null
}

export function getCoupons(status: CouponStatus) {
  return request<CouponItem[]>({
    url: '/coupons',
    data: { status },
    silent: true,
  })
}
