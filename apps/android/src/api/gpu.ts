import { request } from './request'

export type ProductStockSemantics =
  | 'platform_manual_fulfillment_allocation'
  // Compatibility with older API responses; current public responses use the neutral value above.
  | 'platform_closed_test_manual_fulfillment_allocation'
  | 'supplier_reported_inventory'
  | 'merchant_declared_inventory'
  | 'reported_available_units'
  | 'max_configurable_quantity_not_live_inventory'

export interface Product {
  id: number
  name: string
  gpu_model: string
  memory: string
  cuda?: string
  price: number
  billing_unit?: 'GPU_HOUR' | string
  price_currency?: 'CNY' | string
  price_cny_per_gpu_hour?: number
  price_card_hours_per_gpu_hour?: number
  wallet_charge_unit?: 'CARD_HOUR' | string
  purchase_unit?: 'hour' | string
  purchase_hour_options?: number[]
  cycle?: number[]
  desc?: string
  supplier_id?: number
  supplier_name?: string
  supplier_rating?: number | null
  supplier_order_count?: number | null
  seller_type?: 'kai_self_operated' | 'merchant'
  seller_name?: string
  fulfillment_mode?: 'platform_manual' | 'merchant_manual'
  assurance_label?: string
  assurance_description?: string
  status: string
  daily_revenue?: number | null
  revenue_estimate_available?: boolean
  purchasable?: boolean
  purchase_unavailable_reason?: string | null
  stock?: number
  reported_stock?: number
  source_max_configurable_quantity?: number | null
  platform_stock_cap?: number | null
  platform_stock_remaining?: number | null
  max_configurable_quantity?: number | null
  market_source?: 'wod' | 'kai' | 'vast' | 'autodl'
  external_product_id?: string | null
  stock_semantics?: ProductStockSemantics | null
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
  market_source?: 'kai' | 'wod'
  representative?: boolean
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

export interface RegionalQuoteItem {
  region_code: string
  region: string
  median_price_cny: number | null
  min_price_cny: number | null
  max_price_cny: number | null
  p25_price_cny?: number | null
  p75_price_cny?: number | null
  quote_sample_count: number
  location_count: number
  relative_to_lowest_pct: number | null
  is_lowest: boolean
  observed_at?: string | null
}

export interface RegionalQuoteResponse {
  gpu_model: string
  gpu_variant: string
  region_count: number
  source: 'kai'
  billing_unit: 'GPU_HOUR' | string
  market_status: string
  sample_semantics: 'quote_observations' | string
  regions: RegionalQuoteItem[]
}

export function getRegionalQuotes(model: string, variant: string) {
  return request<RegionalQuoteResponse>({
    url: '/products/quote/regional',
    data: { model, variant },
  })
}
