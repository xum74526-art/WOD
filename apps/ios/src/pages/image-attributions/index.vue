<template>
  <view class="page">
    <AppNavBar :title="t('imageAttributionsTitle')" />
    <scroll-view scroll-y class="body">
      <view class="card intro-card">
        <text class="heading">{{ t('imageAttributionsCommonsHeading') }}</text>
        <text class="copy">{{ t('imageAttributionsSummary') }}</text>
        <text class="notice">{{ t('imageAttributionsTrademarkNotice') }}</text>
      </view>

      <view v-for="item in IMAGE_ATTRIBUTIONS" :key="item.asset" class="card attribution-card">
        <text class="asset">{{ item.asset }}</text>
        <text class="work">{{ item.work }}</text>
        <view class="detail-row">
          <text class="label">{{ t('imageAttributionsAuthor') }}</text>
          <text class="value">{{ item.author }}</text>
        </view>
        <view class="detail-row">
          <text class="label">{{ t('imageAttributionsLicense') }}</text>
          <text class="value">{{ item.license }}</text>
        </view>
        <view class="links">
          <button class="link-button" @tap="open(item.sourceUrl)">{{ t('imageAttributionsOriginalWork') }}</button>
          <button class="link-button" @tap="open(item.licenseUrl)">{{ t('imageAttributionsLicenseText') }}</button>
        </view>
        <view class="detail-block">
          <text class="label">{{ t('imageAttributionsModification') }}</text>
          <text class="value block-value">{{ t(item.modificationKey) }}</text>
        </view>
        <view class="detail-block">
          <text class="label">{{ t('imageAttributionsAliases') }}</text>
          <text class="value block-value">{{ item.aliases.length ? item.aliases.join(' · ') : t('imageAttributionsNoAliases') }}</text>
        </view>
      </view>

      <view class="card rights-card">
        <text class="heading">{{ t('imageAttributionsDirectRightsHeading') }}</text>
        <text class="copy">{{ t('imageAttributionsDirectRightsDescription') }}</text>
        <text class="notice">{{ t('imageAttributionsFamilyIllustrationNotice') }}</text>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import AppNavBar from '@/components/AppNavBar.vue'
import { IMAGE_ATTRIBUTIONS } from '@/config/image-attributions'
import { useI18nStore } from '@/store/i18n'
import { openExternalLink } from '@/utils/external-link'

const { t } = useI18nStore()

function open(url: string) {
  openExternalLink(url, () => uni.showToast({ title: t('openFailed'), icon: 'none' }))
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); display: flex; flex-direction: column; }
.body { flex: 1; padding: 0 32rpx calc(80rpx + var(--safe-bottom)); }
.card { margin-bottom: 24rpx; padding: 30rpx; border: 1rpx solid var(--border); border-radius: var(--radius); background: var(--card); }
.heading, .work, .asset, .copy, .notice, .label, .value { display: block; }
.heading { color: var(--text); font-size: 34rpx; font-weight: 700; }
.copy { margin-top: 16rpx; color: var(--text-sub); font-size: 27rpx; line-height: 1.7; }
.notice { margin-top: 14rpx; color: var(--text-dim); font-size: 23rpx; line-height: 1.65; }
.asset { color: var(--primary); font-size: 22rpx; font-weight: 700; letter-spacing: 1rpx; }
.work { margin-top: 8rpx; color: var(--text); font-size: 30rpx; font-weight: 700; line-height: 1.4; }
.detail-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 24rpx; margin-top: 18rpx; }
.detail-block { margin-top: 20rpx; padding-top: 20rpx; border-top: 1rpx solid var(--divider); }
.label { flex-shrink: 0; color: var(--text-dim); font-size: 23rpx; }
.value { color: var(--text-sub); font-size: 25rpx; line-height: 1.55; text-align: right; }
.block-value { margin-top: 8rpx; text-align: left; }
.links { display: flex; gap: 16rpx; margin-top: 22rpx; }
.link-button { flex: 1; min-height: 64rpx; margin: 0; padding: 0 18rpx; border: 1rpx solid var(--primary); border-radius: 32rpx; color: var(--primary); background: transparent; font-size: 24rpx; line-height: 62rpx; }
.link-button::after { border: none; }
.rights-card { margin-bottom: 0; }
</style>
