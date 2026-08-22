<template>
  <view class="page">
    <AppNavBar :title="t('inviteFriends')" />
    <view class="shell">
      <view v-if="loading" class="load-state">{{ t('loading') }}</view>
      <view v-else-if="loadError" class="load-state load-error">
        <text>{{ t('dataUnavailable') }}</text>
        <view class="load-retry" role="button" @tap="load">{{ t('retry') }}</view>
      </view>
      <template v-else>
      <!-- 邀请码卡片 -->
      <view class="card code-card">
        <text class="cl">{{ t('k_6015d540') }}</text>
        <text class="code">{{ info?.code || '...' }}</text>
        <view class="btn" @tap="copyCode">{{ t('k_50bcf090') }}</view>
      </view>

      <view v-if="info && !info.rewards_enabled" class="card reward-warning">{{ t('inviteRewardsUnavailable') }}</view>
      <view v-else-if="info?.reward_mode === 'test_card_hours'" class="card reward-warning active">{{ t('closedTestInviteNotice') }}</view>

      <!-- 数据看板 -->
      <view class="card stats-grid">
        <view class="stat-item">
          <text class="sv">{{ info?.invited_count ?? 0 }}</text>
          <text class="sl">{{ t('k_59c15455') }}</text>
        </view>
        <view class="stat-item">
          <text class="sv">{{ info?.qualified_count ?? 0 }}</text>
          <text class="sl">{{ t('inviteQualified') }}</text>
        </view>
        <view class="stat-item">
          <text class="sv">{{ info?.unverified_count ?? 0 }}</text>
          <text class="sl">{{ t('inviteAwaitingVerification') }}</text>
        </view>
        <view class="stat-item">
          <text class="sv reward">{{ fmtCHn(info?.total_reward ?? 0) }}</text>
          <text class="sl">{{ t('k_d64b4818') }}</text>
        </view>
        <view class="stat-item">
          <text class="sv">{{ info?.pending_count ?? 0 }}</text>
          <text class="sl">{{ t('k_c4e8bacf') }}</text>
        </view>
        <view class="stat-item">
          <text class="sv">{{ info?.rewarded_count ?? 0 }}</text>
          <text class="sl">{{ t('k_ca7204ca') }}</text>
        </view>
      </view>

      <!-- 当前等级 -->
      <view class="card tier-card">
        <view class="tier-row">
          <text class="tl">{{ t('k_f7245327') }}</text>
          <text class="tv">{{ info?.current_tier || '15%' }}</text>
        </view>
        <text class="th">{{ tr(info?.next_tier_hint || '') }}</text>
      </view>

      <!-- 奖励规则 -->
      <SectionHeader :title="t('k_a91cc41a')" />
      <view class="card rules-card">
        <view class="rule-item">
          <text class="dot"></text>
          <text class="rt">{{ t('closedTestInviteNotice') }}</text>
        </view>
        <view class="rule-item">
          <text class="dot"></text>
          <text class="rt">{{ t('好友首单完成，你获 {rate} 返利', { rate: info?.current_tier || '15%' }) }}</text>
        </view>
        <view class="rule-item">
          <text class="dot"></text>
          <text class="rt">{{ t('阶梯加成：1-5人15%、6-20人20%、21+人25%') }}</text>
        </view>
      </view>

      <!-- 邀请记录 -->
      <SectionHeader :title="t('k_893d6ae5')" />
      <view v-if="!records.length" class="card ph"><EmptyState text="暂无邀请记录，快去邀请好友吧" /></view>
      <view v-for="r in records" :key="r.id" class="card rec-row">
        <view class="rec-left">
          <text class="rec-phone">{{ r.invitee_phone }}</text>
          <text class="rec-date">{{ formatDate(r.created_at) }}</text>
        </view>
        <view class="rec-right">
          <text v-if="r.status === 'rewarded'" class="rec-reward">+{{ fmtCHn(r.reward_amount) }} {{ t('cardHour') }}</text>
          <text v-else-if="r.status === 'ordered'" class="rec-status s-ordered">{{ t('inviteStatusOrdered') }}</text>
          <text v-else-if="r.status === 'unverified'" class="rec-status s-pending">{{ t('inviteStatusUnverified') }}</text>
          <text v-else class="rec-status s-pending">{{ t('inviteStatusRegistered') }}</text>
        </view>
      </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getInviteSummary, getInviteRecords, type InviteSummary, type InviteRecordItem } from '@/api/invite'
import { fmtCHn, formatDate } from '@/utils/format'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'

const { t, tr } = useI18nStore()
const info = ref<InviteSummary | null>(null)
const records = ref<InviteRecordItem[]>([])
const loading = ref(true)
const loadError = ref(false)

async function load() {
  loading.value = true
  loadError.value = false
  const [summaryResult, recordsResult] = await Promise.allSettled([getInviteSummary(), getInviteRecords()])
  if (summaryResult.status === 'fulfilled') info.value = summaryResult.value
  if (recordsResult.status === 'fulfilled') records.value = recordsResult.value.items
  loadError.value = summaryResult.status === 'rejected' || recordsResult.status === 'rejected'
  loading.value = false
}
onShow(() => load())

function copyCode() {
  uni.setClipboardData({
    data: info.value?.code || '',
    success: () => uni.showToast({ title: t('邀请码已复制'), icon: 'success' }),
  })
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border-radius: var(--radius); border: 1rpx solid var(--card-border); }
.load-state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: var(--radius); font-weight: 700; }

.code-card { padding: 56rpx 32rpx; text-align: center; margin: 24rpx 0; background: linear-gradient(135deg, var(--primary) 0%, var(--primary) 100%); border: none; }
.cl { color: rgba(255,255,255,0.8); font-size: 26rpx; }
.code { display: block; color: #fff; font-size: 64rpx; font-weight: 800; letter-spacing: 6rpx; margin: 20rpx 0; font-variant-numeric: tabular-nums; }
.btn { display: inline-block; color: #fff; border: 1rpx solid rgba(255,255,255,0.5); padding: 16rpx 48rpx; border-radius: 999rpx; font-size: 28rpx; }

.stats-grid { display: flex; margin-bottom: 20rpx; }
.reward-warning { color: var(--text-sub); padding: 24rpx 28rpx; margin-bottom: 20rpx; font-size: 24rpx; line-height: 1.6; }
.reward-warning.active { color: var(--primary); background: var(--card-border); }
.stats-grid { flex-wrap: wrap; }
.stat-item { width: 33.333%; box-sizing: border-box; text-align: center; padding: 28rpx 8rpx; border-bottom: 1rpx solid var(--card-border); }
.stat-item:nth-child(3n + 2), .stat-item:nth-child(3n + 3) { border-left: 1rpx solid var(--card-border); }
.stat-item:nth-last-child(-n + 3) { border-bottom: none; }
.sv { display: block; color: var(--text); font-size: 40rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.sv.reward { color: var(--up); }
.sl { display: block; color: var(--text-sub); font-size: 22rpx; margin-top: 8rpx; }

.tier-card { padding: 28rpx 32rpx; margin-bottom: 24rpx; }
.tier-row { display: flex; justify-content: space-between; align-items: center; }
.tl { color: var(--text-sub); font-size: 26rpx; }
.tv { color: var(--primary); font-size: 32rpx; font-weight: 700; }
.th { display: block; color: var(--text-dim); font-size: 22rpx; margin-top: 8rpx; }

.rules-card { padding: 24rpx 32rpx; margin-bottom: 24rpx; }
.rule-item { display: flex; align-items: flex-start; gap: 16rpx; margin-bottom: 16rpx; }
.rule-item:last-child { margin-bottom: 0; }
.dot { width: 12rpx; height: 12rpx; border-radius: 6rpx; background: var(--primary); flex-shrink: 0; margin-top: 8rpx; }
.rt { color: var(--text); font-size: 24rpx; line-height: 1.6; }
.hl { color: var(--up); font-weight: 700; }

.ph { padding: 60rpx 0; }
.rec-row { display: flex; justify-content: space-between; align-items: center; padding: 24rpx 32rpx; margin-bottom: 12rpx; }
.rec-left { flex: 1; }
.rec-phone { color: var(--text); font-size: 28rpx; font-weight: 600; display: block; }
.rec-date { color: var(--text-dim); font-size: 22rpx; display: block; margin-top: 4rpx; }
.rec-right { text-align: right; }
.rec-reward { color: var(--up); font-size: 28rpx; font-weight: 700; }
.rec-status { font-size: 24rpx; padding: 4rpx 16rpx; border-radius: 8rpx; }
.s-ordered { color: var(--primary); background: var(--card-border); }
.s-pending { color: var(--text-dim); background: var(--bg); }
</style>
