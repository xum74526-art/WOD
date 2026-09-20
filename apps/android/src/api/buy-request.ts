import { request } from './request'

export type BuyRequestView = 'buyer' | 'seller'

export interface BuyRequestRequirements extends Record<string, unknown> {
  note?: unknown
  remark?: unknown
}

export interface BuyRequestItem {
  id: number
  user_id: number | null
  buyer_name?: string | null
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
  requirements: BuyRequestRequirements
  contact?: string | null
  phone?: string | null
  status: string
  quote_count: number
  expires_at?: string
  created_at?: string
  updated_at?: string
  legacy: boolean
  is_own?: boolean
  targeted_supplier_id?: number | null
  targeted_to_me?: boolean
  target_supplier?: { id: number; company_name?: string | null } | null
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
  updated_at?: string
  revision_count?: number
  latest_revision?: BuyRequestQuoteRevision | null
  revisions?: BuyRequestQuoteRevision[]
  can_counter?: boolean
  can_withdraw?: boolean
}

export interface BuyRequestQuoteRevision {
  id: number
  quote_id?: number
  revision_no?: number
  actor_role?: 'buyer' | 'supplier' | string
  unit_price?: number
  total_price: number
  currency: string
  available_at?: string
  message?: string
  expires_at?: string
  created_at?: string
}

export interface BuyRequestDeal {
  id: number
  status: string
  quote_id: number
  selected_revision_id?: number | null
  supplier_id: number
  supplier_name?: string
  credential_status?: string | null
  can_supplier_confirm?: boolean
  can_supplier_decline?: boolean
  can_submit_credential?: boolean
  can_buyer_view_credential?: boolean
  can_buyer_confirm?: boolean
  can_report?: boolean
}

export interface BuyRequestEvent {
  id?: number
  event_type?: string
  status?: string
  label?: string
  actor_role?: string
  message?: string
  created_at?: string
}

export interface BuyRequestCredential {
  host: string
  port: number
  username: string
  auth_type: 'password' | 'private_key'
  secret?: string
  note?: string
  released_at?: string
}

export interface BuyRequestDetail {
  request: BuyRequestItem
  quotes: BuyRequestQuote[]
  deal?: BuyRequestDeal | null
  events?: BuyRequestEvent[]
}

export interface BuyRequestQuotePayload {
  unit_price?: number
  total_price: number
  currency: string
  available_at?: string
  message?: string
  expires_in_hours: number
}

export interface BuyRequestCredentialPayload {
  host: string
  port: number
  username: string
  auth_type: 'password' | 'private_key'
  secret: string
  note?: string
}

export interface BuyRequestPayload {
  client_request_id?: string
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
  requirements?: BuyRequestRequirements
  contact?: string
  phone?: string
  expires_in_hours: number
}

export function getBuyRequestSummary() {
  return request<{ active: number; new_quotes: number; pending_confirmation: number }>({ url: '/buy-requests/summary' })
}

export function getBuyRequests(requestType: 'online' | 'offline', view: BuyRequestView = 'buyer', quotedOnly = false) {
  return request<BuyRequestItem[]>({
    url: '/buy-requests',
    data: {
      request_type: requestType,
      view,
      ...(view === 'seller' && quotedOnly ? { quoted_only: true } : {}),
    },
  })
}

export function createBuyRequest(data: BuyRequestPayload) {
  return request<BuyRequestItem>({ url: '/buy-requests', method: 'POST', data })
}

export function getBuyRequestDetail(id: number) {
  return request<BuyRequestDetail>({ url: `/buy-requests/${id}` })
}

export function submitBuyRequestQuote(requestId: number, data: BuyRequestQuotePayload) {
  return request<BuyRequestQuote>({ url: `/buy-requests/${requestId}/quotes`, method: 'POST', data, retryUncertainOnce: true })
}

export function counterBuyRequestQuote(requestId: number, quoteId: number, data: BuyRequestQuotePayload) {
  return request<BuyRequestQuote>({ url: `/buy-requests/${requestId}/quotes/${quoteId}/counter`, method: 'POST', data })
}

export function withdrawBuyRequestQuote(requestId: number, quoteId: number) {
  return request<{ request_id: number; quote_id: number; status: string }>({ url: `/buy-requests/${requestId}/quotes/${quoteId}/withdraw`, method: 'POST' })
}

export function selectBuyRequestQuote(requestId: number, quoteId: number, expectedRevisionId: number) {
  return request<{ request_id: number; quote_id: number; status: string }>({
    url: `/buy-requests/${requestId}/quotes/${quoteId}/select`,
    method: 'POST',
    data: { expected_revision_id: expectedRevisionId },
  })
}

export function confirmBuyRequestDealBySupplier(requestId: number, dealId: number) {
  return request<BuyRequestDeal>({ url: `/buy-requests/${requestId}/deals/${dealId}/supplier-confirm`, method: 'POST' })
}

export function declineBuyRequestDealBySupplier(requestId: number, dealId: number) {
  return request<BuyRequestDeal>({ url: `/buy-requests/${requestId}/deals/${dealId}/supplier-decline`, method: 'POST' })
}

export function submitBuyRequestCredential(requestId: number, dealId: number, data: BuyRequestCredentialPayload) {
  return request<{ status: string; credential_status?: string }>({ url: `/buy-requests/${requestId}/deals/${dealId}/credential`, method: 'POST', data })
}

export function getBuyRequestCredential(requestId: number, dealId: number) {
  return request<BuyRequestCredential>({ url: `/buy-requests/${requestId}/deals/${dealId}/credential`, silent: true })
}

export function confirmBuyRequestDelivery(requestId: number, dealId: number) {
  return request<BuyRequestDeal>({ url: `/buy-requests/${requestId}/deals/${dealId}/confirm-delivery`, method: 'POST' })
}

export function reportBuyRequestDelivery(requestId: number, dealId: number, reason: string) {
  return request<BuyRequestDeal>({ url: `/buy-requests/${requestId}/deals/${dealId}/report-delivery`, method: 'POST', data: { reason } })
}
