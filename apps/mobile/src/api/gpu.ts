import { request, requestEnvelope } from './request'

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
  server_online?: boolean
  cpu_cores?: number | null
  ram_gb?: number | null
  disk_gb?: number | null
  bandwidth_mbps?: number | null
  status: string
  daily_revenue?: number | null
  revenue_estimate_available?: boolean
  purchasable?: boolean
  purchase_unavailable_reason?: string | null
  stock?: number
  reported_stock?: number
  market_source?: string
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

interface CanonicalProduct {
  id: number
  supplier_id?: number | null
  name: string
  gpu_model: string
  memory: string
  description?: string | null
  price: { amount: string; currency: string; unit: string }
  available_quantity: number
  total_quantity: number
  source_name?: string | null
  source_observed_at?: string | null
  server_online: boolean
  region?: string | null
  gpu_memory_gb?: number | null
  cpu_cores?: number | null
  ram_gb?: number | null
  disk_gb?: number | null
  bandwidth_mbps?: number | null
  image_url?: string | null
}

function toProduct(row: CanonicalProduct): Product {
  return {
    id: row.id,
    name: row.name,
    gpu_model: row.gpu_model,
    memory: row.memory,
    price: Number(row.price.amount),
    desc: row.description || undefined,
    supplier_id: row.supplier_id || undefined,
    supplier_name: row.source_name || undefined,
    status: 'published',
    stock: row.available_quantity,
    reported_stock: row.total_quantity,
    market_source: row.source_name || 'kai',
    is_market_current: Boolean(row.source_observed_at),
    purchasable: row.server_online && row.available_quantity > 0,
    purchase_unavailable_reason: row.server_online ? null : 'server_offline',
    region_name: row.region || undefined,
    price_updated_at: row.source_observed_at || undefined,
    server_online: row.server_online,
    cpu_cores: row.cpu_cores,
    ram_gb: row.ram_gb,
    disk_gb: row.disk_gb,
    bandwidth_mbps: row.bandwidth_mbps,
    image_url: row.image_url || undefined,
  }
}

function productCategory(model: string): string {
  const value = model.toUpperCase().replace(/\s+/g, '')
  if (/\bH\d/.test(model.toUpperCase())) return 'h_series'
  if (/\bA\d/.test(model.toUpperCase())) return 'a_series'
  if (value.includes('RTX') && !value.includes('PRO') && !value.includes('QUADRO')) return 'consumer'
  if (value.includes('RTXPRO') || value.includes('QUADRO') || value.includes('L40')) return 'professional'
  if (/ASCEND|昇腾|海光|寒武纪|沐曦|壁仞/i.test(model)) return 'domestic'
  if (/VGPU|VIRTUAL/i.test(model)) return 'vgpu'
  return ''
}

function productRegionCode(region?: string): string {
  const value = region || ''
  if (/北京|天津|河北|山西|内蒙古|华北/.test(value)) return 'north_china'
  if (/上海|江苏|浙江|安徽|福建|江西|山东|华东/.test(value)) return 'east_china'
  if (/广东|广西|海南|华南/.test(value)) return 'south_china'
  if (/陕西|甘肃|青海|宁夏|新疆|西北/.test(value)) return 'northwest_china'
  if (/重庆|四川|贵州|云南|西藏|西南/.test(value)) return 'southwest_china'
  return ''
}

export function getProducts(params?: ProductQuery) {
  return requestEnvelope<CanonicalProduct[], { count?: number }>({
    url: '/public/products',
    cacheMs: 30_000,
  }).then(({ data }) => {
    const keyword = params?.keyword?.trim().toLowerCase() || ''
    const filtered = data.map(toProduct).filter((item) => {
      if (keyword && !`${item.name} ${item.gpu_model} ${item.region_name || ''} ${item.supplier_name || ''}`.toLowerCase().includes(keyword)) return false
      if (params?.memory && item.memory.toUpperCase() !== params.memory.toUpperCase()) return false
      if (params?.region && productRegionCode(item.region_name) !== params.region) return false
      if (params?.category && productCategory(item.gpu_model) !== params.category) return false
      if (params?.min_price != null && item.price < params.min_price) return false
      if (params?.max_price != null && item.price > params.max_price) return false
      return true
    })
    if (params?.sort === 'price_asc') filtered.sort((a, b) => a.price - b.price)
    if (params?.sort === 'price_desc') filtered.sort((a, b) => b.price - a.price)
    const page = Math.max(1, params?.page || 1)
    const pageSize = Math.max(1, params?.page_size || filtered.length || 20)
    const start = (page - 1) * pageSize
    return { items: filtered.slice(start, start + pageSize), total: filtered.length, page, page_size: pageSize }
  })
}

export function getProduct(id: number) {
  return request<CanonicalProduct>({ url: `/public/products/${id}`, cacheMs: 15_000 }).then(toProduct)
}

export function getPriceTrend(id: number) {
  return getProduct(id).then(product => request<Array<{ date: string; close: number }>>({
    url: '/public/market/candles',
    data: { gpu_model: product.gpu_model, days: 30 },
  })).then(rows => rows.map(row => ({ date: row.date, price: row.close })))
}

export function getQuoteOverview() {
  return request<Array<{ gpu_model: string; min_price: number; average_price: number; available_gpu_count: number; provider_count: number }>>({
    url: '/public/market/summary',
    cacheMs: 60_000,
  }).then(rows => ({ ranking: rows.map(row => ({
    gpu_model: row.gpu_model,
    name: row.gpu_model,
    min_price: row.min_price,
    avg_price: row.average_price,
    total_stock: row.available_gpu_count,
    supplier_count: row.provider_count,
    change: 0,
  })) }))
}
