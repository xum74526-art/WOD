import { request } from './request'

export interface BuyRequestItem {
  id: number
  user_id: number
  buyer_name: string
  request_type: 'online' | 'offline'
  gpu_model: string
  gpu_variant?: string
  quantity: number
  gpu_hours?: number
  max_unit_price?: number
  budget?: number
  currency: string
  region?: string
  billing_mode?: string
  requirements: Record<string, any>
  contact?: string
  phone?: string
  status: string
  quote_count: number
  expires_at?: string
  created_at?: string
  updated_at?: string
  legacy: boolean
}

export interface BuyRequestQuote {
  id: number
  buy_request_id: number
  supplier_id: number
  supplier_name: string
  supplier_rating?: number
  unit_price?: number
  total_price: number
  currency: string
  available_at?: string
  message?: string
  status: string
  expires_at?: string
  created_at?: string
}

export interface BuyRequestPayload {
  request_type: 'online' | 'offline'
  gpu_model: string
  gpu_variant?: string
  quantity: number
  gpu_hours?: number
  max_unit_price?: number
  budget?: number
  currency: string
  region?: string
  billing_mode?: string
  requirements?: Record<string, any>
  contact?: string
  phone?: string
  expires_in_hours: number
}

export function getBuyRequestSummary() {
  return request<{ active: number; new_quotes: number; pending_confirmation: number }>({ url: '/buy-requests/summary' })
}

export function getBuyRequests(requestType: 'online' | 'offline', view: 'buyer' | 'seller' = 'buyer') {
  return request<BuyRequestItem[]>({ url: '/buy-requests', data: { request_type: requestType, view } })
}

export function createBuyRequest(data: BuyRequestPayload) {
  return request<BuyRequestItem>({ url: '/buy-requests', method: 'POST', data })
}

export function getBuyRequestDetail(id: number) {
  return request<{ request: BuyRequestItem; quotes: BuyRequestQuote[] }>({ url: `/buy-requests/${id}` })
}

export function selectBuyRequestQuote(requestId: number, quoteId: number) {
  return request<{ request_id: number; quote_id: number; status: string }>({ url: `/buy-requests/${requestId}/quotes/${quoteId}/select`, method: 'POST' })
}
