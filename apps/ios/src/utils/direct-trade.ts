import type { Product } from '@/api/gpu'
import { toCardHours } from '@/utils/format'

type DirectTradeProductPrice = Pick<
  Product,
  'price' | 'price_cny_per_gpu_hour' | 'price_card_hours_per_gpu_hour' | 'seller_type' | 'market_source'
>

export function directTradeCnyPerGpuHour(product: DirectTradeProductPrice): number {
  return Number(product.price_cny_per_gpu_hour ?? product.price ?? 0)
}

export function directTradeCardHoursPerGpuHour(product: DirectTradeProductPrice): number {
  const fallback = product.seller_type === 'kai_self_operated' || product.market_source === 'kai'
    ? toCardHours(directTradeCnyPerGpuHour(product))
    : Number(product.price ?? 0)
  return Number(product.price_card_hours_per_gpu_hour ?? fallback)
}

export function directTradeProductPurchasable(
  product: Pick<Product, 'purchasable' | 'stock'>,
): boolean {
  return product.purchasable === true && Number(product.stock || 0) > 0
}
