<template>
  <view class="asset-panel">
    <view v-if="loading && !assets.length" class="asset-panel__skeleton" aria-hidden="true">
      <view class="asset-panel__skeleton-block" style="height: 300rpx"></view>
      <view v-for="n in 3" :key="n" class="asset-panel__skeleton-block"></view>
    </view>

    <view v-else-if="error && !assets.length" class="asset-panel__state">
      <view class="asset-panel__state-icon"><AppIcon name="order" :size="54" /></view>
      <text class="asset-panel__state-title">{{ t('dataUnavailable') }}</text>
      <text class="asset-panel__state-text">{{ t('expiryLoadFailedDesc') }}</text>
      <view class="asset-panel__state-action" @tap="$emit('retry')">{{ t('retry') }}</view>
    </view>

    <template v-else>
      <view class="asset-panel__hero">
        <text class="asset-panel__eyebrow">{{ t('expiryMaintenance') }}</text>
        <view class="asset-panel__amount">
          <text class="asset-panel__amount-value">{{ expiringSevenDays.length }}</text>
          <text class="asset-panel__amount-unit">{{ t('assetsUnit') }}</text>
        </view>
        <text class="asset-panel__hero-note">{{ expiringSevenDays.length ? t('expiryHero') : t('noUpcomingExpiry') }}</text>
        <view class="asset-panel__metrics">
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="expiringThreeDays.length ? 'danger' : ''">{{ expiringThreeDays.length }}</text>
            <text class="asset-panel__metric-label">{{ t('expiringIn3Days') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value" :class="expiringSevenDays.length ? 'warning' : ''">{{ expiringSevenDays.length }}</text>
            <text class="asset-panel__metric-label">{{ t('expiringIn7Days') }}</text>
          </view>
          <view class="asset-panel__metric">
            <text class="asset-panel__metric-value">--</text>
            <text class="asset-panel__metric-label">{{ t('maintenancePlan') }}</text>
          </view>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('upcomingExpiry') }}</text>
          <text class="asset-panel__section-meta">{{ t('countItems', { count: expiringSevenDays.length }) }}</text>
        </view>

        <view v-if="expiringSevenDays.length" class="asset-panel__list">
          <view
            v-for="asset in expiringSevenDays"
            :key="asset.id"
            class="asset-panel__row"
            @tap="$emit('navigate', '/pages/asset/detail?id=' + asset.id)"
          >
            <view class="asset-panel__row-icon"><AppIcon name="order" :size="34" /></view>
            <view class="asset-panel__row-main">
              <text class="asset-panel__row-title">{{ localizeProductName(asset.product_name, i18n.lang) }}</text>
              <text class="asset-panel__row-meta">{{ asset.gpu_model || t('computeResource') }} · {{ formatDate(asset.end_at) || t('dateUnavailable') }}</text>
            </view>
            <view class="asset-panel__row-side">
              <text class="asset-panel__row-value" :class="(asset.remaining_days ?? 0) <= 3 ? 'danger' : ''">{{ t('remainingDaysCount', { days: asset.remaining_days ?? 0 }) }}</text>
            </view>
          </view>
        </view>

        <view v-else class="asset-panel__state">
          <view class="asset-panel__state-icon"><AppIcon name="check" :size="50" /></view>
          <text class="asset-panel__state-title">{{ t('noUpcomingExpiry') }}</text>
          <text class="asset-panel__state-text">{{ t('noUpcomingExpiryDesc') }}</text>
        </view>
      </view>

      <view class="asset-panel__section">
        <view class="asset-panel__section-head">
          <text class="asset-panel__section-title">{{ t('maintenancePlan') }}</text>
          <text class="asset-panel__section-meta">{{ t('notAvailable') }}</text>
        </view>
        <view class="asset-panel__notice">{{ t('noMaintenancePlanDesc') }}</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AssetItem } from '@/api/asset'
import AppIcon from '@/components/AppIcon.vue'
import { useI18nStore } from '@/store/i18n'
import { formatDate } from '@/utils/format'
import { localizeProductName } from '@/utils/localize-content'

const props = defineProps<{
  assets: AssetItem[]
  loading: boolean
  error: boolean
}>()

defineEmits<{
  (event: 'navigate', url: string): void
  (event: 'retry'): void
}>()

const i18n = useI18nStore()
const { t } = i18n
const expiringSevenDays = computed(() => props.assets.filter((asset) => asset.status === 'active' && (asset.remaining_days ?? 999) <= 7))
const expiringThreeDays = computed(() => expiringSevenDays.value.filter((asset) => (asset.remaining_days ?? 999) <= 3))
</script>
