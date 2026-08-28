export interface DirectTradeCapabilitySource {
  direct_trade_enabled?: unknown
}

export function parseDirectTradeBuildGate(value: unknown): boolean {
  return typeof value === 'string' && value.trim().toLowerCase() === 'true'
}

export function serverAllowsDirectTrade(value: DirectTradeCapabilitySource | null | undefined): boolean {
  return value?.direct_trade_enabled === true
}

/** Both independent gates must be explicitly enabled. */
export function resolveDirectTradeEnabled(
  buildGateEnabled: boolean,
  capabilities: DirectTradeCapabilitySource | null | undefined,
): boolean {
  return buildGateEnabled === true && serverAllowsDirectTrade(capabilities)
}
