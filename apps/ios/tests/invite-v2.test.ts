import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  INVITE_DAILY_QUALIFIED_LIMIT,
  INVITE_FIXED_REWARD_CARD_HOURS,
  INVITE_REBATE_TIERS,
  buildInvitePolicyView,
  inviteCommissionStatusKey,
  inviteRecordStatusKey,
  inviteePhoneDisplayValue,
  recordRewardCardHours,
} from '../src/utils/invite-policy.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const invitePage = source('../src/pages/invite/index.vue')
const inviteApi = source('../src/api/invite.ts')
const requestApi = source('../src/api/request.ts')
const i18n = source('../src/store/i18n.ts')
const generatedI18n = source('../src/store/i18n_generated.ts')

test('invitation V2 keeps the approved fixed reward, daily cap, and referral purchase tiers', () => {
  assert.equal(INVITE_FIXED_REWARD_CARD_HOURS, 58)
  assert.equal(INVITE_DAILY_QUALIFIED_LIMIT, 5)
  assert.deepEqual(INVITE_REBATE_TIERS, [
    { minQualifiedCount: 0, ratePercent: 0 },
    { minQualifiedCount: 5, ratePercent: 2 },
    { minQualifiedCount: 10, ratePercent: 4 },
    { minQualifiedCount: 15, ratePercent: 6 },
    { minQualifiedCount: 20, ratePercent: 8 },
  ])
})

test('legacy invitation summaries never become V2 quota, tier, or reward data', () => {
  const policy = buildInvitePolicyView({
    policy_version: 'invite-first-order-v1',
    program_code: 'invite_first_order_reward',
    qualified_count: 12,
    current_tier: '20%',
    current_rate_bps: 2000,
    total_reward: 99,
    pending_count: 3,
    fixed_reward_card_hours: 58,
    daily_used: 0,
    daily_remaining: 5,
  })

  assert.equal(policy.v2DataAvailable, false)
  assert.equal(policy.dailyLimit, 5)
  assert.equal(policy.dailySlotsUsed, null)
  assert.equal(policy.qualifiedFriendCount, null)
  assert.equal(policy.currentRatePercent, null)
  assert.equal(policy.totalRewardCardHours, null)
})

test('V2 server fields drive the daily 0/5 state and friend tier progress', () => {
  const policy = buildInvitePolicyView({
    policy_version: 'invite-qualified-v2',
    fixed_reward_card_hours: 58,
    daily_limit: 5,
    daily_used: 0,
    daily_remaining: 5,
    qualified_count: 12,
    current_rate_bps: 400,
    fixed_reward_total: 116,
    fixed_reward_pending: 58,
    eligible_friend_spend_card_hours: 200,
    commission_pending: 8,
    commission_total: 16,
  })

  assert.equal(policy.v2DataAvailable, true)
  assert.equal(policy.dailySlotsUsed, 0)
  assert.equal(policy.dailySlotsRemaining, 5)
  assert.equal(policy.currentRatePercent, 4)
  assert.equal(policy.nextTier?.ratePercent, 6)
  assert.equal(policy.remainingToNextTier, 3)
  assert.equal(policy.tierProgressPercent, 80)
  assert.equal(policy.totalRewardCardHours, 116)
})

test('record status mapping covers qualification, quota, settlement, and reversal', () => {
  const record = (status: string, extra = {}) => ({
    id: 1,
    invitee_phone: '138****0000',
    status,
    reward_amount: 0,
    ...extra,
  })

  assert.equal(inviteRecordStatusKey(record('unverified')), 'inviteStatusAwaitingIdentity')
  assert.equal(inviteRecordStatusKey(record('registered')), 'inviteStatusAwaitingFirstOrder')
  assert.equal(inviteRecordStatusKey(record('qualified')), 'inviteStatusQualified')
  assert.equal(inviteRecordStatusKey(record('reviewing')), 'inviteStatusReviewing')
  assert.equal(inviteRecordStatusKey(record('daily_cap_exceeded', { qualification_status: 'daily_cap_exceeded' })), 'inviteStatusQuotaFull')
  assert.equal(inviteRecordStatusKey(record('rewarded')), 'inviteStatusRewarded')
  assert.equal(inviteRecordStatusKey(record('qualified', { fixed_reward_status: 'pending' })), 'inviteStatusPendingReward')
  assert.equal(inviteRecordStatusKey(record('qualified', { fixed_reward_status: 'settled' })), 'inviteStatusRewarded')
  assert.equal(inviteRecordStatusKey(record('qualified', { fixed_reward_status: 'forfeited' })), 'inviteStatusReversed')
  const commission = (status: 'pending' | 'settled' | 'forfeited') => ({
    id: 1,
    source_type: 'order' as const,
    order_id: 10,
    order_renewal_id: null,
    base_card_hours: 100,
    rate_bps: 400,
    reward_card_hours: 4,
    status,
    policy_version: 'invite-v2-2026-08',
  })
  assert.equal(inviteCommissionStatusKey(commission('pending')), 'inviteRebateStatusPending')
  assert.equal(inviteCommissionStatusKey(commission('settled')), 'inviteRebateStatusSettled')
  assert.equal(inviteCommissionStatusKey(commission('forfeited')), 'inviteRebateStatusReversed')
})

test('historical unbound phone text is localized instead of leaking a Chinese backend literal', () => {
  const record = (phone?: string) => ({ id: 1, invitee_phone: phone, status: 'legacy_v1', reward_amount: 0 })
  assert.equal(inviteePhoneDisplayValue(record(), 'No phone linked'), 'No phone linked')
  assert.equal(inviteePhoneDisplayValue(record('未绑定手机号'), 'No phone linked'), 'No phone linked')
  assert.equal(inviteePhoneDisplayValue(record('138****0000'), 'No phone linked'), '138****0000')
})

test('only an explicitly settled V2 fixed reward may fall back to 58 card-hours', () => {
  assert.equal(recordRewardCardHours({
    id: 1,
    status: 'rewarded',
    qualification_status: 'legacy_v1',
    reward_amount: 0,
  }, 58), 0)
  assert.equal(recordRewardCardHours({
    id: 2,
    status: 'rewarded',
    qualification_status: 'legacy_v1',
  }, 58), 0)
  assert.equal(recordRewardCardHours({
    id: 3,
    status: 'rewarded',
    qualification_status: 'legacy_v1',
    reward_amount: 18,
  }, 58), 18)
  assert.equal(recordRewardCardHours({
    id: 4,
    qualification_status: 'qualified',
    fixed_reward_status: 'settled',
    fixed_reward_amount: 0,
  }, 58), 58)
  assert.equal(recordRewardCardHours({
    id: 5,
    qualification_status: 'legacy_v1',
    fixed_reward_status: 'settled',
    fixed_reward_amount: 0,
  }, 58), 0)
})

test('invite page shows both mechanisms, visible compliance rules, and server-owned V2 data', () => {
  for (const marker of [
    'inviteV2FixedRewardBadge',
    'inviteTodayProgress',
    'dailySlotsUsed',
    'inviteFriendRebateTitle',
    'inviteTierProgress',
    'inviteFixedRewardRecords',
    'inviteFriendRebateRecords',
    'getInviteCommissions',
    'ApiRequestError',
    'inviteDailyQuotaRule',
    'inviteFirstLevelOnlyRule',
    'inviteNoEntryFeeRule',
    'inviteEligibleSpendRule',
    'inviteExcludedSpendRule',
    'inviteAntiAbuseRule',
    'inviteRewardRestriction',
    'fmtCardHours',
    'copyInviteLink',
    'loadMoreRecords',
    'inviteCommissionFriendSource',
  ]) assert.ok(invitePage.includes(marker), `invite page must retain ${marker}`)

  assert.doesNotMatch(invitePage, /current_tier|next_tier_hint|fmtCHn/)
  assert.doesNotMatch(invitePage, /1-5人15%|6-20人20%|21\+人25%/)
  assert.match(i18n, /累计合格一级好友达到 5 \/ 10 \/ 15 \/ 20 人/)
  assert.match(i18n, /仅计算你直接邀请的一级好友/)
  assert.match(i18n, /北京时间日期占用，不按注册日期/)
  assert.match(i18n, /当天第 6 位及以后只保留记录/)
  assert.match(i18n, /不支持提现、转赠或兑换现金/)
  assert.match(i18n, /Only friends you invite directly count/)
  assert.match(i18n, /identity verification/)
  assert.match(i18n, /referral purchase reward/)
  assert.doesNotMatch(invitePage + i18n, /—|real-name verification|friend-spend|Qualified ·/)
  assert.doesNotMatch(generatedI18n, /邀请码得88卡时|invite code for 88 CH/i)
  assert.match(invitePage, /Promise\.allSettled\([\s\S]*getInviteCommissions\(\)/)
  assert.match(invitePage, /statusCode === 404[\s\S]*!buildInvitePolicyView/)
  assert.match(invitePage, /commissionsResult\.status === 'rejected' && !commissionIsLegacy404/)
  assert.match(invitePage, /hero-badges \{[^}]*flex-wrap: wrap/)
})

test('mobile invite contract accepts V2 fields while retaining legacy response fields', () => {
  for (const field of [
    'fixed_reward_card_hours',
    'daily_used',
    'daily_remaining',
    'current_rate_bps',
    'commission_total',
    'commission_pending',
    'qualification_status',
    'invitee_phone_masked',
    'fixed_reward_amount',
  ]) assert.match(inviteApi, new RegExp(`${field}\\?`))
  assert.match(inviteApi, /items: InviteRecordItem\[\]/)
  assert.match(inviteApi, /reward_card_hours: number/)
  assert.match(inviteApi, /invitee_phone_masked\?: string/)
  assert.match(inviteApi, /url: '\/invite\/commissions'/)
  assert.match(requestApi, /export class ApiRequestError extends Error/)
  assert.match(requestApi, /new ApiRequestError\(msg, res\.statusCode\)/)
})
