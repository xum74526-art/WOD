import { request } from './request'

export interface OrderItem {
  id: number
  order_no: string
  client_request_id?: string
  product_id: number
  quantity: number
  cycle_days?: number | null
  duration_hours?: number | null
  purchase_hours?: number | null
  purchase_unit?: 'hour' | 'day' | string | null
  billing_unit?: 'GPU_HOUR' | string | null
  amount: number
  amount_card_hours?: number
  purchase_type?: string
  ssh_info?: string
  status: string
  start_at?: string
  end_at?: string
  created_at?: string
  product_name?: string
  gpu_model?: string
  asset_id?: number
  market_source?: 'wod' | 'kai' | 'vast' | 'autodl'
  fulfillment_status?: string
  accumulated_revenue?: number
  historical_test_revenue?: number
  revenue_settlement_enabled?: boolean
  remaining_days?: number
  remaining_hours?: number
}

export type PurchaseType = 'usage' | 'holding'

export function createOrder(
  product_id: number,
  hours: number,
  purchase_type: PurchaseType,
  quantity = 1,
  client_request_id?: string,
) {
  return request<OrderItem>({
    url: '/orders',
    method: 'POST',
    data: { product_id, hours, purchase_type, quantity, client_request_id },
  })
}

export function getOrders(status_filter?: string) {
  return request<OrderItem[]>({ url: '/orders', data: status_filter ? { status_filter } : {} })
}

export function getOrder(id: number) {
  return request<OrderItem>({ url: `/orders/${id}` })
}

export function renewOrder(id: number, hours: number, client_request_id: string) {
  return request<OrderItem>({
    url: `/orders/${id}/renew`,
    method: 'POST',
    data: { hours, client_request_id },
  })
}

export function cancelOrder(id: number) {
  return request<OrderItem>({ url: `/orders/${id}/cancel`, method: 'POST' })
}
