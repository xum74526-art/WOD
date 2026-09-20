import type { BuyRequestDeal, BuyRequestQuote } from '@/api/buy-request'

const OPEN_REQUEST_STATUSES = new Set(['published', 'quoting', 'active'])
const ACTIVE_QUOTE_STATUSES = new Set(['active', 'countered', 'revised'])

function flagAllows(value: boolean | undefined) {
  return value !== false
}

export function canSellerSubmitQuote(options: {
  matchmakingEnabled: boolean
  isOwnRequest: boolean
  requestStatus: string
  ownQuote?: BuyRequestQuote | null
}) {
  return options.matchmakingEnabled
    && !options.isOwnRequest
    && OPEN_REQUEST_STATUSES.has(options.requestStatus)
    && !options.ownQuote
}

export function canCounterQuote(options: {
  matchmakingEnabled: boolean
  role: 'buyer' | 'seller'
  isOwnRequest: boolean
  requestStatus: string
  quote: BuyRequestQuote
  deal?: BuyRequestDeal | null
}) {
  if (!options.matchmakingEnabled || options.deal) return false
  if (!OPEN_REQUEST_STATUSES.has(options.requestStatus)) return false
  if (!ACTIVE_QUOTE_STATUSES.has(options.quote.status)) return false
  if (!flagAllows(options.quote.can_counter)) return false
  const lastActor = options.quote.latest_revision?.actor_role
  if (options.role === 'buyer' && lastActor === 'buyer') return false
  if (options.role === 'seller' && (lastActor === 'supplier' || lastActor === 'seller')) return false
  return options.role === 'buyer' ? options.isOwnRequest : !options.isOwnRequest
}

export function canWithdrawQuote(options: {
  matchmakingEnabled: boolean
  isOwnRequest: boolean
  requestStatus: string
  quote: BuyRequestQuote
  deal?: BuyRequestDeal | null
}) {
  return options.matchmakingEnabled
    && !options.isOwnRequest
    && !options.deal
    && OPEN_REQUEST_STATUSES.has(options.requestStatus)
    && ACTIVE_QUOTE_STATUSES.has(options.quote.status)
    && flagAllows(options.quote.can_withdraw)
}

export function canBuyerSelectQuote(options: {
  matchmakingEnabled: boolean
  directTradeEnabled: boolean
  isOwnRequest: boolean
  requestStatus: string
  quote: BuyRequestQuote
  deal?: BuyRequestDeal | null
}) {
  return (options.matchmakingEnabled || options.directTradeEnabled)
    && options.isOwnRequest
    && !options.deal
    && OPEN_REQUEST_STATUSES.has(options.requestStatus)
    && ACTIVE_QUOTE_STATUSES.has(options.quote.status)
}

function dealStatusAllows(deal: BuyRequestDeal | null | undefined, allowed: string[], flag: keyof BuyRequestDeal) {
  return Boolean(deal && allowed.includes(deal.status) && flagAllows(deal[flag] as boolean | undefined))
}

export function canSupplierConfirmDeal(deal?: BuyRequestDeal | null) {
  return dealStatusAllows(deal, ['buyer_selected'], 'can_supplier_confirm')
}

export function canSupplierDeclineDeal(deal?: BuyRequestDeal | null) {
  return dealStatusAllows(deal, ['buyer_selected'], 'can_supplier_decline')
}

export function canSupplierSubmitCredential(deal?: BuyRequestDeal | null) {
  return dealStatusAllows(deal, ['credential_pending', 'credential_rejected'], 'can_submit_credential')
}

export function canBuyerViewCredential(deal?: BuyRequestDeal | null) {
  return dealStatusAllows(deal, ['credential_released', 'completed', 'delivery_disputed'], 'can_buyer_view_credential')
}

export function canBuyerConfirmDelivery(deal?: BuyRequestDeal | null) {
  return dealStatusAllows(deal, ['credential_released'], 'can_buyer_confirm')
}

export function canBuyerReportDelivery(deal?: BuyRequestDeal | null) {
  return dealStatusAllows(deal, ['credential_released'], 'can_report')
}
