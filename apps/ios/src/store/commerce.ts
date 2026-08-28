import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getPlatformCapabilities, type PlatformCapabilities } from '@/api/platform'
import { parseDirectTradeBuildGate, resolveDirectTradeEnabled } from '@/utils/commerce-mode'

const FAIL_CLOSED_CAPABILITIES: PlatformCapabilities = Object.freeze({
  commerce_mode: 'unavailable',
  matchmaking_enabled: false,
  direct_trade_enabled: false,
  payment_enabled: false,
  recharge_enabled: false,
  withdraw_enabled: false,
  history_read_enabled: false,
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
  const paymentEnabled = computed(() => directTradeEnabled.value && capabilities.value.payment_enabled === true)
  const rechargeEnabled = computed(() => paymentEnabled.value && capabilities.value.recharge_enabled === true)
  const withdrawEnabled = computed(() => directTradeEnabled.value && capabilities.value.withdraw_enabled === true)
  const historyReadEnabled = computed(() => available.value && capabilities.value.history_read_enabled === true)

  function failClosed(reason = ''): PlatformCapabilities {
    capabilities.value = FAIL_CLOSED_CAPABILITIES
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
          payment_enabled: next?.payment_enabled === true,
          recharge_enabled: next?.recharge_enabled === true,
          withdraw_enabled: next?.withdraw_enabled === true,
          history_read_enabled: next?.history_read_enabled === true,
        }
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
    paymentEnabled,
    rechargeEnabled,
    withdrawEnabled,
    historyReadEnabled,
    refresh,
  }
})
