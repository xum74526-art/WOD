import { request } from './request'

export interface Product {
  id: number
  name: string
  gpu_model: string
  memory: string
  cuda?: string
  price: number
  cycle?: number[]
  desc?: string
  supplier_id?: number
  supplier_name?: string
  status: string
  daily_revenue?: number | null
  revenue_estimate_available?: boolean
  purchasable?: boolean
  purchase_unavailable_reason?: string | null
  stock?: number
  reported_stock?: number
  market_source?: 'wod' | 'vast' | 'autodl'
  market_source_status?: 'live' | 'delayed' | 'stale' | 'unavailable' | 'pending'
  is_market_current?: boolean
  stability?: number | null
  tags?: string[]
  image_url?: string
  region_code?: string
  region_name?: string
  city?: string
  source_price?: number
  price_updated_at?: string
  created_at?: string
}

export interface ProductQuery {
  keyword?: string
  memory?: string
  sort?: string
  region?: string
  category?: string
  min_price?: number
  max_price?: number
  page?: number
  page_size?: number
}

export interface ProductPage { items: Product[]; total: number; page: number; page_size: number }

export function getProducts(params?: ProductQuery) {
  return request<ProductPage>({ url: '/products', data: params || {} })
}

export function getProduct(id: number) {
  return request<Product>({ url: `/products/${id}` })
}

export function getPriceTrend(id: number) {
  return request<{ date: string; price: number }[]>({ url: `/products/${id}/price-trend` })
}

export function getQuoteOverview() {
  return request<{ ranking: { gpu_model: string; name: string; min_price: number; avg_price: number; total_stock: number; supplier_count: number; change: number }[] }>({ url: '/products/quote/overview' })
}
