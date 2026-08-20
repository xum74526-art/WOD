import { request, requestEnvelope } from './request'
import type { Product } from './gpu'

export interface SupplierInfo {
  id: number
  company_name: string
  contact: string
  phone: string
  region?: string
  desc?: string
  status: string
  rating: number
  order_count: number
}

export interface SupplierDeviceItem {
  id: number
  name: string
  gpu_model: string
  memory: string
  price: number
  stock: number
  region: string
  city: string
  order_count: number
  status: 'online' | 'offline' | string
  list_status: 'on' | 'off' | string
  image_url: string | null
  version?: number
}

interface CanonicalResource {
  id: number
  name: string
  gpu_model: string
  memory: string
  gpu_memory_gb: number
  price: { amount: string; currency: string; unit: string }
  total_quantity: number
  available_quantity: number
  region: string
  status: string
  description?: string
  image_url?: string | null
  version: number
  server?: { status?: string } | null
}

function resourceToProduct(row: CanonicalResource): Product {
  return {
    id: row.id,
    name: row.name,
    gpu_model: row.gpu_model,
    memory: row.memory,
    price: Number(row.price?.amount || 0),
    desc: row.description,
    status: row.status,
    stock: row.available_quantity,
    reported_stock: row.total_quantity,
    region_name: row.region,
    purchasable: row.status === 'published' && row.server?.status === 'online',
    image_url: row.image_url || undefined,
  }
}

function resourceToDevice(row: CanonicalResource): SupplierDeviceItem {
  return {
    id: row.id,
    name: row.name,
    gpu_model: row.gpu_model,
    memory: row.memory,
    price: Number(row.price?.amount || 0),
    stock: row.available_quantity,
    region: row.region,
    city: row.region,
    order_count: 0,
    status: row.server?.status || 'offline',
    list_status: row.status === 'published' ? 'on' : 'off',
    image_url: row.image_url || null,
    version: row.version,
  }
}

export function registerSupplier(data: { company_name: string; contact: string; phone: string; region?: string; desc?: string }) {
  return request<any>({
    url: '/supplier/application',
    method: 'POST',
    data: {
      company_name: data.company_name,
      contact_name: data.contact,
      contact_phone: data.phone,
      region: data.region,
      description: data.desc,
    },
  }).then(result => ({
    id: result.id,
    company_name: data.company_name,
    contact: data.contact,
    phone: data.phone,
    region: data.region,
    desc: data.desc,
    status: result.status,
    rating: 0,
    order_count: 0,
  }))
}
export function getMySupplier() {
  return request<any>({ url: '/supplier/application' }).then(result => {
    if (!result.id) return { status: result.status }
    return {
      id: result.id,
      company_name: result.company_name,
      contact: result.contact_name,
      phone: result.contact_phone,
      region: result.region,
      desc: result.description,
      status: result.status,
      rating: 0,
      order_count: 0,
    } as SupplierInfo
  })
}
export function getMyProducts() {
  return requestEnvelope<CanonicalResource[]>({
    url: '/supplier/resources', data: { page_size: 100 },
  }).then(({ data }) => data.map(resourceToProduct))
}
export function getSupplierDevices(status_filter: 'on' | 'off' | 'all' = 'all') {
  return requestEnvelope<CanonicalResource[]>({
    url: '/supplier/resources', data: { page_size: 100 },
  }).then(({ data }) => data.map(resourceToDevice).filter(item => status_filter === 'all' || item.list_status === status_filter))
}
export function getStore(id: number) {
  void id
  return Promise.reject<{ supplier: SupplierInfo; products: Product[] }>(new Error('公开商家主页尚未纳入统一后端'))
}
export function getDashboard() {
  return Promise.all([
    request<any>({ url: '/supplier/application' }),
    request<any>({ url: '/supplier/summary' }),
    request<any>({ url: '/supplier/revenue' }),
    getSupplierDevices('all'),
    requestEnvelope<any[]>({ url: '/supplier/orders', data: { page_size: 100 } }),
  ]).then(([application, summary, revenue, devices, orders]) => {
    const balance = revenue.balances?.[0] || {}
    return {
      company_name: application.company_name || '',
      today_revenue: 0,
      total_revenue: Number(revenue.summary?.paid || 0),
      product_count: devices.length,
      total_stock: devices.reduce((sum, item) => sum + item.stock, 0),
      pending_orders: orders.data.filter(item => !['completed', 'cancelled'].includes(item.status)).length,
      completed_orders: orders.data.filter(item => item.status === 'completed').length,
      rating: 0,
      order_count: orders.data.length,
      devices,
      trend: [],
      available: Number(balance.available || 0),
      has_data: summary.has_data,
    }
  }) as Promise<{
    company_name: string
    today_revenue: number
    total_revenue: number
    product_count: number
    total_stock: number
    pending_orders: number
    completed_orders: number
    rating: number
    order_count: number
    devices: { id: number; name: string; gpu_model: string; stock: number; price: number; region: string; status: string }[]
    trend: { date: string; amount: number }[]
  }>
}

export function getSupplierWallet() {
  return request<any>({ url: '/supplier/revenue' }).then(result => {
    const balance = result.balances?.[0] || {}
    return {
      total_revenue: Number(result.summary?.paid || 0),
      pending_amount: Number(result.summary?.requested || 0),
      withdrawn: Number(result.summary?.paid || 0),
      available: Number(balance.available || 0),
      today_revenue: 0,
      payment_service_enabled: true,
    }
  }) as Promise<{
    total_revenue: number
    pending_amount: number
    withdrawn: number
    available: number
    today_revenue: number
    payment_service_enabled: boolean
  }>
}

export function getRevenueDetail() {
  return request<any[]>({ url: '/supplier/settlements' }).then(rows => rows.map(row => ({
    order_no: row.withdrawal_no,
    product_name: '商家结算',
    buyer_name: '-',
    amount: Number(row.amount || 0),
    service_fee: 0,
    net_income: Number(row.amount || 0),
    status: row.status,
    purchase_type: 'settlement',
    created_at: row.created_at,
  }))) as Promise<{
    order_no: string
    product_name: string
    buyer_name: string
    amount: number
    service_fee: number
    net_income: number
    status: string
    purchase_type: string | null
    created_at: string | null
  }[]>
}

export interface SupplierRebate {
  month_sales: number
  month_rebated: number
  current_rate: number
  est_total_rebate: number
  next_tier_hint: string
  monthly_cap: number
  service_fee_rate: number
  rewards_enabled: boolean
  reward_mode: 'disabled' | 'test_card_hours' | 'live'
}

export function getSupplierRebate() {
  return request<any>({ url: '/supplier/rebates' }).then(result => ({
    month_sales: 0,
    month_rebated: 0,
    current_rate: 0,
    est_total_rebate: 0,
    next_tier_hint: result.module?.reason || '商家奖励尚未配置',
    monthly_cap: 0,
    service_fee_rate: 0,
    rewards_enabled: Boolean(result.module?.available),
    reward_mode: result.module?.available ? 'live' : 'disabled',
  } as SupplierRebate))
}

export function setSupplierResourceListed(resource: SupplierDeviceItem, listed: boolean) {
  const action = listed
    ? request<CanonicalResource>({
        url: `/supplier/resources/${resource.id}/publish`,
        method: 'POST',
        data: { version: resource.version },
      })
    : request<CanonicalResource>({
        url: `/supplier/resources/${resource.id}/unpublish`,
        method: 'POST',
        data: { version: resource.version },
      })
  return action.then(resourceToDevice)
}

export function updateSupplierResource(resource: SupplierDeviceItem, data: { price: number; stock: number }) {
  if (data.stock !== 1) return Promise.reject<SupplierDeviceItem>(new Error('统一后端的独立服务器资源库存固定为 1'))
  return request<CanonicalResource>({
    url: `/supplier/resources/${resource.id}`,
    method: 'PATCH',
    data: { version: resource.version, price_amount: data.price, total_quantity: 1 },
  }).then(resourceToDevice)
}

export function createSupplierResource(data: {
  name: string
  gpu_model: string
  memory: string
  price: number
  region: string
  image_url?: string
  description: string
}) {
  const memoryMatch = data.memory.match(/\d+/)
  return request<CanonicalResource>({
    url: '/supplier/resources',
    method: 'POST',
    data: {
      name: data.name,
      gpu_model: data.gpu_model,
      gpu_memory_gb: Number(memoryMatch?.[0] || 1),
      region: data.region,
      image_url: data.image_url || null,
      description: data.description,
      price_amount: data.price,
      price_currency: 'CNY',
      price_unit: 'server_hour',
      total_quantity: 1,
      public_host: '127.0.0.1',
      ssh_port: 22,
      ssh_username: 'kai',
      agent_mode: 'mtls',
    },
  }).then(resourceToDevice)
}
