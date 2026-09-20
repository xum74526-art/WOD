import { request } from './request'

export interface OfflinePurchaseItem { id: number; device_model: string; quantity: number; budget: number; contact: string; phone: string; remark?: string; status: string; created_at?: string }
export function getOfflinePurchases() { return request<OfflinePurchaseItem[]>({ url: '/offline-purchases' }) }
export function submitOfflinePurchase(data: { device_model: string; quantity: number; budget: number; contact: string; phone: string; remark?: string }) {
  return request<OfflinePurchaseItem>({ url: '/offline-purchases', method: 'POST', data })
}
