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
  seller_type?: 'kai_self_operated' | 'merchant'
  seller_name?: string
  fulfillment_mode?: 'platform_manual' | 'merchant_manual'
  fulfillment_status?: string
  delivery_due_at?: string | null
  delivered_at?: string | null
  confirmation_due_at?: string | null
  confirmed_at?: string | null
  canceled_at?: string | null
  stock_released_at?: string | null
  disputed_at?: string | null
  dispute_due_at?: string | null
  dispute_reason?: string | null
  dispute_resolution?: 'refund' | 'release' | string | null
  dispute_resolution_note?: string | null
  dispute_resolved_at?: string | null
  can_cancel?: boolean
  can_confirm?: boolean
  can_dispute?: boolean
  can_deliver?: boolean
  can_renew?: boolean
  accumulated_revenue?: number
  historical_test_revenue?: number
  revenue_settlement_enabled?: boolean
  remaining_days?: number
  remaining_hours?: number
}

// The API currently rejects new holding purchases. Historical orders may still
// report purchase_type="holding" through OrderItem, but checkout is usage-only.
export type PurchaseType = 'usage'

export function createOrder(
  product_id: number,
  hours: number,
  purchase_type: PurchaseType,
  quantity = 1,
  client_request_id?: string,
  expected_unit_price_card_hours?: number,
) {
  return request<OrderItem>({
    url: '/orders',
    method: 'POST',
    data: { product_id, hours, purchase_type, quantity, client_request_id, expected_unit_price_card_hours },
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

export function disputeOrder(id: number, reason: string) {
  return request<OrderItem>({
    url: `/orders/${id}/dispute`,
    method: 'POST',
    data: { reason },
  })
}
