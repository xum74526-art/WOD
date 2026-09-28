import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  INVITE_V2_TIERS,
  normalizeInviteRecordBundle,
  normalizeInviteSummary,
} from "../lib/invite-v2.ts";

test("Referral V2 summary uses server ledger fields and basis-point tiers", () => {
  const summary = normalizeInviteSummary({
    code: "WODABC123",
    policy_version: "invite-v2-2026-08",
    rewards_enabled: true,
    rewards_withdrawable: false,
    rewards_transferable: false,
    fixed_reward_card_hours: 58,
    daily_limit: 5,
    daily_used: 3,
    daily_remaining: 2,
    daily_slots_used: 4,
    daily_slots_remaining: 1,
    next_reset_at: "2026-08-27T00:00:00+08:00",
    invited_count: 17,
    qualified_count: 15,
    pending_identity_count: 1,
    pending_order_count: 1,
    daily_cap_exceeded_count: 2,
    current_rate_bps: 600,
    tiers: [
      { min_qualified_count: 0, max_qualified_count: 4, rate_bps: 0 },
      { min_qualified_count: 5, max_qualified_count: 9, rate_bps: 200 },
      { min_qualified_count: 10, max_qualified_count: 14, rate_bps: 400 },
      { min_qualified_count: 15, max_qualified_count: 19, rate_bps: 600 },
      { min_qualified_count: 20, max_qualified_count: null, rate_bps: 800 },
    ],
    fixed_reward_total: 696,
    fixed_reward_pending: 58,
    commission_total: 43.25,
    commission_pending: 8.5,
    eligible_friend_spend_card_hours: 1081.25,
  });

  assert.equal(summary.isV2, true);
  assert.equal(summary.dailySlotsUsed, 3);
  assert.equal(summary.dailySlotsRemaining, 2);
  assert.equal(summary.eligibleFriendCount, 15);
  assert.equal(summary.friendRebateCurrentRate, 6);
  assert.equal(summary.nextTier?.minimumFriends, 20);
  assert.equal(summary.nextTier?.ratePercent, 8);
  assert.equal(summary.friendRebateTiers.at(-1)?.maximumFriends, null);
  assert.equal(summary.fixedRewardTotal, 696);
  assert.equal(summary.fixedRewardPending, 58);
  assert.equal(summary.friendRebateSettled, 43.25);
  assert.equal(summary.friendRebatePending, 8.5);
  assert.equal(summary.eligibleFriendSpendCardHours, 1081.25);
  assert.equal(summary.withdrawable, false);
  assert.equal(summary.transferable, false);
});

test("legacy referral response never becomes a calculated V2 tier or balance", () => {
  const summary = normalizeInviteSummary({
    policy_version: "invite-first-order-v1",
    qualified_count: 20,
    current_tier: "20%",
    total_reward: 99,
    pending_reward: 12,
    rewards_enabled: true,
  });

  assert.equal(summary.isV2, false);
  assert.equal(summary.eligibleFriendCount, null);
  assert.equal(summary.friendRebateCurrentRate, null);
  assert.equal(summary.dailySlotsUsed, null);
  assert.equal(summary.dailySlotsRemaining, null);
  assert.equal(summary.fixedRewardTotal, null);
  assert.equal(summary.fixedRewardPending, null);
  assert.equal(summary.friendRebateSettled, null);
  assert.equal(summary.friendRebatePending, null);
  assert.equal(summary.rewardsEnabled, false);
  assert.deepEqual(summary.friendRebateTiers, INVITE_V2_TIERS);
});

test("partial V2 responses do not turn missing ledger metrics into zero", () => {
  const summary = normalizeInviteSummary({
    policy_version: "invite-v2-2026-08",
    fixed_reward_card_hours: 58,
    daily_limit: 5,
    tiers: INVITE_V2_TIERS.map((tier) => ({
      min_qualified_count: tier.minimumFriends,
      max_qualified_count: tier.maximumFriends,
      rate_bps: tier.ratePercent * 100,
    })),
  });

  assert.equal(summary.dailySlotsUsed, null);
  assert.equal(summary.dailySlotsRemaining, null);
  assert.equal(summary.eligibleFriendCount, null);
  assert.equal(summary.friendRebateCurrentRate, null);
  assert.equal(summary.fixedRewardTotal, null);
  assert.equal(summary.fixedRewardPending, null);
  assert.equal(summary.friendRebateSettled, null);
  assert.equal(summary.friendRebatePending, null);
  assert.equal(summary.eligibleFriendSpendCardHours, null);
  assert.equal(summary.friendRebateTiers.at(-1)?.maximumFriends, null);
});

test("qualification records and commission records stay separated", () => {
  const records = normalizeInviteRecordBundle({
    total: 2,
    items: [
      {
        id: 10,
        invitee_phone_masked: "138****0001",
        qualification_status: "qualified",
        daily_slot: 2,
        fixed_reward_amount: 58,
        fixed_reward_status: "settled",
        policy_version: "invite-v2-2026-08",
        created_at: "2026-08-26T08:00:00Z",
      },
      {
        id: 9,
        invitee_phone: "138****0002",
        qualification_status: "legacy_v1",
        reward_amount: 12,
        created_at: "2026-08-25T08:00:00Z",
      },
    ],
  }, {
    total: 2,
    items: [
      {
        id: 23,
        invitee_phone_masked: "138****0001",
        source_type: "order",
        order_id: 88,
        base_card_hours: 100,
        rate_bps: 400,
        reward_card_hours: 4,
        status: "settled",
        policy_version: "invite-v2-2026-08",
      },
      {
        id: 24,
        source_type: "renewal",
        order_id: 88,
        order_renewal_id: 109,
        base_card_hours: 50,
        rate_bps: 400,
        reward_card_hours: 2,
        status: "settled",
        policy_version: "invite-v2-2026-08",
      },
    ],
  });

  assert.equal(records.fixedRewardRecords.length, 2);
  assert.equal(records.fixedRewardRecords[0].kind, "fixed_reward");
  assert.equal(records.fixedRewardRecords[0].amountCardHours, 58);
  assert.equal(records.fixedRewardRecords[1].kind, "legacy");
  assert.equal(records.friendRebateRecords.length, 2);
  assert.equal(records.friendRebateRecords[0].orderId, "88");
  assert.equal(records.friendRebateRecords[0].eligibleConsumptionCardHours, 100);
  assert.equal(records.friendRebateRecords[0].ratePercent, 4);
  assert.equal(records.friendRebateRecords[0].amountCardHours, 4);
  assert.equal(records.friendRebateRecords[0].inviteePhone, "138****0001");
  assert.equal(records.friendRebateRecords[1].sourceType, "renewal");
  assert.equal(records.friendRebateRecords[1].orderRenewalId, "109");
  assert.equal(records.fixedRewardTotal, 2);
  assert.equal(records.friendRebateTotal, 2);
  assert.equal(records.total, 4);
});

test("Web referral page exposes both mechanisms and the approved compliance boundaries", () => {
  const component = fs.readFileSync(new URL("../components/referral-workspace.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(component, /邀请达标奖励/);
  assert.match(component, /好友消费返佣/);
  assert.match(component, /名额按好友完成“实名 \+ 首笔有效订单”的北京时间日期占用，不按注册日期计算/);
  assert.match(component, /第 6 位及以后仍保留邀请关系，但不发 58 卡时/);
  assert.match(component, /仅计算一级好友/);
  assert.match(component, /不要求缴纳入门费/);
  assert.match(component, /禁止自邀和关联账号/);
  assert.match(component, /不可提现或转赠/);
  assert.match(component, /summary\.isV2/);
  assert.match(api, /\/invite\/commissions\?page=1&page_size=50/);
  assert.match(api, /Promise\.allSettled/);
  assert.match(api, /!summary\.isV2 && commissionsResult\.reason instanceof ApiError/);
  assert.match(locale, /"invite\.fixed\.creditNote": "58 card hours enter the in-app spending balance"/);
  assert.match(locale, /"invite\.rebate\.rule": "Only completed, eligible consumption by first-level friends/);
  assert.match(locale, /"invite\.records\.unboundPhone": "No phone number linked"/);
  assert.match(locale, /"invite\.records\.renewalReference": "Renewal #\{id\}"/);
  assert.match(component, /normalized === "未绑定手机号"/);
  assert.match(component, /row\.sourceType === "renewal" && row\.orderRenewalId/);
  assert.match(component, /invite\.records\.renewalReference/);
  assert.match(component, /shareInvite/);
  assert.match(component, /loadMoreRecords/);
  assert.doesNotMatch(`${component}\n${locale}`, /15%.*20%.*25%|first-order rebate rate/i);
  assert.doesNotMatch(component, /[—–]/);
});
