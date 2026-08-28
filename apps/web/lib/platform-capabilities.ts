import { apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";

export type PlatformCapabilities = {
  commerce_mode: "direct_trade" | "matchmaking" | "history_only";
  matchmaking_enabled: boolean;
  direct_trade_enabled: boolean;
  payment_enabled: boolean;
  recharge_enabled: boolean;
  withdraw_enabled: boolean;
  history_read_enabled: boolean;
};

export const FAIL_CLOSED_PLATFORM_CAPABILITIES: PlatformCapabilities = Object.freeze({
  commerce_mode: "matchmaking",
  matchmaking_enabled: true,
  direct_trade_enabled: false,
  payment_enabled: false,
  recharge_enabled: false,
  withdraw_enabled: false,
  history_read_enabled: true,
});

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
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
    payment_enabled: directTradeEnabled && source.payment_enabled === true,
    recharge_enabled: directTradeEnabled && source.recharge_enabled === true,
    withdraw_enabled: directTradeEnabled && source.withdraw_enabled === true,
    history_read_enabled: source.history_read_enabled !== false,
  };
}

export async function getPlatformCapabilities() {
  const payload = await apiRequest<unknown>(canonicalApiPath("/platform/capabilities"));
  return normalizePlatformCapabilities(payload);
}
