export type ProductPurchaseType = "usage" | "holding";

export type ConsumerRebateTier = {
  max_month_spent: number | null;
  rate: number;
};

export type ProductRebateSummary = {
  month_spent: number;
  month_rebated: number;
  current_rate: number;
  next_tier_hint: string;
  pending_rebate: number;
  monthly_cap: number;
  rewards_enabled: boolean;
  reward_mode: "disabled" | "test_card_hours" | "live";
  minimum_order_amount?: number;
  tiers?: ConsumerRebateTier[];
};

export function clampPurchaseHours(value: number, maximum = 720) {
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.min(Math.floor(value), Math.max(1, Math.floor(maximum))));
}

/** Estimate from server-returned reward policy only; no tier is invented here. */
export function estimateProductExpiryRebate(
  orderAmount: number,
  purchaseType: ProductPurchaseType,
  summary: ProductRebateSummary | null,
) {
  const amount = Number(orderAmount);
  if (!summary?.rewards_enabled || purchaseType !== "usage" || !Number.isFinite(amount) || amount <= 0) {
    return { amount: 0, ratePercent: 0 };
  }
  const spent = Number(summary.month_spent);
  const minimum = Number(summary.minimum_order_amount ?? Number.NaN);
  if (!Number.isFinite(spent) || spent < 0 || !Number.isFinite(minimum) || minimum < 0 || amount < minimum) {
    return { amount: 0, ratePercent: 0 };
  }
  const projectedMonthlySpend = spent + amount;
  const projectedTier = [...(summary.tiers ?? [])]
    .filter((tier) => {
      const limit = tier.max_month_spent;
      const rate = Number(tier.rate);
      return (limit == null || (Number.isFinite(Number(limit)) && Number(limit) >= 0))
        && Number.isFinite(rate)
        && rate > 0
        && rate <= 100;
    })
    .sort((left, right) => (
      (left.max_month_spent ?? Number.POSITIVE_INFINITY)
      - (right.max_month_spent ?? Number.POSITIVE_INFINITY)
    ))
    .find((tier) => tier.max_month_spent == null || projectedMonthlySpend <= Number(tier.max_month_spent));
  if (!projectedTier) return { amount: 0, ratePercent: 0 };

  const ratePercent = Number(projectedTier.rate);
  const unrounded = amount * ratePercent / 100;
  const scaled = unrounded * 100;
  const floatingPointTolerance = Number.EPSILON * Math.max(1, Math.abs(scaled)) * 4;
  return {
    amount: Math.floor(scaled + 0.5 + floatingPointTolerance) / 100,
    ratePercent,
  };
}
