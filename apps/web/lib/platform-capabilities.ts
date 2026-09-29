import { apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";
import {
  DEFAULT_DISPLAY_CURRENCY_CONFIG,
  type DisplayCurrencyConfig as CurrencyConfig,
} from "@/lib/display-currency";

export { DEFAULT_DISPLAY_CURRENCY_CONFIG };
export type { DisplayCurrencyCode, DisplayCurrencyConfig } from "@/lib/display-currency";

export type PlatformCapabilities = {
  commerce_mode: "direct_trade" | "matchmaking" | "history_only";
  matchmaking_enabled: boolean;
  direct_trade_enabled: boolean;
  holding_trade_enabled: boolean;
  payment_enabled: boolean;
  recharge_enabled: boolean;
  withdraw_enabled: boolean;
  history_read_enabled: boolean;
  display_currency: CurrencyConfig;
};

export const FAIL_CLOSED_PLATFORM_CAPABILITIES: PlatformCapabilities = Object.freeze({
  commerce_mode: "matchmaking",
  matchmaking_enabled: true,
  direct_trade_enabled: false,
  holding_trade_enabled: false,
  payment_enabled: false,
  recharge_enabled: false,
  withdraw_enabled: false,
  history_read_enabled: true,
  display_currency: DEFAULT_DISPLAY_CURRENCY_CONFIG,
});

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function normalizeDisplayCurrencyConfig(value: unknown): CurrencyConfig {
  const source = object(value);
  const rates = object(source.rates);
  if (source.rate_mode !== "daily_reference") {
    return DEFAULT_DISPLAY_CURRENCY_CONFIG;
  }
  const positiveRate = (candidate: unknown, fallback: number) => {
    const parsed = Number(candidate);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  };
  const rateDate = typeof source.rate_date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(source.rate_date)
    ? source.rate_date
    : null;
  return {
    base_currency: "CNY",
    settlement_currency: "CNY",
    fraction_digits: 3,
    card_hour_cny_rate: 1,
    rates: {
      CNY: 1,
      HKD: positiveRate(rates.HKD, DEFAULT_DISPLAY_CURRENCY_CONFIG.rates.HKD),
      USD: positiveRate(rates.USD, DEFAULT_DISPLAY_CURRENCY_CONFIG.rates.USD),
    },
    rate_mode: "daily_reference",
    rate_source: typeof source.rate_source === "string" ? source.rate_source.slice(0, 32) : "UNKNOWN",
    rate_date: rateDate,
    rates_stale: source.rates_stale !== false,
    conversion_scope: "display_only",
  };
}

export function normalizePlatformCapabilities(value: unknown): PlatformCapabilities {
  const source = object(value);
  const directTradeEnabled = source.direct_trade_enabled === true;
  const matchmakingEnabled = source.matchmaking_enabled === true;
  return {
    commerce_mode: directTradeEnabled
      ? "direct_trade"
      : matchmakingEnabled ? "matchmaking" : "history_only",
    matchmaking_enabled: matchmakingEnabled,
    direct_trade_enabled: directTradeEnabled,
    holding_trade_enabled: directTradeEnabled && source.holding_trade_enabled === true,
    payment_enabled: directTradeEnabled && source.payment_enabled === true,
    recharge_enabled: directTradeEnabled && source.recharge_enabled === true,
    withdraw_enabled: directTradeEnabled && source.withdraw_enabled === true,
    history_read_enabled: source.history_read_enabled !== false,
    display_currency: normalizeDisplayCurrencyConfig(source.display_currency),
  };
}

export async function getPlatformCapabilities() {
  const payload = await apiRequest<unknown>(canonicalApiPath("/platform/capabilities"));
  return normalizePlatformCapabilities(payload);
}
