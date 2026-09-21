<template>
  <view :class="['page', pageMotionClass, { 'picker-open': pickerOpen }]">
    <view class="shell">
      <view class="asset-page-header">
        <text class="asset-page-kicker">{{ t(role === 'supplier' ? 'merchantAssetOperations' : 'myAssets') }}</text>
        <view
          class="asset-panel-trigger pressable"
          role="button"
          tabindex="0"
          :aria-label="t('switchAssetComponent')"
          @tap="openPicker"
        >
          <text class="asset-panel-title">{{ currentPanelTitle }}</text>
          <view class="asset-panel-trigger-icon"><AppIcon name="chevron-down" :size="28" /></view>
        </view>
        <text class="asset-page-description">{{ currentPanelDescription }}</text>
      </view>

      <view v-if="role === 'personal' && !revenueSettlementEnabled" class="service-warning">{{ t('revenueSettlementUnavailable') }}</view>
      <view v-if="role === 'personal' && (assetLoadError || walletLoadError)" class="service-warning">{{ t('partialAssetDataUnavailable') }}</view>

      <view :key="visiblePanelKey" class="asset-panel-host">
        <SupplierAssetOverviewPanel
          v-if="visiblePanelKey === 'asset-overview' && role === 'supplier'"
          @navigate="go"
        />

        <AssetOverviewPanel
          v-else-if="visiblePanelKey === 'asset-overview'"
          :summary="summary"
          :assets="activeAssets"
          :total-asset="totalAsset"
          :wallet-balance="walletBalance"
          :total-income="totalIncome"
          :today-revenue="todayComputeRevenue"
          :active-count="activeAssetCount"
          :asset-available="!assetLoadError"
          :wallet-available="!walletLoadError"
          :loading="assetStore.loading"
          :error="assetLoadError && walletLoadError"
          :updated-at="assetStore.lastUpdated"
          @navigate="go"
          @retry="load"
        />

        <SupplierComputeAssetsPanel
          v-else-if="visiblePanelKey === 'compute-assets' && role === 'supplier'"
          @navigate="go"
        />

        <ComputeAssetsPanel
          v-else-if="visiblePanelKey === 'compute-assets'"
          :summary="summary"
          :items="items"
          :active-count="activeAssetCount"
          :today-revenue="todayComputeRevenue"
          :expiring-count="expiringSevenDays"
          :tab="tab"
          :loading="assetStore.loading"
          :list-loading="listLoading"
          :error="assetLoadError || listError"
          @navigate="go"
          @retry="load"
          @update-tab="onTab"
        />

        <DeviceHostingPanel
          v-else-if="visiblePanelKey === 'device-hosting'"
          @navigate="go"
          @select-panel="selectPanel"
        />

        <DeviceStatusPanel
          v-else-if="visiblePanelKey === 'device-status'"
          @navigate="go"
        />

        <HostingEarningsPanel
          v-else-if="visiblePanelKey === 'hosting-earnings'"
          :wallet-balance="walletBalance"
          :total-income="totalIncome"
          :pending-revenue="summary?.pending_revenue || 0"
          :loading="assetStore.loading || hostingStore.loading"
          :error="walletLoadError || assetLoadError || !!hostingStore.error"
          @navigate="go"
          @retry="load"
        />

        <ActionRequiredPanel
          v-else-if="visiblePanelKey === 'action-required'"
          @navigate="go"
        />

        <SupplierExpiryMaintenancePanel
          v-else-if="role === 'supplier'"
          @navigate="go"
        />

        <ExpiryMaintenancePanel
          v-else
          :assets="activeAssets"
          :loading="assetStore.loading"
          :error="assetLoadError"
          @navigate="go"
          @retry="load"
        />
      </view>
    </view>

    <AssetPanelPicker
      :open="pickerOpen"
      :items="panelOptions"
      :active-key="draftPanelKey"
      @preview="previewPanel"
      @confirm="confirmPanel"
      @cancel="cancelPicker"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onBackPress, onLoad, onShow } from '@dcloudio/uni-app'
import { getAssets, type AssetItem } from '@/api/asset'
import { getWallet } from '@/api/wallet'
import ActionRequiredPanel from '@/components/assets/ActionRequiredPanel.vue'
import AssetOverviewPanel from '@/components/assets/AssetOverviewPanel.vue'
import AssetPanelPicker from '@/components/assets/AssetPanelPicker.vue'
import ComputeAssetsPanel from '@/components/assets/ComputeAssetsPanel.vue'
import DeviceHostingPanel from '@/components/assets/DeviceHostingPanel.vue'
import DeviceStatusPanel from '@/components/assets/DeviceStatusPanel.vue'
import ExpiryMaintenancePanel from '@/components/assets/ExpiryMaintenancePanel.vue'
import HostingEarningsPanel from '@/components/assets/HostingEarningsPanel.vue'
import SupplierAssetOverviewPanel from '@/components/assets/SupplierAssetOverviewPanel.vue'
import SupplierComputeAssetsPanel from '@/components/assets/SupplierComputeAssetsPanel.vue'
import SupplierExpiryMaintenancePanel from '@/components/assets/SupplierExpiryMaintenancePanel.vue'
import type { AssetPanelKey, AssetPanelOption } from '@/components/assets/types'
import AppIcon from '@/components/AppIcon.vue'
import { useAssetStore } from '@/store/asset'
import { useHostingStore } from '@/store/hosting'
import { useI18nStore } from '@/store/i18n'
import { useUserStore } from '@/store/user'
import { navigateTo as nav } from '@/utils/nav'
import { usePageMotion } from '@/utils/page-motion'

const PANEL_KEYS: AssetPanelKey[] = [
  'asset-overview',
  'compute-assets',
  'device-hosting',
  'device-status',
  'hosting-earnings',
  'action-required',
  'expiry-maintenance',
]

interface AssetPanelMeta extends AssetPanelOption {
  description: string
}

const assetStore = useAssetStore()
const hostingStore = useHostingStore()
const userStore = useUserStore()
const i18n = useI18nStore()
const { t } = i18n
const { pageMotionClass } = usePageMotion()
const role = computed(() => userStore.role)

const walletBalance = ref(0)
const totalIncome = ref(0)
const revenueSettlementEnabled = ref(false)
const tab = ref(0)
const items = ref<AssetItem[]>([])
const listLoading = ref(false)
const listError = ref(false)
const assetLoadError = ref(false)
const walletLoadError = ref(false)
const pickerOpen = ref(false)
const selectedPanelKey = ref<AssetPanelKey>('asset-overview')
const previousPanelKey = ref<AssetPanelKey>('asset-overview')
const draftPanelKey = ref<AssetPanelKey>('asset-overview')
const panelRole = ref<'personal' | 'supplier' | ''>('')
const requestedPanel = ref<AssetPanelKey | null>(null)

const summary = computed(() => assetStore.summary)
const activeAssets = computed(() => (summary.value?.items ?? []).filter((asset) => asset.status === 'active'))
const activeAssetCount = computed(() => activeAssets.value.reduce((sum, asset) => sum + Math.max(asset.quantity || 1, 1), 0))
const todayComputeRevenue = computed(() => activeAssets.value.reduce((sum, asset) => sum + Number(asset.today_revenue || 0), 0))
const expiringSevenDays = computed(() => activeAssets.value.filter((asset) => (asset.remaining_days ?? 999) <= 7).length)
const totalAsset = computed(() => Number(summary.value?.total_value || 0) + walletBalance.value)
const visiblePanelKey = computed(() => pickerOpen.value ? draftPanelKey.value : selectedPanelKey.value)

const personalPanelMeta = computed<AssetPanelMeta[]>(() => [
  { key: 'asset-overview', label: t('personalAssetOverview'), description: t('personalAssetOverviewSummary') },
  { key: 'compute-assets', label: t('personalComputeAssets'), description: t('personalComputeAssetsSummary') },
  { key: 'device-hosting', label: t('personalDeviceHosting'), description: t('personalDeviceHostingSummary') },
  { key: 'device-status', label: t('personalDeviceStatus'), description: t('personalDeviceStatusSummary') },
  { key: 'hosting-earnings', label: t('personalEarningsSettlement'), description: t('personalEarningsSettlementSummary') },
  { key: 'action-required', label: t('personalActionRequired'), description: t('personalActionRequiredSummary') },
  { key: 'expiry-maintenance', label: t('personalExpiryRenewal'), description: t('personalExpiryRenewalSummary') },
])

const supplierPanelMeta = computed<AssetPanelMeta[]>(() => [
  { key: 'asset-overview', label: t('merchantOperationsOverview'), description: t('merchantAssetOverviewSummary') },
  { key: 'compute-assets', label: t('merchantComputeInventory'), description: t('merchantComputeAssetsSummary') },
  { key: 'device-hosting', label: t('merchantHostingFleet'), description: t('merchantHostingFleetSummary') },
  { key: 'device-status', label: t('merchantDeviceOperations'), description: t('merchantDeviceOperationsSummary') },
  { key: 'hosting-earnings', label: t('merchantSalesSettlement'), description: t('merchantSalesSettlementSummary') },
  { key: 'action-required', label: t('merchantOperationsAlerts'), description: t('merchantOperationsAlertsSummary') },
  { key: 'expiry-maintenance', label: t('merchantInventoryMaintenance'), description: t('merchantExpiryMaintenanceSummary') },
])

const activePanelMeta = computed(() => role.value === 'supplier' ? supplierPanelMeta.value : personalPanelMeta.value)
const allowedPanelKeys = computed(() => activePanelMeta.value.map((panel) => panel.key))
const panelOptions = computed<AssetPanelOption[]>(() => activePanelMeta.value.map(({ key, label }) => ({ key, label })))

const currentPanelTitle = computed(() => panelOptions.value.find((panel) => panel.key === visiblePanelKey.value)?.label || t('assetOverview'))
const currentPanelDescription = computed(() => activePanelMeta.value.find((panel) => panel.key === visiblePanelKey.value)?.description || '')

function isPanelKey(value: unknown): value is AssetPanelKey {
  return typeof value === 'string' && PANEL_KEYS.includes(value as AssetPanelKey)
}

function isAllowedPanelKey(value: unknown): value is AssetPanelKey {
  return isPanelKey(value) && allowedPanelKeys.value.includes(value)
}

function defaultPanelKey() : AssetPanelKey {
  return role.value === 'supplier' ? 'device-hosting' : 'asset-overview'
}

function panelStorageKey() {
  return `wod-selected-asset-panel:${role.value}`
}

function restorePanel(requested?: AssetPanelKey | null) {
  const saved = uni.getStorageSync(panelStorageKey())
  const initial = isAllowedPanelKey(requested)
    ? requested
    : isAllowedPanelKey(saved)
      ? saved
      : defaultPanelKey()
  selectedPanelKey.value = initial
  previousPanelKey.value = initial
  draftPanelKey.value = initial
  panelRole.value = role.value
}

async function load() {
  assetLoadError.value = false
  walletLoadError.value = false
  walletBalance.value = 0
  totalIncome.value = 0
  items.value = []

  if (role.value === 'supplier') {
    revenueSettlementEnabled.value = true
    await hostingStore.refresh()
    return
  }

  const [walletResult, assetResult] = await Promise.allSettled([
    getWallet(),
    assetStore.refresh(),
    hostingStore.refresh(),
  ])

  if (walletResult.status === 'fulfilled') {
    walletBalance.value = walletResult.value.balance
    totalIncome.value = walletResult.value.total_income
    revenueSettlementEnabled.value = walletResult.value.revenue_settlement_enabled === true
  }

  walletLoadError.value = walletResult.status === 'rejected'
  assetLoadError.value = assetResult.status === 'rejected'

  await loadItems()
}

async function loadItems() {
  listLoading.value = true
  listError.value = false
  try {
    if (tab.value === 2) {
      items.value = (await getAssets('expired')).items
    } else {
      const active = (await getAssets('active')).items
      items.value = tab.value === 1
        ? active.filter((asset) => (asset.remaining_days ?? 999) <= 7)
        : active
    }
  } catch {
    items.value = []
    listError.value = true
  } finally {
    listLoading.value = false
  }
}

function onTab(value: number) {
  tab.value = value
  loadItems()
}

function openPicker() {
  previousPanelKey.value = selectedPanelKey.value
  draftPanelKey.value = selectedPanelKey.value
  pickerOpen.value = true
}

function previewPanel(key: AssetPanelKey) {
  draftPanelKey.value = key
}

function confirmPanel(key: AssetPanelKey) {
  if (!isAllowedPanelKey(key)) key = defaultPanelKey()
  selectedPanelKey.value = key
  draftPanelKey.value = key
  pickerOpen.value = false
  uni.setStorageSync(panelStorageKey(), key)
  uni.pageScrollTo({ scrollTop: 0, duration: 180 })
}

function cancelPicker() {
  draftPanelKey.value = previousPanelKey.value
  pickerOpen.value = false
}

function selectPanel(key: AssetPanelKey) {
  if (!isAllowedPanelKey(key)) return
  selectedPanelKey.value = key
  previousPanelKey.value = key
  draftPanelKey.value = key
  uni.setStorageSync(panelStorageKey(), key)
  uni.pageScrollTo({ scrollTop: 0, duration: 180 })
}

function go(url: string) {
  nav(url)
}

onLoad((options) => {
  requestedPanel.value = isPanelKey(options?.panel) ? options.panel : null
  restorePanel(requestedPanel.value)
})

onShow(async () => {
  i18n.updateTabBar()
  if (userStore.isLogin) {
    try { await userStore.fetchProfile() } catch {}
  }
  if (panelRole.value !== role.value || !isAllowedPanelKey(selectedPanelKey.value)) {
    restorePanel(requestedPanel.value)
  }
  requestedPanel.value = null
  load().catch(() => {
    assetLoadError.value = true
    walletLoadError.value = true
  })
})

onBackPress(() => {
  if (!pickerOpen.value) return false
  cancelPicker()
  return true
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; min-height: 100dvh; background: var(--bg); }
.page.picker-open { overflow: hidden; }
.shell { padding: calc(24rpx + var(--safe-top)) 32rpx calc(140rpx + var(--safe-bottom)); }
.asset-page-header { padding: 8rpx 0 24rpx; }
.asset-page-kicker { display: block; color: var(--text-sub); font-size: 22rpx; font-weight: 600; margin-bottom: 8rpx; }
.asset-panel-trigger { min-height: 88rpx; display: inline-flex; align-items: center; gap: 12rpx; max-width: 100%; border-radius: 16rpx; }
.asset-panel-trigger:active { transform: scale(0.985); }
.asset-panel-title { min-width: 0; color: var(--text); font-size: 42rpx; line-height: 1.2; font-weight: 780; letter-spacing: -1rpx; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asset-panel-trigger-icon { width: 48rpx; height: 48rpx; flex-shrink: 0; border-radius: 14rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); background: var(--primary-soft); }
.asset-page-description { display: block; max-width: 600rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.5; margin-top: 5rpx; }
.service-warning { color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 22rpx 24rpx; margin-bottom: 20rpx; font-size: 23rpx; line-height: 1.55; }
.asset-panel-host { min-height: calc(100dvh - 260rpx); }

@media (prefers-reduced-motion: reduce) {
  .asset-panel-trigger { transition: none; }
}

@media (max-width: 360px) {
  .shell { padding-left: 26rpx; padding-right: 26rpx; }
  .asset-panel-title { font-size: 37rpx; }
}
</style>
