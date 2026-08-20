import { request, requestEnvelope } from './request'

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
  version?: number
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
  version?: number
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

interface CanonicalRequest {
  id: number
  request_no: string
  request_type: 'cloud_compute' | 'offline_device'
  title: string
  status: string
  gpu_model: string
  min_gpu_memory_gb?: number | null
  gpu_quantity: number
  region_codes?: string[]
  budget: { amount?: string | null; currency: string; unit: string }
  quote_deadline_at?: string
  expected_duration_hours?: number | null
  requirements?: string
  created_at?: string
  updated_at?: string
  version?: number
  contact?: { contact_name?: string; contact_phone?: string } | null
  quote_count?: number
}

interface CanonicalQuote {
  id: number
  buy_request_id: number
  status: string
  price: { amount: string; currency: string; unit: string }
  available_quantity: number
  valid_until?: string
  service_description?: string
  created_at?: string
  version: number
  supplier?: { display_name?: string; company_name?: string }
}

function toRequest(row: CanonicalRequest): BuyRequestItem {
  let requirements: Record<string, any> = {}
  try { requirements = row.requirements ? JSON.parse(row.requirements) : {} } catch { requirements = { remark: row.requirements } }
  return {
    id: row.id,
    user_id: 0,
    buyer_name: '',
    request_type: row.request_type === 'offline_device' ? 'offline' : 'online',
    gpu_model: row.gpu_model,
    quantity: row.gpu_quantity,
    gpu_hours: row.expected_duration_hours || undefined,
    max_unit_price: row.budget.unit === 'gpu_hour' ? Number(row.budget.amount || 0) : undefined,
    budget: Number(row.budget.amount || 0) || undefined,
    currency: row.budget.currency,
    region: row.region_codes?.[0],
    requirements,
    contact: row.contact?.contact_name,
    phone: row.contact?.contact_phone,
    status: row.status,
    quote_count: row.quote_count || 0,
    expires_at: row.quote_deadline_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
    legacy: false,
    version: row.version,
  }
}

function toQuote(row: CanonicalQuote): BuyRequestQuote {
  return {
    id: row.id,
    buy_request_id: row.buy_request_id,
    supplier_id: 0,
    supplier_name: row.supplier?.company_name || row.supplier?.display_name || '供应商',
    unit_price: Number(row.price.amount),
    total_price: Number(row.price.amount) * row.available_quantity,
    currency: row.price.currency,
    message: row.service_description,
    status: row.status === 'submitted' ? 'active' : row.status,
    expires_at: row.valid_until,
    created_at: row.created_at,
    version: row.version,
  }
}

export function getBuyRequestSummary() {
  return request<CanonicalRequest[]>({ url: '/account/buy-requests' }).then(rows => ({
    active: rows.filter(row => ['draft', 'reviewing', 'published', 'negotiating'].includes(row.status)).length,
    new_quotes: rows.reduce((sum, row) => sum + Number(row.quote_count || 0), 0),
    pending_confirmation: rows.filter(row => row.status === 'matched').length,
  }))
}

export function getBuyRequests(requestType: 'online' | 'offline', view: 'buyer' | 'seller' = 'buyer') {
  const rows = view === 'seller'
    ? request<CanonicalRequest[]>({ url: '/supplier/buy-requests' })
    : request<CanonicalRequest[]>({ url: '/account/buy-requests' })
  return rows.then(items => items
    .map(toRequest)
    .filter(row => row.request_type === requestType))
}

export function createBuyRequest(data: BuyRequestPayload) {
  const deadline = new Date(Date.now() + data.expires_in_hours * 3600000).toISOString()
  return request<CanonicalRequest>({
    url: '/buy-requests',
    method: 'POST',
    data: {
      request_type: data.request_type === 'offline' ? 'offline_device' : 'cloud_compute',
      title: `${data.gpu_model} 算力需求`,
      visibility: 'public',
      gpu_model: data.gpu_model,
      gpu_quantity: data.quantity,
      region_codes: data.region ? [data.region.replace(/[^A-Za-z0-9_-]/g, '_')] : [],
      delivery_mode: data.request_type === 'offline' ? 'negotiable' : 'remote',
      budget_amount: data.max_unit_price ?? data.budget,
      budget_currency: data.currency,
      budget_unit: data.max_unit_price != null ? 'gpu_hour' : 'total',
      quote_deadline_at: deadline,
      expected_duration_hours: data.gpu_hours,
      requirements: JSON.stringify(data.requirements || {}),
      contact: data.contact ? { contact_name: data.contact, visible_after: 'accepted' } : undefined,
    },
  }).then(row => request<CanonicalRequest>({
    url: `/account/buy-requests/${row.id}/publish`,
    method: 'POST',
    data: { version: row.version },
  })).then(toRequest)
}

export function getBuyRequestDetail(id: number) {
  return Promise.all([
    request<CanonicalRequest>({ url: `/account/buy-requests/${id}` }),
    request<{ request: CanonicalRequest; quotes: CanonicalQuote[] }>({ url: `/account/buy-requests/${id}/quotes` }),
  ]).then(([item, quoteResult]) => ({ request: toRequest(item), quotes: quoteResult.quotes.map(toQuote) }))
    .catch(() => request<{ request: CanonicalRequest; quotes: CanonicalQuote[] }>({
      url: `/supplier/buy-requests/${id}`,
    }).then(result => ({ request: toRequest(result.request), quotes: result.quotes.map(toQuote) })))
}

export function createBuyRequestQuote(id: number, data: { unit_price?: number; total_price: number; currency: string; message?: string; expires_in_hours: number }) {
  return request<CanonicalQuote>({
    url: `/supplier/buy-requests/${id}/quotes`,
    method: 'POST',
    data: {
      price_amount: data.unit_price ?? data.total_price,
      price_currency: data.currency,
      price_unit: data.unit_price != null ? 'gpu_hour' : 'total',
      available_quantity: 1,
      valid_until: new Date(Date.now() + data.expires_in_hours * 3600000).toISOString(),
      service_description: data.message || '',
    },
  }).then(row => request<CanonicalQuote>({
    url: `/supplier/quotes/${row.id}/submit`,
    method: 'POST',
    data: { version: row.version },
  })).then(toQuote)
}

export function selectBuyRequestQuote(requestId: number, quoteId: number) {
  return getBuyRequestDetail(requestId).then(detail => {
    const quote = detail.quotes.find(item => item.id === quoteId)
    if (!quote?.version || !detail.request.version) throw new Error('报价版本信息缺失，请刷新后重试')
    return request<{ id: number; status: string }>({
      url: `/account/buy-requests/${requestId}/quotes/${quoteId}/accept`,
      method: 'POST',
      data: { request_version: detail.request.version, quote_version: quote.version },
    })
  }).then(order => ({ request_id: requestId, quote_id: quoteId, status: order.status }))
}
