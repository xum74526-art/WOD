import { request } from './request'

export interface OrderItem {
  id: number
  order_no: string
  client_request_id?: string
  product_id: number
  quantity: number
  cycle_days: number
  amount: number
  purchase_type?: string
  ssh_info?: string
  status: string
  start_at?: string
  end_at?: string
  created_at?: string
  product_name?: string
  gpu_model?: string
  asset_id?: number
  market_source?: 'wod' | 'vast' | 'autodl'
  fulfillment_status?: string
  accumulated_revenue?: number
  historical_test_revenue?: number
  revenue_settlement_enabled?: boolean
  remaining_days?: number
}

export function createOrder(product_id: number, cycle_days: number, purchase_type: 'usage' | 'holding' = 'usage', quantity = 1, client_request_id?: string) {
  return request<OrderItem>({ url: '/orders', method: 'POST', data: { product_id, cycle_days, purchase_type, quantity, client_request_id } })
}

export function getOrders(status_filter?: string) {
  return request<OrderItem[]>({ url: '/orders', data: status_filter ? { status_filter } : {} })
}

export function getOrder(id: number) {
  return request<OrderItem>({ url: `/orders/${id}` })
}

export function renewOrder(id: number, cycle_days: number) {
  return request<OrderItem>({ url: `/orders/${id}/renew`, method: 'POST', data: { product_id: 0, cycle_days } })
}

export function cancelOrder(id: number) {
  return request<OrderItem>({ url: `/orders/${id}/cancel`, method: 'POST' })
}
