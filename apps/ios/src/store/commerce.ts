import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getPlatformCapabilities, type DisplayCurrencyConfig, type PlatformCapabilities } from '@/api/platform'
import { parseDirectTradeBuildGate, resolveDirectTradeEnabled } from '@/utils/commerce-mode'
import { setDisplayCurrencyConfig } from '@/utils/format'

const DEFAULT_DISPLAY_CURRENCY = Object.freeze({
  base_currency: 'CNY' as const,
  settlement_currency: 'CNY' as const,
  fraction_digits: 3 as const,
  card_hour_cny_rate: 1,
  rates: Object.freeze({ CNY: 1, HKD: 1.169032900251, USD: 0.149020326907 }),
  rate_mode: 'daily_reference' as const,
  rate_source: 'ECB_BOOTSTRAP',
  rate_date: '2026-09-28',
  rates_stale: true,
  conversion_scope: 'display_only' as const,
})

function normalizeDisplayCurrency(value?: Partial<DisplayCurrencyConfig> | null): DisplayCurrencyConfig {
  if (value?.rate_mode !== 'daily_reference') return DEFAULT_DISPLAY_CURRENCY
  const positiveRate = (candidate: unknown, fallback: number) => {
    const parsed = Number(candidate)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
  }
  return {
    base_currency: 'CNY',
    settlement_currency: 'CNY',
    fraction_digits: 3,
    card_hour_cny_rate: 1,
    rates: {
      CNY: 1,
      HKD: positiveRate(value.rates?.HKD, DEFAULT_DISPLAY_CURRENCY.rates.HKD),
      USD: positiveRate(value.rates?.USD, DEFAULT_DISPLAY_CURRENCY.rates.USD),
    },
    rate_mode: 'daily_reference',
    rate_source: typeof value.rate_source === 'string' ? value.rate_source.slice(0, 32) : 'UNKNOWN',
    rate_date: typeof value.rate_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.rate_date) ? value.rate_date : null,
    rates_stale: value.rates_stale !== false,
    conversion_scope: 'display_only',
  }
}

const FAIL_CLOSED_CAPABILITIES: PlatformCapabilities = Object.freeze({
  commerce_mode: 'unavailable',
  matchmaking_enabled: false,
  direct_trade_enabled: false,
  holding_trade_enabled: false,
  payment_enabled: false,
  recharge_enabled: false,
  withdraw_enabled: false,
  history_read_enabled: false,
  display_currency: DEFAULT_DISPLAY_CURRENCY,
})
const CAPABILITY_REFRESH_INTERVAL_MS = 60_000

export const DIRECT_TRADE_BUILD_ENABLED = parseDirectTradeBuildGate(
  import.meta.env.VITE_ENABLE_DIRECT_TRADE,
)

export const useCommerceStore = defineStore('commerce', () => {
  const capabilities = ref<PlatformCapabilities>(FAIL_CLOSED_CAPABILITIES)
  const loading = ref(false)
  const loaded = ref(false)
  const available = ref(false)
  const error = ref('')
  const lastUpdatedAt = ref(0)
  let inFlight: Promise<PlatformCapabilities> | null = null

  const directTradeEnabled = computed(() => resolveDirectTradeEnabled(
    DIRECT_TRADE_BUILD_ENABLED,
    capabilities.value,
  ))
  const matchmakingEnabled = computed(() => available.value
    && capabilities.value.matchmaking_enabled === true
    && !directTradeEnabled.value)
  const inquiryMode = computed(() => matchmakingEnabled.value)
  const holdingTradeEnabled = computed(() => directTradeEnabled.value
    && capabilities.value.holding_trade_enabled === true)
  const paymentEnabled = computed(() => directTradeEnabled.value && capabilities.value.payment_enabled === true)
  const rechargeEnabled = computed(() => paymentEnabled.value && capabilities.value.recharge_enabled === true)
  const withdrawEnabled = computed(() => directTradeEnabled.value && capabilities.value.withdraw_enabled === true)
  const historyReadEnabled = computed(() => available.value && capabilities.value.history_read_enabled === true)

  function failClosed(reason = ''): PlatformCapabilities {
    capabilities.value = FAIL_CLOSED_CAPABILITIES
    setDisplayCurrencyConfig(DEFAULT_DISPLAY_CURRENCY)
    available.value = false
    error.value = reason
    return capabilities.value
  }

  async function refresh(force = false): Promise<PlatformCapabilities> {
    if (!force && loaded.value && Date.now() - lastUpdatedAt.value < CAPABILITY_REFRESH_INTERVAL_MS) {
      return capabilities.value
    }
    if (inFlight) return inFlight

    loading.value = true
    inFlight = getPlatformCapabilities()
      .then((next) => {
        capabilities.value = {
          commerce_mode: String(next?.commerce_mode || 'unavailable'),
          matchmaking_enabled: next?.matchmaking_enabled === true,
          direct_trade_enabled: next?.direct_trade_enabled === true,
          holding_trade_enabled: next?.holding_trade_enabled === true,
          payment_enabled: next?.payment_enabled === true,
          recharge_enabled: next?.recharge_enabled === true,
          withdraw_enabled: next?.withdraw_enabled === true,
          history_read_enabled: next?.history_read_enabled === true,
          display_currency: normalizeDisplayCurrency(next?.display_currency),
        }
        setDisplayCurrencyConfig(capabilities.value.display_currency)
        available.value = true
        error.value = ''
        return capabilities.value
      })
      .catch((reason: unknown) => failClosed(reason instanceof Error ? reason.message : 'capability-unavailable'))
      .finally(() => {
        loaded.value = true
        lastUpdatedAt.value = Date.now()
        loading.value = false
        inFlight = null
      })
    return inFlight
  }

  return {
    capabilities,
    loading,
    loaded,
    available,
    error,
    lastUpdatedAt,
    directTradeEnabled,
    matchmakingEnabled,
    inquiryMode,
    holdingTradeEnabled,
    paymentEnabled,
    rechargeEnabled,
    withdrawEnabled,
    historyReadEnabled,
    refresh,
  }
})
