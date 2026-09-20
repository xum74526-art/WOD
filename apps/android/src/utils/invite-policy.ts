import type { InviteCommissionItem, InviteRecordItem, InviteRebateTier, InviteSummary } from '../api/invite'

export const INVITE_FIXED_REWARD_CARD_HOURS = 58
export const INVITE_DAILY_QUALIFIED_LIMIT = 5

export interface InviteTierView {
  minQualifiedCount: number
  ratePercent: number
}

export const INVITE_REBATE_TIERS: readonly InviteTierView[] = [
  { minQualifiedCount: 0, ratePercent: 0 },
  { minQualifiedCount: 5, ratePercent: 2 },
  { minQualifiedCount: 10, ratePercent: 4 },
  { minQualifiedCount: 15, ratePercent: 6 },
  { minQualifiedCount: 20, ratePercent: 8 },
]

export interface InvitePolicyView {
  v2DataAvailable: boolean
  fixedRewardCardHours: number
  dailyLimit: number
  dailySlotsUsed: number | null
  dailySlotsRemaining: number | null
  qualifiedFriendCount: number | null
  totalRewardCardHours: number | null
  pendingFixedRewardCardHours: number | null
  eligibleFriendSpendCardHours: number | null
  friendRebatePendingCardHours: number | null
  friendRebateSettledCardHours: number | null
  tiers: InviteTierView[]
  currentRatePercent: number | null
  nextTier: InviteTierView | null
  remainingToNextTier: number | null
  tierProgressPercent: number | null
}

function numeric(value: unknown): number | undefined {
  if (value == null || value === '') return undefined
  const parsed = Number(typeof value === 'string' ? value.replace('%', '').trim() : value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    const parsed = numeric(value)
    if (parsed != null) return parsed
  }
  return undefined
}

function nonNegative(value: unknown, fallback = 0): number {
  return Math.max(0, firstNumber(value) ?? fallback)
}

function integer(value: unknown, fallback: number): number {
  return Math.max(0, Math.floor(firstNumber(value) ?? fallback))
}

function optionalNonNegative(...values: unknown[]): number | null {
  const parsed = firstNumber(...values)
  return parsed == null ? null : Math.max(0, parsed)
}

function optionalInteger(...values: unknown[]): number | null {
  const parsed = firstNumber(...values)
  return parsed == null ? null : Math.max(0, Math.floor(parsed))
}

function tierThreshold(tier: InviteRebateTier): number {
  return tier.min_qualified_count
}

function tierRate(tier: InviteRebateTier): number {
  return nonNegative(tier.rate_bps) / 100
}

function normalizeTiers(summary?: Partial<InviteSummary> | null): InviteTierView[] {
  const source = summary?.tiers
  if (!source?.length) return INVITE_REBATE_TIERS.map((tier) => ({ ...tier }))

  const allowedRates = new Set(INVITE_REBATE_TIERS.map((tier) => tier.ratePercent))
  const normalized = source
    .map((tier) => ({ minQualifiedCount: tierThreshold(tier), ratePercent: tierRate(tier) }))
    .filter((tier) => tier.minQualifiedCount >= 0 && allowedRates.has(tier.ratePercent))
    .map((tier) => ({
      minQualifiedCount: Math.floor(tier.minQualifiedCount),
      ratePercent: tier.ratePercent,
    }))
    .sort((a, b) => a.minQualifiedCount - b.minQualifiedCount)

  const unique = normalized.filter((tier, index) => (
    index === 0 || tier.minQualifiedCount !== normalized[index - 1]?.minQualifiedCount
  ))
  if (!unique.length || unique[0]?.minQualifiedCount !== 0 || unique[0]?.ratePercent !== 0) {
    return INVITE_REBATE_TIERS.map((tier) => ({ ...tier }))
  }
  return unique
}

/**
 * Presentation compatibility for the legacy `/invite/summary` response.
 * The server still owns qualification, quota, settlement and amounts. The
 * fallbacks can be removed once invitation-v2 fields are mandatory in OpenAPI.
 */
export function buildInvitePolicyView(summary?: Partial<InviteSummary> | null): InvitePolicyView {
  const version = `${summary?.policy_version ?? ''}`.toLowerCase()
  const program = `${summary?.program_code ?? ''}`.toLowerCase()
  const v2DataAvailable = Boolean(summary && (
    version.includes('v2')
    || program.includes('v2')
  ))
  const fixedRewardCardHours = nonNegative(
    v2DataAvailable
      ? summary?.fixed_reward_card_hours
      : undefined,
    INVITE_FIXED_REWARD_CARD_HOURS,
  )
  const dailyLimit = Math.max(
    1,
    v2DataAvailable ? integer(summary?.daily_limit, INVITE_DAILY_QUALIFIED_LIMIT) : INVITE_DAILY_QUALIFIED_LIMIT,
  )
  const dailySlotsRaw = v2DataAvailable
    ? optionalInteger(summary?.daily_used, summary?.daily_slots_used)
    : null
  const dailySlotsUsed = dailySlotsRaw == null ? null : Math.min(dailyLimit, dailySlotsRaw)
  const explicitRemaining = v2DataAvailable
    ? optionalInteger(summary?.daily_remaining, summary?.daily_slots_remaining)
    : null
  const dailySlotsRemaining = explicitRemaining != null
    ? Math.min(dailyLimit, explicitRemaining)
    : dailySlotsUsed == null ? null : dailyLimit - dailySlotsUsed
  const qualifiedFriendCount = v2DataAvailable
    ? optionalInteger(summary?.qualified_count)
    : null
  const tiers = normalizeTiers(summary)
  const serverRateBps = firstNumber(summary?.current_rate_bps)
  const serverRate = v2DataAvailable && serverRateBps != null
    ? nonNegative(serverRateBps) / 100
    : undefined
  const currentRatePercent = serverRate != null && tiers.some((tier) => tier.ratePercent === serverRate)
    ? serverRate
    : null
  const derivedNextTier = qualifiedFriendCount == null
    ? null
    : tiers.find((tier) => tier.minQualifiedCount > qualifiedFriendCount) ?? null
  const nextTier = derivedNextTier
  const remainingToNextTier = qualifiedFriendCount == null || !nextTier
    ? qualifiedFriendCount != null && !nextTier ? 0 : null
    : Math.max(0, nextTier.minQualifiedCount - qualifiedFriendCount)
  const tierProgressPercent = qualifiedFriendCount == null
    ? null
    : nextTier
      ? Math.min(100, Math.round((qualifiedFriendCount / Math.max(1, nextTier.minQualifiedCount)) * 100))
      : 100
  const totalRewardCardHours = v2DataAvailable ? optionalNonNegative(summary?.fixed_reward_total) : null

  return {
    v2DataAvailable,
    fixedRewardCardHours,
    dailyLimit,
    dailySlotsUsed,
    dailySlotsRemaining,
    qualifiedFriendCount,
    totalRewardCardHours,
    pendingFixedRewardCardHours: v2DataAvailable
      ? optionalNonNegative(summary?.fixed_reward_pending)
      : null,
    eligibleFriendSpendCardHours: v2DataAvailable
      ? optionalNonNegative(
        summary?.eligible_friend_spend_card_hours,
        summary?.total_eligible_consumption_card_hours,
      )
      : null,
    friendRebatePendingCardHours: v2DataAvailable
      ? optionalNonNegative(summary?.commission_pending)
      : null,
    friendRebateSettledCardHours: v2DataAvailable
      ? optionalNonNegative(summary?.commission_total)
      : null,
    tiers,
    currentRatePercent,
    nextTier,
    remainingToNextTier,
    tierProgressPercent,
  }
}

function statusTokens(record: InviteRecordItem): string {
  return [
    record.status,
    record.legacy_status,
    record.qualification_status,
    record.qualification_reason,
    record.fixed_reward_status,
  ].filter(Boolean).join(' ').toLowerCase()
}

export function inviteRecordStatusKey(record: InviteRecordItem): string {
  const fixedRewardStatus = `${record.fixed_reward_status ?? ''}`.toLowerCase()
  if (fixedRewardStatus === 'forfeited') return 'inviteStatusReversed'
  if (fixedRewardStatus === 'settled') return 'inviteStatusRewarded'
  if (fixedRewardStatus === 'pending') return 'inviteStatusPendingReward'
  const status = statusTokens(record)
  if (/revers|revok|refund|forfeit/.test(status)) return 'inviteStatusReversed'
  if (/quota[_ -]?(full|reached)|cap[_ -]?(reached|exceeded)|daily[_ -]?(limit|cap[_ -]?exceeded)/.test(status)) return 'inviteStatusQuotaFull'
  if (/ineligible|reject|invalid|self[_ -]?invite|related[_ -]?account/.test(status)) return 'inviteStatusIneligible'
  if (/review|risk|audit/.test(status)) return 'inviteStatusReviewing'
  if (/settled|rewarded|credited/.test(status)) return 'inviteStatusRewarded'
  if (/pending[_ -]?(reward|settlement)|ordered/.test(status)) return 'inviteStatusPendingReward'
  if (/qualified/.test(status)) return 'inviteStatusQualified'
  if (/registered|first[_ -]?order|pending[_ -]?order/.test(status)) return 'inviteStatusAwaitingFirstOrder'
  return 'inviteStatusAwaitingIdentity'
}

export function inviteePhoneDisplayValue(record: InviteRecordItem, unboundLabel: string): string {
  const value = `${record.invitee_phone_masked ?? record.invitee_phone ?? ''}`.trim()
  return !value || value === '未绑定手机号' ? unboundLabel : value
}

export function inviteCommissionStatusKey(record: InviteCommissionItem): string {
  if (record.status === 'forfeited') return 'inviteRebateStatusReversed'
  if (record.status === 'settled') return 'inviteRebateStatusSettled'
  return 'inviteRebateStatusPending'
}

export function recordRewardCardHours(record: InviteRecordItem, fixedRewardCardHours: number): number {
  const explicit = firstNumber(
    record.fixed_reward_amount,
    record.reward_amount,
  )
  if (explicit != null && explicit > 0) return explicit

  const qualificationStatus = `${record.qualification_status ?? ''}`.trim().toLowerCase()
  const fixedRewardStatus = `${record.fixed_reward_status ?? ''}`.trim().toLowerCase()
  const isSettledV2FixedReward = qualificationStatus !== 'legacy_v1'
    && fixedRewardStatus === 'settled'
  return isSettledV2FixedReward ? fixedRewardCardHours : 0
}

export function commissionRatePercent(record: InviteCommissionItem): number {
  return nonNegative(record.rate_bps) / 100
}
