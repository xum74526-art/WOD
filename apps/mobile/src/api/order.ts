import { request, requestEnvelope } from './request'
import { makeIdempotencyKey } from '@/utils/idempotency'

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
  version?: number
}

interface CanonicalOrder {
  id: number
  order_no: string
  product_id: number
  quantity: number
  duration_hours: number
  amount: string | number
  status: string
  created_at?: string
  version: number
  snapshot?: Record<string, any>
}

function toOrder(row: CanonicalOrder): OrderItem {
  return {
    id: row.id,
    order_no: row.order_no,
    product_id: row.product_id,
    quantity: row.quantity,
    cycle_days: Math.max(1, Math.ceil(Number(row.duration_hours || 24) / 24)),
    amount: Number(row.amount || 0),
    purchase_type: 'usage',
    status: row.status,
    created_at: row.created_at,
    product_name: row.snapshot?.product_name || row.snapshot?.server_name,
    gpu_model: row.snapshot?.gpu_model,
    version: row.version,
  }
}

export function createOrder(product_id: number, cycle_days: number, purchase_type: 'usage' | 'holding' = 'usage', quantity = 1, client_request_id?: string) {
  if (purchase_type !== 'usage') {
    return Promise.reject(new Error('统一后端目前只支持按使用时长租赁'))
  }
  if (quantity !== 1) {
    return Promise.reject(new Error('统一后端的直接租赁订单目前每单只支持 1 台设备'))
  }
  return request<any[]>({ url: '/account/ssh-keys', silent: true }).then(keys => {
    const key = keys.find(item => item.status !== 'revoked')
    if (!key) throw new Error('请先在账户中添加 SSH 公钥，再提交租赁订单')
    return request<{ order: CanonicalOrder }>({
      url: '/account/orders/direct',
      method: 'POST',
      headers: { 'Idempotency-Key': makeIdempotencyKey('direct-order', client_request_id) },
      data: {
        product_id,
        ssh_key_id: key.id,
        duration_hours: Math.max(1, Math.round(cycle_days * 24)),
      },
    })
  }).then(result => toOrder(result.order))
}

export function getOrders(status_filter?: string) {
  return requestEnvelope<CanonicalOrder[]>({
    url: '/account/orders',
    data: status_filter ? { status: status_filter, page_size: 100 } : { page_size: 100 },
  }).then(({ data }) => data.map(toOrder))
}

export function getOrder(id: number) {
  return request<CanonicalOrder>({ url: `/account/orders/${id}` }).then(toOrder)
}

export function renewOrder(id: number, cycle_days: number) {
  return request<any[]>({ url: '/account/leases' }).then(leases => {
    const lease = leases.find(item => item.order_id === id)
    if (!lease) throw new Error('未找到该订单对应的租约')
    return request<any>({
      url: `/account/leases/${lease.id}/renew`,
      method: 'POST',
      headers: { 'Idempotency-Key': makeIdempotencyKey(`renew-${lease.id}`) },
      data: { version: lease.version, duration_hours: Math.max(1, Math.round(cycle_days * 24)) },
    }).then(() => getOrder(id))
  })
}

export function cancelOrder(id: number) {
  return request<CanonicalOrder>({ url: `/account/orders/${id}`, silent: true }).then(order =>
    request<CanonicalOrder>({
      url: `/account/orders/${id}/cancel`,
      method: 'POST',
      data: { version: order.version, reason: '用户从移动端取消订单' },
    }),
  ).then(toOrder)
}
