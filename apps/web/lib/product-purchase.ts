import { localeForFormatting, type KaiLocale } from "./language.ts";
import { toTraditionalChinese } from "./traditional-chinese.ts";

export type ProductPurchaseType = "usage" | "holding";

export type RebateTier = {
  max_month_spent: number | null;
  rate: number;
};

export type ProductRebatePolicy = {
  month_spent: number;
  current_rate: number;
  minimum_order_amount: number;
  tiers: RebateTier[];
  cap_remaining: number;
  rewards_enabled: boolean;
};

export function clampPurchaseHours(value: number, maximum = 720) {
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.min(Math.floor(value), Math.max(1, Math.floor(maximum))));
}

function validTiers(summary: ProductRebatePolicy) {
  return [...summary.tiers]
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
    ));
}

/** Estimate an expiry rebate only from the authenticated server policy. */
export function estimateProductExpiryRebate(
  purchasedCardHours: number,
  purchaseType: ProductPurchaseType,
  summary: ProductRebatePolicy | null,
) {
  const amount = Number(purchasedCardHours);
  const spent = Number(summary?.month_spent);
  const minimum = Number(summary?.minimum_order_amount ?? 0);
  const capRemaining = Number(summary?.cap_remaining);
  if (
    !summary?.rewards_enabled
    || purchaseType !== "usage"
    || !Number.isFinite(amount)
    || amount <= 0
    || !Number.isFinite(spent)
    || spent < 0
    || !Number.isFinite(minimum)
    || minimum < 0
    || amount < minimum
    || !Number.isFinite(capRemaining)
    || capRemaining < 0
  ) {
    return { amount: 0, ratePercent: 0 };
  }

  const tiers = validTiers(summary);
  const projectedSpend = spent + amount;
  const projectedTier = tiers.find((tier) => (
    tier.max_month_spent == null || projectedSpend <= Number(tier.max_month_spent)
  ));
  const fallbackRate = Number(summary.current_rate);
  const ratePercent = Number(projectedTier?.rate ?? fallbackRate);
  if (!Number.isFinite(ratePercent) || ratePercent <= 0 || ratePercent > 100) {
    return { amount: 0, ratePercent: 0 };
  }

  const scaled = amount * ratePercent;
  const floatingPointTolerance = Number.EPSILON * Math.max(1, Math.abs(scaled)) * 4;
  const uncappedAmount = Math.floor(scaled + 0.5 + floatingPointTolerance) / 100;
  return {
    amount: Math.min(uncappedAmount, capRemaining),
    ratePercent,
  };
}

export function localizeRebateHint(value: string | null | undefined, locale: KaiLocale) {
  const source = String(value || "").trim();
  if (locale === "zh-Hant") return toTraditionalChinese(source);
  if (locale !== "en" || !source) return source;

  let match = source.match(/^再(?:消费|购买)\s*([\d,.]+)\s*卡时可升至\s*([\d.]+)%\s*返佣$/);
  if (match) return `Spend ${match[1]} more card hours to reach the ${match[2]}% personal purchase rebate tier.`;
  match = source.match(/^再销售\s*([\d,.]+)\s*卡时可升至\s*([\d.]+)%\s*返佣$/);
  if (match) return `Confirm ${match[1]} more card hours in sales to reach the ${match[2]}% supplier sales rebate tier.`;
  match = source.match(/^已达最高返佣等级\s*([\d.]+)%$/);
  if (match) return `Highest rebate tier reached: ${match[1]}%.`;
  if (source === "返佣计划当前未开启") return "This rebate program is currently disabled.";
  return /[\u3400-\u9fff]/.test(source)
    ? "Tier progress is calculated from confirmed card hours this month."
    : source;
}

export function rebateTierRange(tiers: RebateTier[], index: number, locale: KaiLocale) {
  const previous = index > 0 ? tiers[index - 1]?.max_month_spent : 0;
  const current = tiers[index]?.max_month_spent;
  const format = (value: number) => value.toLocaleString(localeForFormatting(locale), { maximumFractionDigits: 2 });
  if (current == null) return `${format(Number(previous || 0))}+`;
  return `${format(Number(previous || 0))} – ${format(Number(current))}`;
}
