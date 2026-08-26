import { request } from './request'
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
}

export interface SupplierDeviceCreateInput {
  name: string
  gpu_model: string
  memory: string
  cuda?: string | null
  price: number
  stock: number
  desc?: string | null
  image_url?: string | null
  region_code: string
  region_name: string
  city: string
}

export interface SupplierDeviceUpdateInput {
  name?: string
  price?: number
  stock?: number
  status?: 'on' | 'off'
}

export interface SupplierDeviceMutationResult {
  id: number
  name?: string
  status?: 'on' | 'off'
  updated?: boolean
}

export function getMySupplier() {
  return request<SupplierInfo | { status: string }>({ url: '/supplier/mine' })
}
export function getMyProducts() {
  return request<Product[]>({ url: '/supplier/products' })
}
export function getSupplierDevices(status_filter: 'on' | 'off' | 'all' = 'all') {
  return request<SupplierDeviceItem[]>({ url: '/supplier/devices', data: { status_filter } })
}
export function createSupplierDevice(data: SupplierDeviceCreateInput) {
  return request<SupplierDeviceMutationResult>({
    url: '/supplier/devices',
    method: 'POST',
    data,
    silent: true,
  })
}
export function updateSupplierDevice(id: number, data: SupplierDeviceUpdateInput) {
  return request<SupplierDeviceMutationResult>({
    url: `/supplier/devices/${id}`,
    method: 'PUT',
    data,
    silent: true,
  })
}
export function getStore(id: number) {
  return request<{ supplier: SupplierInfo; products: Product[] }>({ url: `/supplier/${id}` })
}
export function getDashboard() {
  return request<{
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
  }>({ url: '/supplier/dashboard' })
}

export function getSupplierWallet() {
  return request<{
    total_revenue: number
    pending_amount: number
    withdrawn: number
    available: number
    today_revenue: number
    payment_service_enabled: boolean
  }>({ url: '/supplier/wallet' })
}

export function getRevenueDetail() {
  return request<{
    order_no: string
    product_name: string
    buyer_name: string
    amount: number
    service_fee: number
    net_income: number
    status: string
    purchase_type: string | null
    created_at: string | null
  }[]>({ url: '/supplier/revenue/detail' })
}

export interface SupplierRebate {
  program_code: 'supplier_sales_rebate'
  policy_version: string
  period_key: string
  month_sales: number
  month_rebated: number
  month_entitled: number
  pending_rebate: number
  current_rate: number
  tiers: { max_month_spent: number | null; rate: number; rate_bps?: number }[]
  monthly_target: number
  est_total_rebate: number
  next_tier_hint: string
  monthly_cap: number
  service_fee_rate: number
  cap_used: number
  cap_remaining: number
  rewards_enabled: boolean
  reward_mode: 'disabled' | 'test_card_hours' | 'live'
}

export function getSupplierRebate() {
  return request<SupplierRebate>({ url: '/supplier/rebate' })
}
