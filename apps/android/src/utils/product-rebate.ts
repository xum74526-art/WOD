export type ProductPurchaseType = 'usage' | 'holding'

export interface UsageRebateEstimate {
  amount: number
  ratePercent: number
}

export interface RebateTier {
  max_month_spent: number | null
  rate: number
}

function roundCardHours(value: number): number {
  const scaled = value * 100
  const floatingPointTolerance = Number.EPSILON * Math.max(1, Math.abs(scaled)) * 4
  return Math.floor(scaled + 0.5 + floatingPointTolerance) / 100
}

function normalizedTiers(tiers: RebateTier[]): RebateTier[] {
  return [...tiers]
    .filter((tier) => {
      const limit = tier.max_month_spent
      const rate = Number(tier.rate)
      return (limit == null || (Number.isFinite(Number(limit)) && Number(limit) >= 0))
        && Number.isFinite(rate)
        && rate > 0
        && rate <= 100
    })
    .sort((left, right) => (
      (left.max_month_spent ?? Number.POSITIVE_INFINITY)
      - (right.max_month_spent ?? Number.POSITIVE_INFINITY)
    ))
}

/**
 * Estimate a usage order with the live /user/rebate policy. The order is added
 * to the confirmed monthly usage total to preview the tier that the backend will
 * lock when delivery is confirmed. Holding purchases never earn this rebate.
 */
export function estimateUsageExpiryRebate(
  orderAmount: number,
  purchaseType: ProductPurchaseType,
  rewardsEnabled: boolean,
  monthSpent: number,
  minimumOrderAmount: number,
  tiers: RebateTier[],
  capRemaining: number,
): UsageRebateEstimate {
  const amount = Number(orderAmount)
  const spent = Number(monthSpent)
  const minimum = Number(minimumOrderAmount)
  const remaining = Number(capRemaining)
  if (
    purchaseType !== 'usage'
    || !rewardsEnabled
    || !Number.isFinite(amount)
    || amount <= 0
    || !Number.isFinite(spent)
    || spent < 0
    || !Number.isFinite(minimum)
    || minimum < 0
    || amount < minimum
    || !Number.isFinite(remaining)
    || remaining < 0
  ) {
    return { amount: 0, ratePercent: 0 }
  }

  const projectedMonthlySpend = spent + amount
  const projectedTier = normalizedTiers(tiers).find((tier) => (
    tier.max_month_spent == null || projectedMonthlySpend <= Number(tier.max_month_spent)
  ))
  if (!projectedTier) return { amount: 0, ratePercent: 0 }

  const ratePercent = Number(projectedTier.rate)
  return {
    amount: roundCardHours(Math.min(amount * ratePercent / 100, remaining)),
    ratePercent,
  }
}
