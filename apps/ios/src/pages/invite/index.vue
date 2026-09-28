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
        <view class="card hero-card">
          <view class="hero-badges">
            <text class="hero-badge">{{ t('inviteV2FixedRewardBadge', { amount: policy.fixedRewardCardHours }) }}</text>
            <text class="hero-badge secondary">{{ t('inviteV2DailyLimitBadge', { count: policy.dailyLimit }) }}</text>
          </view>
          <text class="hero-title">{{ t('inviteV2HeroTitle') }}</text>
          <text class="hero-subtitle">{{ t('inviteV2HeroSubtitle') }}</text>
          <view class="code-panel">
            <view class="code-copy">
              <text class="code-label">{{ t('inviteCodeLabel') }}</text>
              <text class="code">{{ info?.code || t('notAvailableShort') }}</text>
            </view>
            <view
              class="copy-button"
              role="button"
              :aria-label="t('copyInviteCode')"
              @tap="copyCode"
            >{{ t('copyInviteCode') }}</view>
          </view>
          <view class="link-button" role="button" :aria-label="t('copyInviteLink')" @tap="copyInviteLink">
            {{ t('copyInviteLink') }}
          </view>
        </view>

        <view v-if="info && !info.rewards_enabled" class="card reward-warning">
          {{ t('rewardProgramDisabled') }}
        </view>
        <view v-else-if="!policy.v2DataAvailable" class="card reward-warning">
          {{ t('inviteV2DataPending') }}
        </view>

        <view class="card daily-card">
          <view class="section-row">
            <view>
              <text class="section-eyebrow">{{ t('inviteTodayProgress') }}</text>
              <text class="section-title">{{ dailyProgressText }}</text>
            </view>
            <text class="remaining-pill">{{ remainingSlotsText }}</text>
          </view>
          <view
            class="daily-progress"
            role="progressbar"
            :aria-label="t('inviteTodayProgress')"
            :aria-valuemin="0"
            :aria-valuemax="policy.dailyLimit"
            :aria-valuenow="policy.dailySlotsUsed ?? 0"
          >
            <view
              v-for="slot in policy.dailyLimit"
              :key="slot"
              class="daily-segment"
              :class="{ filled: policy.dailySlotsUsed != null && slot <= policy.dailySlotsUsed }"
            ></view>
          </view>
          <view class="daily-meta">
            <text>{{ t('inviteTodayUsed', { count: displayCount(policy.dailySlotsUsed) }) }}</text>
            <text>{{ t('inviteBeijingTimeShort') }}</text>
          </view>
          <text class="reset-hint">{{ t('inviteDailyResetHint') }}</text>
        </view>

        <view class="card reward-card">
          <view class="section-row compact">
            <view>
              <text class="section-eyebrow">{{ t('inviteFixedRewardTitle') }}</text>
              <text class="section-title small">{{ t('inviteFixedRewardSubtitle') }}</text>
            </view>
            <text class="reward-mark">+{{ policy.fixedRewardCardHours }}</text>
          </view>
          <view class="metric-grid">
            <view class="metric-item">
              <text class="metric-value">{{ displayCardHours(policy.totalRewardCardHours) }}</text>
              <text class="metric-label">{{ t('inviteCumulativeReward') }}</text>
            </view>
            <view class="metric-item">
              <text class="metric-value">{{ displayCardHours(policy.pendingFixedRewardCardHours) }}</text>
              <text class="metric-label">{{ t('invitePendingReward') }}</text>
            </view>
            <view class="metric-item">
              <text class="metric-value">{{ displayCardHours(policy.friendRebateSettledCardHours) }}</text>
              <text class="metric-label">{{ t('inviteCumulativePurchaseReward') }}</text>
            </view>
          </view>
          <view class="restriction-note">
            <text class="restriction-icon">!</text>
            <text>{{ t('inviteRewardRestriction') }}</text>
          </view>
        </view>

        <view class="card rebate-card">
          <view class="section-row compact">
            <view>
              <text class="section-eyebrow">{{ t('inviteFriendRebateTitle') }}</text>
              <text class="section-title small">{{ t('inviteFriendRebateSubtitle') }}</text>
            </view>
            <view class="rate-pill">
              <text class="rate-value">{{ displayRate(policy.currentRatePercent) }}</text>
              <text class="rate-label">{{ t('inviteCurrentRate') }}</text>
            </view>
          </view>

          <view class="tier-summary">
            <text>{{ t('inviteQualifiedFriendCount', { count: displayCount(policy.qualifiedFriendCount) }) }}</text>
            <text v-if="policy.remainingToNextTier != null && policy.nextTier">
              {{ t('inviteNextTierHint', { count: policy.remainingToNextTier, rate: policy.nextTier.ratePercent }) }}
            </text>
            <text v-else-if="policy.qualifiedFriendCount != null">{{ t('inviteMaxTierReached') }}</text>
            <text v-else>{{ t('inviteRuleDataUnavailableShort') }}</text>
          </view>
          <view class="tier-progress" role="progressbar" :aria-label="t('inviteTierProgress')">
            <view class="tier-progress-fill" :style="tierProgressStyle"></view>
          </view>
          <view class="tier-scale">
            <view
              v-for="tier in policy.tiers"
              :key="tier.ratePercent"
              class="tier-node"
              :class="{
                reached: policy.qualifiedFriendCount != null && policy.qualifiedFriendCount >= tier.minQualifiedCount,
                current: policy.currentRatePercent === tier.ratePercent,
              }"
            >
              <text class="tier-rate">{{ tier.ratePercent }}%</text>
              <text class="tier-count">{{ tier.minQualifiedCount === 0 ? t('inviteTierStart') : t('inviteTierPeople', { count: tier.minQualifiedCount }) }}</text>
            </view>
          </view>

          <view class="rebate-metrics">
            <view class="rebate-metric">
              <text>{{ displayCardHours(policy.eligibleFriendSpendCardHours) }}</text>
              <text class="rebate-label">{{ t('inviteEligibleFriendSpend') }}</text>
            </view>
            <view class="rebate-metric">
              <text>{{ displayCardHours(policy.friendRebatePendingCardHours) }}</text>
              <text class="rebate-label">{{ t('inviteFriendRebatePending') }}</text>
            </view>
            <view class="rebate-metric">
              <text>{{ displayCardHours(policy.friendRebateSettledCardHours) }}</text>
              <text class="rebate-label">{{ t('inviteFriendRebateSettled') }}</text>
            </view>
          </view>
        </view>

        <SectionHeader :title="t('inviteRulesTitle')" />
        <view class="card rules-card">
          <view v-for="(rule, index) in inviteRules" :key="rule" class="rule-item">
            <text class="rule-index">{{ index + 1 }}</text>
            <text class="rule-text">{{ rule }}</text>
          </view>
        </view>

        <view class="record-heading">
          <text class="record-title">{{ t('inviteRecordsTitle') }}</text>
          <view class="record-tabs">
            <view
              class="record-tab"
              :class="{ active: activeRecordTab === 'fixed' }"
              role="button"
              @tap="activeRecordTab = 'fixed'"
            >{{ t('inviteFixedRewardRecords') }}</view>
            <view
              class="record-tab"
              :class="{ active: activeRecordTab === 'rebate' }"
              role="button"
              @tap="activeRecordTab = 'rebate'"
            >{{ t('inviteFriendRebateRecords') }}</view>
          </view>
        </view>

        <view v-if="recordLoadError" class="card record-error">
          <text>{{ t('inviteRecordsLoadFailed') }}</text>
          <view role="button" @tap="load">{{ t('retry') }}</view>
        </view>
        <template v-else-if="activeRecordTab === 'fixed'">
          <view v-if="!fixedRewardRecords.length" class="card empty-card">
            <EmptyState :text="t('inviteNoFixedRewardRecords')" />
          </view>
          <view v-for="record in fixedRewardRecords" :key="`fixed-${record.id}`" class="card record-row">
            <view class="record-main">
              <text class="record-identity">{{ inviteePhoneDisplayValue(record, t('invitePhoneUnbound')) }}</text>
              <text class="record-date">{{ recordDate(record) }}</text>
            </view>
            <view class="record-side">
              <text class="record-status" :class="recordStatusClass(inviteRecordStatusKey(record))">
                {{ t(inviteRecordStatusKey(record)) }}
              </text>
              <text v-if="recordReward(record) > 0" class="record-amount">
                +{{ fmtCardHours(recordReward(record)) }} {{ t('cardHour') }}
              </text>
            </view>
          </view>
        </template>
        <template v-else>
          <view v-if="!friendRebateRecords.length" class="card empty-card">
            <EmptyState :text="t('inviteNoFriendRebateRecords')" />
          </view>
          <view v-for="record in friendRebateRecords" :key="`rebate-${record.id}`" class="card record-row">
            <view class="record-main">
              <text class="record-identity">{{ commissionSourceLabel(record) }}</text>
              <text class="record-date">{{ friendRecordDetail(record) }}</text>
            </view>
            <view class="record-side">
              <text class="record-status" :class="recordStatusClass(inviteCommissionStatusKey(record))">
                {{ t(inviteCommissionStatusKey(record)) }}
              </text>
              <text v-if="record.reward_card_hours > 0" class="record-amount">
                +{{ fmtCardHours(record.reward_card_hours) }} {{ t('cardHour') }}
              </text>
            </view>
          </view>
        </template>
        <view v-if="activeHasMore" class="load-more" role="button" @tap="loadMoreRecords">
          {{ loadingMore ? t('inviteLoadingMore') : t('inviteLoadMore') }}
        </view>
      </template>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  getInviteCommissions,
  getInviteSummary,
  getInviteRecords,
  type InviteCommissionItem,
  type InviteSummary,
  type InviteRecordItem,
} from '@/api/invite'
import { ApiRequestError } from '@/api/request'
import { fmtCardHours, formatDate } from '@/utils/format'
import {
  buildInvitePolicyView,
  commissionRatePercent,
  inviteRecordStatusKey,
  inviteCommissionStatusKey,
  inviteePhoneDisplayValue,
  recordRewardCardHours,
} from '@/utils/invite-policy'
import AppNavBar from '@/components/AppNavBar.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { useI18nStore } from '@/store/i18n'

const { t } = useI18nStore()
const info = ref<InviteSummary | null>(null)
const fixedRewardRecords = ref<InviteRecordItem[]>([])
const friendRebateRecords = ref<InviteCommissionItem[]>([])
const fixedRewardTotal = ref(0)
const friendRebateTotal = ref(0)
const fixedRewardPage = ref(1)
const friendRebatePage = ref(1)
const loadingMore = ref(false)
const activeRecordTab = ref<'fixed' | 'rebate'>('fixed')
const loading = ref(true)
const loadError = ref(false)
const recordLoadError = ref(false)
const policy = computed(() => buildInvitePolicyView(info.value))
const dailyProgressText = computed(() => `${displayCount(policy.value.dailySlotsUsed)}/${policy.value.dailyLimit}`)
const remainingSlotsText = computed(() => policy.value.dailySlotsRemaining == null
  ? t('inviteRuleDataUnavailableShort')
  : t('inviteRemainingSlots', { count: policy.value.dailySlotsRemaining }))
const tierProgressStyle = computed(() => ({ width: `${policy.value.tierProgressPercent ?? 0}%` }))
const activeHasMore = computed(() => activeRecordTab.value === 'fixed'
  ? fixedRewardRecords.value.length < fixedRewardTotal.value
  : friendRebateRecords.value.length < friendRebateTotal.value)
const inviteRules = computed(() => [
  t('inviteQualificationRule', { amount: policy.value.fixedRewardCardHours, count: policy.value.dailyLimit }),
  t('inviteDailyQuotaRule', { amount: policy.value.fixedRewardCardHours }),
  t('inviteFriendTierRule'),
  t('inviteFirstLevelOnlyRule'),
  t('inviteNoEntryFeeRule'),
  t('inviteEligibleSpendRule'),
  t('inviteExcludedSpendRule'),
  t('inviteAntiAbuseRule'),
  t('inviteRewardRestriction'),
])

function uniqueRecords(records: InviteRecordItem[]): InviteRecordItem[] {
  const seen = new Set<string>()
  return records.filter((record) => {
    const key = String(record.id)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function uniqueCommissionRecords(records: InviteCommissionItem[]): InviteCommissionItem[] {
  const seen = new Set<string>()
  return records.filter((record) => {
    const key = String(record.id)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

async function load() {
  loading.value = true
  loadError.value = false
  recordLoadError.value = false
  const [summaryResult, recordsResult, commissionsResult] = await Promise.allSettled([
    getInviteSummary(),
    getInviteRecords(),
    getInviteCommissions(),
  ])
  if (summaryResult.status === 'fulfilled') info.value = summaryResult.value
  if (recordsResult.status === 'fulfilled') {
    const payload = recordsResult.value
    fixedRewardRecords.value = uniqueRecords(payload.items ?? [])
    fixedRewardTotal.value = payload.total ?? fixedRewardRecords.value.length
    fixedRewardPage.value = 1
  }
  if (commissionsResult.status === 'fulfilled') {
    friendRebateRecords.value = uniqueCommissionRecords(commissionsResult.value.items ?? [])
    friendRebateTotal.value = commissionsResult.value.total ?? friendRebateRecords.value.length
    friendRebatePage.value = 1
  }
  const commissionIsLegacy404 = commissionsResult.status === 'rejected'
    && commissionsResult.reason instanceof ApiRequestError
    && commissionsResult.reason.statusCode === 404
    && !buildInvitePolicyView(summaryResult.status === 'fulfilled' ? summaryResult.value : null).v2DataAvailable
  if (commissionIsLegacy404) friendRebateRecords.value = []
  loadError.value = summaryResult.status === 'rejected'
  recordLoadError.value = recordsResult.status === 'rejected'
    || (commissionsResult.status === 'rejected' && !commissionIsLegacy404)
  loading.value = false
}
onShow(() => load())

function copyCode() {
  if (!info.value?.code) return
  uni.setClipboardData({
    data: info.value.code,
    success: () => uni.showToast({ title: t('inviteCodeCopied'), icon: 'success' }),
  })
}

function copyInviteLink() {
  if (!info.value?.code) return
  const link = `https://wod.kai.com/register?invite_code=${encodeURIComponent(info.value.code)}`
  uni.setClipboardData({
    data: link,
    success: () => uni.showToast({ title: t('inviteLinkCopied'), icon: 'success' }),
  })
}

async function loadMoreRecords() {
  if (loadingMore.value || !activeHasMore.value) return
  loadingMore.value = true
  try {
    if (activeRecordTab.value === 'fixed') {
      const nextPage = fixedRewardPage.value + 1
      const payload = await getInviteRecords(nextPage)
      fixedRewardRecords.value = uniqueRecords([...fixedRewardRecords.value, ...(payload.items ?? [])])
      fixedRewardTotal.value = payload.total ?? fixedRewardRecords.value.length
      fixedRewardPage.value = nextPage
    } else {
      const nextPage = friendRebatePage.value + 1
      const payload = await getInviteCommissions(nextPage)
      friendRebateRecords.value = uniqueCommissionRecords([...friendRebateRecords.value, ...(payload.items ?? [])])
      friendRebateTotal.value = payload.total ?? friendRebateRecords.value.length
      friendRebatePage.value = nextPage
    }
  } catch {
    uni.showToast({ title: t('inviteRecordsLoadFailed'), icon: 'none' })
  } finally {
    loadingMore.value = false
  }
}

function displayCount(value: number | null): string {
  return value == null ? t('notAvailableShort') : String(value)
}

function displayRate(value: number | null): string {
  return value == null ? t('notAvailableShort') : `${value}%`
}

function displayCardHours(value: number | null): string {
  return value == null ? t('notAvailableShort') : `${fmtCardHours(value)} ${t('cardHour')}`
}

function recordDate(record: InviteRecordItem): string {
  return formatDate(record.rewarded_at ?? record.qualified_at ?? record.created_at)
}

function recordReward(record: InviteRecordItem): number {
  return recordRewardCardHours(record, policy.value.fixedRewardCardHours)
}

function friendRecordDetail(record: InviteCommissionItem): string {
  return t('inviteFriendRebateRecordDetail', {
    amount: fmtCardHours(record.base_card_hours),
    rate: commissionRatePercent(record),
  })
}

function commissionSourceLabel(record: InviteCommissionItem): string {
  const id = record.source_type === 'renewal' ? record.order_renewal_id : record.order_id
  const source = record.source_type === 'renewal'
    ? t('inviteCommissionRenewal', { id: id ?? t('notAvailableShort') })
    : t('inviteCommissionOrder', { id: id ?? t('notAvailableShort') })
  return record.invitee_phone_masked
    ? t('inviteCommissionFriendSource', { phone: record.invitee_phone_masked, source })
    : source
}

function recordStatusClass(key: string): string {
  if (/Rewarded|Settled/.test(key)) return 'success'
  if (/Reversed|Ineligible|QuotaFull/.test(key)) return 'danger'
  if (/Pending|Reviewing/.test(key)) return 'pending'
  return 'muted'
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 28rpx calc(132rpx + var(--safe-bottom)); }
.card { background: var(--card); border: 1rpx solid var(--card-border); border-radius: 28rpx; }
.load-state { min-height: 420rpx; display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-size: 26rpx; }
.load-error { flex-direction: column; gap: 18rpx; }
.load-retry { min-height: 68rpx; padding: 0 28rpx; display: flex; align-items: center; color: var(--primary); border: 1rpx solid var(--primary); border-radius: 18rpx; font-weight: 700; }

.hero-card { margin: 24rpx 0 20rpx; padding: 32rpx; color: #fff; border: none; overflow: hidden; background: linear-gradient(145deg, #087e91 0%, #0baec2 58%, #79dbe4 100%); box-shadow: 0 18rpx 44rpx rgba(7, 129, 148, 0.16); }
.hero-badges { display: flex; gap: 12rpx; flex-wrap: wrap; }
.hero-badge { padding: 8rpx 16rpx; border-radius: 999rpx; background: rgba(255,255,255,0.2); font-size: 21rpx; font-weight: 700; }
.hero-badge.secondary { background: rgba(5,48,57,0.2); }
.hero-title { display: block; margin-top: 28rpx; font-size: 38rpx; line-height: 1.25; font-weight: 800; }
.hero-subtitle { display: block; margin-top: 10rpx; color: rgba(255,255,255,0.82); font-size: 23rpx; line-height: 1.55; }
.code-panel { display: flex; align-items: center; gap: 20rpx; margin-top: 30rpx; padding: 20rpx 22rpx; border: 1rpx solid rgba(255,255,255,0.28); border-radius: 22rpx; background: rgba(4,62,72,0.2); }
.code-copy { min-width: 0; flex: 1; }
.code-label { display: block; color: rgba(255,255,255,0.72); font-size: 20rpx; }
.code { display: block; margin-top: 4rpx; color: #fff; font-size: 42rpx; font-weight: 850; letter-spacing: 5rpx; font-variant-numeric: tabular-nums; }
.copy-button { min-height: 68rpx; padding: 0 24rpx; display: flex; align-items: center; justify-content: center; border-radius: 18rpx; color: #076779; background: #fff; font-size: 24rpx; font-weight: 800; }
.link-button { min-height: 66rpx; margin-top: 14rpx; display: flex; align-items: center; justify-content: center; border: 1rpx solid rgba(255,255,255,0.42); border-radius: 18rpx; color: #fff; background: rgba(4,62,72,0.18); font-size: 23rpx; font-weight: 750; }

.reward-warning { margin-bottom: 20rpx; padding: 22rpx 26rpx; color: #9b6a08; background: rgba(250, 191, 42, 0.1); border-color: rgba(250, 191, 42, 0.26); font-size: 23rpx; line-height: 1.55; }
.daily-card, .reward-card, .rebate-card { margin-bottom: 20rpx; padding: 28rpx; }
.section-row { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; }
.section-row.compact { align-items: flex-start; }
.section-eyebrow { display: block; color: var(--text-sub); font-size: 21rpx; letter-spacing: 1rpx; }
.section-title { display: block; margin-top: 4rpx; color: var(--text); font-size: 38rpx; font-weight: 850; font-variant-numeric: tabular-nums; }
.section-title.small { font-size: 28rpx; line-height: 1.35; }
.remaining-pill { padding: 9rpx 16rpx; color: var(--primary); background: var(--primary-soft, rgba(12,174,195,0.1)); border-radius: 999rpx; font-size: 21rpx; font-weight: 700; }
.daily-progress { display: flex; gap: 10rpx; margin-top: 24rpx; }
.daily-segment { height: 16rpx; flex: 1; border-radius: 999rpx; background: var(--card-border); }
.daily-segment.filled { background: linear-gradient(90deg, var(--primary), #5fd3df); }
.daily-meta { display: flex; justify-content: space-between; margin-top: 18rpx; color: var(--text-sub); font-size: 22rpx; }
.reset-hint { display: block; margin-top: 10rpx; color: var(--text-dim); font-size: 20rpx; }

.reward-mark { color: var(--up); font-size: 42rpx; font-weight: 850; }
.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); margin-top: 24rpx; border: 1rpx solid var(--card-border); border-radius: 20rpx; overflow: hidden; }
.metric-item { min-width: 0; padding: 22rpx 8rpx; text-align: center; }
.metric-item + .metric-item { border-left: 1rpx solid var(--card-border); }
.metric-value { display: block; color: var(--text); font-size: 25rpx; font-weight: 800; font-variant-numeric: tabular-nums; word-break: break-all; }
.metric-label { display: block; margin-top: 8rpx; color: var(--text-sub); font-size: 19rpx; }
.restriction-note { display: flex; align-items: flex-start; gap: 12rpx; margin-top: 20rpx; padding: 18rpx; color: var(--text-sub); background: var(--bg); border-radius: 16rpx; font-size: 21rpx; line-height: 1.5; }
.restriction-icon { width: 30rpx; height: 30rpx; flex: 0 0 30rpx; display: flex; align-items: center; justify-content: center; color: #fff; background: var(--primary); border-radius: 50%; font-size: 19rpx; font-weight: 800; }

.rate-pill { min-width: 110rpx; padding: 12rpx 18rpx; text-align: center; border-radius: 18rpx; background: rgba(12,174,195,0.1); }
.rate-value { display: block; color: var(--primary); font-size: 34rpx; font-weight: 850; }
.rate-label { display: block; margin-top: 2rpx; color: var(--text-sub); font-size: 18rpx; }
.tier-summary { display: flex; justify-content: space-between; gap: 20rpx; margin-top: 24rpx; color: var(--text-sub); font-size: 21rpx; }
.tier-summary text:last-child { color: var(--primary); text-align: right; }
.tier-progress { height: 10rpx; margin-top: 16rpx; overflow: hidden; border-radius: 999rpx; background: var(--card-border); }
.tier-progress-fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg, #08a6bb, #48cedb); transition: width 0.2s ease; }
.tier-scale { display: flex; justify-content: space-between; margin-top: 18rpx; }
.tier-node { width: 19%; padding: 12rpx 2rpx; text-align: center; border-radius: 14rpx; color: var(--text-dim); background: var(--bg); }
.tier-node.reached { color: var(--text); }
.tier-node.current { color: var(--primary); background: rgba(12,174,195,0.11); box-shadow: inset 0 0 0 1rpx rgba(12,174,195,0.26); }
.tier-rate { display: block; font-size: 25rpx; font-weight: 850; }
.tier-count { display: block; margin-top: 3rpx; font-size: 18rpx; }
.rebate-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10rpx; margin-top: 22rpx; }
.rebate-metric { min-width: 0; padding: 18rpx 6rpx; text-align: center; border-radius: 16rpx; background: var(--bg); }
.rebate-metric text { display: block; color: var(--text); font-size: 23rpx; font-weight: 800; word-break: break-all; }
.rebate-label { display: block; margin-top: 7rpx; color: var(--text-sub) !important; font-size: 18rpx !important; font-weight: 400 !important; }

.rules-card { padding: 26rpx 28rpx; margin-bottom: 26rpx; }
.rule-item { display: flex; align-items: flex-start; gap: 16rpx; padding: 14rpx 0; border-bottom: 1rpx solid var(--card-border); }
.rule-item:first-child { padding-top: 0; }
.rule-item:last-child { padding-bottom: 0; border-bottom: none; }
.rule-index { width: 34rpx; height: 34rpx; flex: 0 0 34rpx; display: flex; align-items: center; justify-content: center; color: var(--primary); background: rgba(12,174,195,0.1); border-radius: 50%; font-size: 19rpx; font-weight: 800; }
.rule-text { flex: 1; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; }

.record-heading { margin: 8rpx 0 18rpx; }
.record-title { display: block; color: var(--text); font-size: 29rpx; font-weight: 800; }
.record-tabs { display: flex; margin-top: 16rpx; padding: 6rpx; border-radius: 18rpx; background: var(--card); border: 1rpx solid var(--card-border); }
.record-tab { min-height: 60rpx; flex: 1; display: flex; align-items: center; justify-content: center; color: var(--text-sub); border-radius: 14rpx; font-size: 22rpx; font-weight: 700; }
.record-tab.active { color: var(--primary); background: rgba(12,174,195,0.11); }
.record-error { display: flex; justify-content: space-between; padding: 24rpx 28rpx; color: var(--text-sub); font-size: 22rpx; }
.record-error view { color: var(--primary); font-weight: 700; }
.empty-card { padding: 54rpx 0; }
.record-row { display: flex; align-items: center; justify-content: space-between; gap: 18rpx; margin-bottom: 12rpx; padding: 22rpx 26rpx; }
.record-main { min-width: 0; flex: 1; }
.record-identity { display: block; overflow: hidden; color: var(--text); font-size: 25rpx; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
.record-date { display: block; margin-top: 7rpx; color: var(--text-dim); font-size: 19rpx; }
.record-side { display: flex; flex-direction: column; align-items: flex-end; gap: 8rpx; }
.record-status { padding: 5rpx 12rpx; border-radius: 10rpx; font-size: 19rpx; }
.record-status.success { color: var(--up); background: rgba(25,166,91,0.1); }
.record-status.danger { color: var(--down); background: rgba(231,70,70,0.09); }
.record-status.pending { color: var(--primary); background: rgba(12,174,195,0.1); }
.record-status.muted { color: var(--text-sub); background: var(--bg); }
.record-amount { color: var(--up); font-size: 23rpx; font-weight: 800; }
.load-more { min-height: 76rpx; margin: 18rpx 0 8rpx; display: flex; align-items: center; justify-content: center; border: 1rpx solid var(--card-border); border-radius: 20rpx; color: var(--primary); background: var(--card); font-size: 23rpx; font-weight: 750; }
</style>
