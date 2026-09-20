export type InviteTier = {
  minimumFriends: number;
  maximumFriends: number | null;
  ratePercent: number;
};

export type InviteSummary = {
  isV2: boolean;
  code: string;
  invitedCount: number | null;
  qualifiedCount: number | null;
  pendingIdentityCount: number | null;
  pendingOrderCount: number | null;
  dailyCapExceededCount: number | null;
  fixedRewardCardHours: number;
  dailyLimit: number;
  dailySlotsUsed: number | null;
  dailySlotsRemaining: number | null;
  nextResetAt: string | null;
  eligibleFriendCount: number | null;
  eligibleFriendSpendCardHours: number | null;
  friendRebateCurrentRate: number | null;
  friendRebateTiers: InviteTier[];
  nextTier: InviteTier | null;
  fixedRewardTotal: number | null;
  fixedRewardPending: number | null;
  friendRebatePending: number | null;
  friendRebateSettled: number | null;
  rewardsEnabled: boolean;
  withdrawable: boolean;
  transferable: boolean;
  policyVersion: string;
};

export type InviteRecordKind = "fixed_reward" | "friend_rebate" | "legacy";

export type InviteRecord = {
  key: string;
  id: number | string;
  kind: InviteRecordKind;
  inviteePhone: string;
  sourceType: string;
  orderId: number | string | null;
  orderRenewalId: number | string | null;
  status: string;
  amountCardHours: number;
  eligibleConsumptionCardHours: number;
  ratePercent: number;
  quotaEligible: boolean | null;
  exclusionReason: string;
  createdAt: string | null;
  settledAt: string | null;
  policyVersion: string;
};

export type InviteRecordBundle = {
  total: number;
  fixedRewardRecords: InviteRecord[];
  friendRebateRecords: InviteRecord[];
};

export const INVITE_V2_TIERS: InviteTier[] = [
  { minimumFriends: 0, maximumFriends: 4, ratePercent: 0 },
  { minimumFriends: 5, maximumFriends: 9, ratePercent: 2 },
  { minimumFriends: 10, maximumFriends: 14, ratePercent: 4 },
  { minimumFriends: 15, maximumFriends: 19, ratePercent: 6 },
  { minimumFriends: 20, maximumFriends: null, ratePercent: 8 },
];

type UnknownRecord = Record<string, unknown>;

function object(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function numberFrom(source: UnknownRecord, keys: string[], fallback = 0) {
  for (const key of keys) {
    const raw = source[key];
    if (raw === null || raw === undefined || raw === "") continue;
    const value = Number(raw);
    if (Number.isFinite(value)) return value;
  }
  return fallback;
}

function optionalNumberFrom(source: UnknownRecord, keys: string[]) {
  const value = numberFrom(source, keys, Number.NaN);
  return Number.isFinite(value) ? value : null;
}

function optionalIntegerFrom(source: UnknownRecord, keys: string[]) {
  const value = optionalNumberFrom(source, keys);
  return value === null ? null : Math.max(0, Math.trunc(value));
}

function optionalNonnegativeNumberFrom(source: UnknownRecord, keys: string[]) {
  const value = optionalNumberFrom(source, keys);
  return value === null ? null : Math.max(0, value);
}

function integerFrom(source: UnknownRecord, keys: string[], fallback = 0) {
  return Math.max(0, Math.trunc(numberFrom(source, keys, fallback)));
}

function stringFrom(source: UnknownRecord, keys: string[], fallback = "") {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return fallback;
}

function booleanFrom(source: UnknownRecord, keys: string[], fallback: boolean) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "boolean") return value;
    if (value === 1 || value === "1" || value === "true") return true;
    if (value === 0 || value === "0" || value === "false") return false;
  }
  return fallback;
}

function normalizeTier(value: unknown): InviteTier | null {
  const source = object(value);
  const minimumRaw = numberFrom(source, ["min_qualified_count"], Number.NaN);
  if (!Number.isFinite(minimumRaw) || minimumRaw < 0) return null;
  const minimumFriends = Math.trunc(minimumRaw);
  const maximumRaw = numberFrom(source, ["max_qualified_count"], Number.NaN);
  const bps = numberFrom(source, ["rate_bps"], Number.NaN);
  if (!Number.isFinite(bps) || bps < 0) return null;
  return {
    minimumFriends,
    maximumFriends: Number.isFinite(maximumRaw) ? Math.max(minimumFriends, Math.trunc(maximumRaw)) : null,
    ratePercent: bps / 100,
  };
}

function normalizeTiers(value: unknown) {
  if (!Array.isArray(value)) return INVITE_V2_TIERS.map((tier) => ({ ...tier }));
  const tiers = value.map(normalizeTier).filter((tier): tier is InviteTier => tier !== null);
  if (!tiers.length) return INVITE_V2_TIERS.map((tier) => ({ ...tier }));
  const sorted = tiers.sort((a, b) => a.minimumFriends - b.minimumFriends);
  return sorted.map((tier, index) => ({
    ...tier,
    maximumFriends: tier.maximumFriends ?? (sorted[index + 1] ? sorted[index + 1].minimumFriends - 1 : null),
  }));
}

export function nextInviteTier(count: number, tiers: InviteTier[] = INVITE_V2_TIERS) {
  return tiers.find((tier) => tier.minimumFriends > count) || null;
}

export function normalizeInviteSummary(value: unknown): InviteSummary {
  const source = object(value);
  const policyVersion = stringFrom(source, ["policy_version"], "");
  const isV2 = /^invite-v2(?:-|$)/i.test(policyVersion);
  const dailyLimit = integerFrom(source, ["daily_limit"], 5) || 5;
  const dailyUsedValue = isV2 ? optionalIntegerFrom(source, ["daily_used", "daily_slots_used"]) : null;
  const dailyRemainingValue = isV2 ? optionalIntegerFrom(source, ["daily_remaining", "daily_slots_remaining"]) : null;
  const dailySlotsUsed = dailyUsedValue === null ? null : Math.min(dailyLimit, dailyUsedValue);
  const eligibleFriendCount = isV2
    ? optionalIntegerFrom(source, ["qualified_count"])
    : null;
  const tiers = isV2
    ? normalizeTiers(source.tiers)
    : INVITE_V2_TIERS.map((tier) => ({ ...tier }));
  const nextTier = eligibleFriendCount !== null ? nextInviteTier(eligibleFriendCount, tiers) : null;
  const currentRateBps = numberFrom(source, ["current_rate_bps"], Number.NaN);

  return {
    isV2,
    code: stringFrom(source, ["code"], ""),
    invitedCount: isV2 ? optionalIntegerFrom(source, ["invited_count"]) : null,
    qualifiedCount: isV2 ? optionalIntegerFrom(source, ["qualified_count"]) : null,
    pendingIdentityCount: isV2 ? optionalIntegerFrom(source, ["pending_identity_count"]) : null,
    pendingOrderCount: isV2 ? optionalIntegerFrom(source, ["pending_order_count"]) : null,
    dailyCapExceededCount: isV2 ? optionalIntegerFrom(source, ["daily_cap_exceeded_count"]) : null,
    fixedRewardCardHours: isV2 ? Math.max(0, numberFrom(source, ["fixed_reward_card_hours"], 58)) : 58,
    dailyLimit,
    dailySlotsUsed,
    dailySlotsRemaining: dailyRemainingValue === null ? null : Math.min(dailyLimit, dailyRemainingValue),
    nextResetAt: isV2 ? stringFrom(source, ["next_reset_at"], "") || null : null,
    eligibleFriendCount,
    eligibleFriendSpendCardHours: isV2
      ? optionalNonnegativeNumberFrom(source, ["eligible_friend_spend_card_hours", "total_eligible_consumption_card_hours"])
      : null,
    friendRebateCurrentRate: !isV2
      ? null
      : Number.isFinite(currentRateBps)
        ? Math.max(0, currentRateBps / 100) : null,
    friendRebateTiers: tiers,
    nextTier,
    fixedRewardTotal: isV2 ? optionalNonnegativeNumberFrom(source, ["fixed_reward_total"]) : null,
    fixedRewardPending: isV2 ? optionalNonnegativeNumberFrom(source, ["fixed_reward_pending"]) : null,
    friendRebatePending: isV2 ? optionalNonnegativeNumberFrom(source, ["commission_pending"]) : null,
    friendRebateSettled: isV2 ? optionalNonnegativeNumberFrom(source, ["commission_total"]) : null,
    rewardsEnabled: isV2 && booleanFrom(source, ["rewards_enabled"], false),
    withdrawable: isV2 && booleanFrom(source, ["rewards_withdrawable"], false),
    transferable: isV2 && booleanFrom(source, ["rewards_transferable"], false),
    policyVersion,
  };
}

function recordKind(source: UnknownRecord, forcedKind?: InviteRecordKind): InviteRecordKind {
  if (forcedKind) return forcedKind;
  if ("qualification_status" in source || "fixed_reward_status" in source) return "fixed_reward";
  return "legacy";
}

function normalizeRecord(value: unknown, index: number, forcedKind?: InviteRecordKind): InviteRecord {
  const source = object(value);
  const qualificationStatus = stringFrom(source, ["qualification_status"]);
  const fixedRewardStatus = stringFrom(source, ["fixed_reward_status"]);
  const legacyV1 = qualificationStatus === "legacy_v1";
  const kind = legacyV1 ? "legacy" : recordKind(source, forcedKind);
  const id = stringFrom(source, ["id"], String(index + 1));
  const policyVersion = stringFrom(source, ["policy_version"]);
  const rateBps = numberFrom(source, ["rate_bps"], Number.NaN);
  const dailySlot = numberFrom(source, ["daily_slot"], Number.NaN);
  return {
    key: `${kind}:${id}:${policyVersion}`,
    id,
    kind,
    inviteePhone: stringFrom(source, ["invitee_phone_masked", "invitee_phone"], ""),
    sourceType: stringFrom(source, ["source_type"]),
    orderId: stringFrom(source, ["order_id"], "") || null,
    orderRenewalId: stringFrom(source, ["order_renewal_id"], "") || null,
    status: qualificationStatus && !["qualified", "legacy_v1"].includes(qualificationStatus)
      ? qualificationStatus
      : fixedRewardStatus || qualificationStatus || stringFrom(source, ["status", "legacy_status"], "pending_qualification"),
    amountCardHours: Math.max(0, numberFrom(source, kind === "friend_rebate" ? ["reward_card_hours"] : ["fixed_reward_amount", "reward_amount"])),
    eligibleConsumptionCardHours: Math.max(0, numberFrom(source, ["base_card_hours"])),
    ratePercent: Number.isFinite(rateBps) ? Math.max(0, rateBps / 100) : 0,
    quotaEligible: qualificationStatus === "daily_cap_exceeded"
      ? false
      : Number.isFinite(dailySlot) ? dailySlot > 0 : null,
    exclusionReason: stringFrom(source, ["qualification_reason"]),
    createdAt: stringFrom(source, ["qualified_at", "created_at"], "") || null,
    settledAt: stringFrom(source, ["settled_at", "rewarded_at"], "") || null,
    policyVersion,
  };
}

export function normalizeInviteRecordBundle(value: unknown, commissions?: unknown): InviteRecordBundle {
  const source = object(value);
  const commissionSource = object(commissions);
  const all: InviteRecord[] = [];
  const append = (items: unknown, kind?: InviteRecordKind) => {
    if (!Array.isArray(items)) return;
    items.forEach((item, index) => all.push(normalizeRecord(item, index, kind)));
  };
  append(source.items);
  append(commissionSource.items, "friend_rebate");

  const unique = [...new Map(all.map((record) => [record.key, record])).values()];
  const fixedRewardRecords = unique.filter((record) => record.kind !== "friend_rebate");
  const friendRebateRecords = unique.filter((record) => record.kind === "friend_rebate");
  return {
    total: integerFrom(source, ["total"], unique.length),
    fixedRewardRecords,
    friendRebateRecords,
  };
}
