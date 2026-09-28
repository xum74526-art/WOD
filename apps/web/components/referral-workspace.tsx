"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle,
  ClockCountdown,
  Coins,
  Copy,
  Gift,
  LockKey,
  Receipt,
  ShareNetwork,
  ShieldCheck,
  TrendUp,
  UserCheck,
  UsersThree,
  WarningCircle,
} from "@phosphor-icons/react";
import { useI18n } from "@/components/locale-root";
import { errorMessage } from "@/lib/commerce-ui";
import { getInviteBundle, getInviteCommissionPage, getInviteRecordPage, type InviteRecord, type InviteSummary } from "@/lib/mobile-business-api";
import { formatFinancialAmount } from "@/lib/financial-format";
import styles from "./referral-workspace.module.css";

type RecordTab = "fixed" | "rebate";

function amount(value: unknown, locale: string) {
  return formatFinancialAmount(value as number | string | null | undefined, locale);
}

function rate(value: unknown, locale: string) {
  const number = Number(value || 0);
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(Number.isFinite(number) ? number : 0);
}

function optionalAmount(value: number | null, locale: string) {
  return value === null ? "-" : amount(value, locale);
}

function date(value: string | null, locale: string) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(parsed);
}

function resetTime(value: string | null, locale: string) {
  if (!value) return "00:00 (UTC+8)";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "00:00 (UTC+8)";
  const result = new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(parsed);
  return `${result} (UTC+8)`;
}

function statusText(status: string, isCommission: boolean, t: ReturnType<typeof useI18n>["t"]) {
  const normalized = String(status || "").trim().toLowerCase();
  const states: Record<string, [string, string]> = {
    unverified: ["invite.status.pendingIdentity", "待完成实名"],
    registered: ["invite.status.pendingOrder", "待完成首笔有效订单"],
    pending_qualification: ["invite.status.pendingQualification", "待完成资格条件"],
    pending_identity: ["invite.status.pendingIdentity", "待完成实名"],
    pending_order: ["invite.status.pendingOrder", "待完成首笔有效订单"],
    risk_review: ["invite.status.riskReview", "风控审核中"],
    risk_rejected: ["invite.status.riskRejected", "风控未通过"],
    ordered: ["invite.status.pendingReward", "已达标，奖励待入账"],
    qualified_pending_reward: ["invite.status.pendingReward", "已达标，奖励待入账"],
    rewarded: ["invite.status.rewarded", "已奖励"],
    qualified: ["invite.status.qualified", "已达标"],
    quota_full: ["invite.status.quotaFull", "当日名额已满"],
    daily_cap_exceeded: ["invite.status.quotaFull", "当日名额已满"],
    ineligible: ["invite.status.ineligible", "不符合奖励条件"],
    not_eligible: ["invite.status.ineligible", "不符合奖励条件"],
    pending: isCommission ? ["invite.status.commissionPending", "返佣待结算"] : ["invite.status.pendingReward", "已达标，奖励待入账"],
    settled: isCommission ? ["invite.status.commissionSettled", "返佣已结算"] : ["invite.status.rewarded", "已奖励"],
    not_applicable: ["invite.status.notApplicable", "不适用固定奖励"],
    forfeited: ["invite.status.forfeited", "已失效"],
    revoked: ["invite.status.revoked", "已撤销"],
    legacy_v1: ["invite.status.legacy", "历史规则记录"],
  };
  const entry = states[normalized];
  return entry ? t(entry[0], entry[1]) : status || t("invite.status.unknown", "状态待确认");
}

function exclusionText(reason: string, t: ReturnType<typeof useI18n>["t"]) {
  const normalized = String(reason || "").trim().toLowerCase();
  const reasons: Record<string, [string, string]> = {
    verified_identity_required: ["invite.reason.identityRequired", "需先完成实名认证"],
    first_cash_backed_order_required: ["invite.reason.firstOrderRequired", "需完成首笔真实充值支持订单"],
    verified_identity_and_first_cash_order: ["invite.reason.qualified", "实名认证与首笔有效订单均已满足"],
    daily_qualified_limit_reached: ["invite.exclusion.dailyLimit", "当日 5 个合格名额已满"],
    self_invite: ["invite.exclusion.selfInvite", "自邀不参与奖励"],
    same_verified_identity: ["invite.exclusion.relatedAccount", "与邀请人实名认证身份重复"],
    identity_comparison_unavailable: ["invite.reason.riskReview", "身份风控校验暂不可用，等待复核"],
  };
  const entry = reasons[normalized];
  return entry ? t(entry[0], entry[1]) : reason;
}

function inviteeText(value: string, t: ReturnType<typeof useI18n>["t"]) {
  const normalized = String(value || "").trim();
  if (normalized === "未绑定手机号") return t("invite.records.unboundPhone", "未绑定手机号");
  return normalized || t("invite.records.maskedFriend", "已脱敏好友");
}

function recordReference(row: InviteRecord, t: ReturnType<typeof useI18n>["t"]) {
  if (row.kind !== "friend_rebate") return inviteeText(row.inviteePhone, t);
  if (row.sourceType === "renewal" && row.orderRenewalId) {
    return t("invite.records.renewalReference", "续费 #{id}", { id: row.orderRenewalId });
  }
  if (row.sourceType === "order" && row.orderId) {
    return t("invite.records.orderReference", "订单 #{id}", { id: row.orderId });
  }
  if (row.orderRenewalId) return t("invite.records.renewalReference", "续费 #{id}", { id: row.orderRenewalId });
  if (row.orderId) return t("invite.records.orderReference", "订单 #{id}", { id: row.orderId });
  return inviteeText(row.inviteePhone, t);
}

function RecordRow({ row, summary }: { row: InviteRecord; summary: InviteSummary }) {
  const { dateLocale, t } = useI18n();
  const isCommission = row.kind === "friend_rebate";
  const isLegacy = row.kind === "legacy";
  const fallbackAmount = !isCommission && !isLegacy && row.status === "rewarded"
    ? summary.fixedRewardCardHours
    : 0;
  const displayAmount = row.amountCardHours || fallbackAmount;
  const reason = exclusionText(row.exclusionReason, t);
  const positiveReason = row.exclusionReason === "verified_identity_and_first_cash_order";

  return <article className={styles.recordRow}>
    <div className={styles.recordIdentity}>
      <span className={styles.recordIcon}>{isCommission ? <TrendUp size={17}/> : <UserCheck size={17}/>}</span>
      <span>
        <strong>{recordReference(row, t)}</strong>
        <small>{statusText(row.status, isCommission, t)}</small>
      </span>
    </div>
    <div className={styles.recordBasis}>
      {isCommission ? <>
        <small>{t("invite.records.eligibleConsumption", "有效消费")}</small>
        <strong>{amount(row.eligibleConsumptionCardHours, dateLocale)} {t("invite.unit.cardHours", "卡时")}</strong>
        <span>{row.sourceType === "renewal" ? t("invite.records.sourceRenewal", "续费") : t("invite.records.sourceOrder", "订单")} / {rate(row.ratePercent, dateLocale)}%</span>
      </> : <>
        <small>{isLegacy ? t("invite.records.legacy", "历史邀请奖励") : t("invite.records.qualification", "实名及首单资格")}</small>
        <strong>{row.quotaEligible === false ? t("invite.records.outsideQuota", "不占奖励名额") : t("invite.records.firstLevel", "一级好友")}</strong>
      </>}
    </div>
    <div className={styles.recordValue}>
      <strong>{displayAmount > 0 ? `+${amount(displayAmount, dateLocale)}` : "-"}</strong>
      <small>{t("invite.unit.cardHours", "卡时")}</small>
      <time>{date(row.settledAt || row.createdAt, dateLocale)}</time>
    </div>
    {reason && <p className={`${styles.recordReason} ${["risk_rejected", "daily_cap_exceeded", "forfeited"].includes(row.status) ? styles.recordReasonNegative : ""}`}>{positiveReason ? <CheckCircle size={14}/> : <WarningCircle size={14}/>} {reason}</p>}
  </article>;
}

export function ReferralWorkspace() {
  const { dateLocale, t } = useI18n();
  const [summary, setSummary] = useState<InviteSummary | null>(null);
  const [fixedRecords, setFixedRecords] = useState<InviteRecord[]>([]);
  const [rebateRecords, setRebateRecords] = useState<InviteRecord[]>([]);
  const [fixedTotal, setFixedTotal] = useState(0);
  const [rebateTotal, setRebateTotal] = useState(0);
  const [fixedPage, setFixedPage] = useState(1);
  const [rebatePage, setRebatePage] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const [activeTab, setActiveTab] = useState<RecordTab>("fixed");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [linkError, setLinkError] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getInviteBundle()
      .then(([nextSummary, records]) => {
        if (!active) return;
        setSummary(nextSummary);
        setFixedRecords(records.fixedRewardRecords);
        setRebateRecords(records.friendRebateRecords);
        setFixedTotal(records.fixedRewardTotal);
        setRebateTotal(records.friendRebateTotal);
      })
      .catch((reason) => { if (active) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, []);

  const displayedRecords = activeTab === "fixed" ? fixedRecords : rebateRecords;
  const tierHint = useMemo(() => {
    if (!summary) return "";
    if (!summary.isV2) return t("invite.sync.hint", "邀请 V2 数据待服务端同步");
    if (summary.eligibleFriendCount === null) return t("invite.sync.hint", "邀请 V2 数据待服务端同步");
    if (!summary.nextTier) return t("invite.tier.maximum", "已达到最高 8% 返佣等级");
    return t("invite.tier.next", "再有 {count} 位合格好友可达到 {rate}%", {
      count: Math.max(0, summary.nextTier.minimumFriends - summary.eligibleFriendCount),
      rate: rate(summary.nextTier.ratePercent, dateLocale),
    });
  }, [dateLocale, summary, t]);

  async function copyCode() {
    if (!summary?.code) return;
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(summary.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopyError(true);
    }
  }

  async function shareInvite() {
    if (!summary?.code) return;
    setLinkError(false);
    const url = `${window.location.origin}/register?invite_code=${encodeURIComponent(summary.code)}`;
    try {
      if (navigator.share) {
        await navigator.share({
          title: t("invite.link.shareTitle", "邀请好友加入 KAI 星算"),
          text: t("invite.link.shareText", "注册时使用我的邀请码 {code}", { code: summary.code }),
          url,
        });
      } else {
        await navigator.clipboard.writeText(url);
      }
      setLinkCopied(true);
      window.setTimeout(() => setLinkCopied(false), 1600);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setLinkError(true);
    }
  }

  async function loadMoreRecords() {
    if (loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      if (activeTab === "fixed") {
        const nextPage = fixedPage + 1;
        const result = await getInviteRecordPage(nextPage);
        setFixedRecords((current) => [...new Map([...current, ...result.items].map((item) => [item.key, item])).values()]);
        setFixedTotal(result.total);
        setFixedPage(nextPage);
      } else {
        const nextPage = rebatePage + 1;
        const result = await getInviteCommissionPage(nextPage);
        setRebateRecords((current) => [...new Map([...current, ...result.items].map((item) => [item.key, item])).values()]);
        setRebateTotal(result.total);
        setRebatePage(nextPage);
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadingMore(false);
    }
  }

  if (!summary && !error) return <div className={styles.skeleton} aria-label={t("invite.loading", "正在读取邀请奖励")}> <i/><i/><i/> </div>;
  if (!summary) return <div className="commerce-error" role="alert">{error}</div>;

  const visibleSlots = Math.min(12, Math.max(1, summary.dailyLimit));
  const restrictions = !summary.withdrawable && !summary.transferable
    ? t("invite.restriction.both", "奖励仅可站内消费，不可提现或转赠")
    : !summary.withdrawable
      ? t("invite.restriction.withdraw", "奖励仅可站内消费，不可提现")
      : !summary.transferable
        ? t("invite.restriction.transfer", "奖励不可转赠")
        : t("invite.restriction.account", "奖励用途以账户规则为准");

  return <div className={styles.root}>
    {error && <div className="commerce-error" role="alert">{error}</div>}
    {!summary.isV2 && <div className={styles.programNotice} role="status">
      <ClockCountdown size={18}/>
      <span><strong>{t("invite.sync.title", "邀请 V2 数据待同步")}</strong>{t("invite.sync.body", "静态规则已更新，当前名额、等级和奖励金额需等待服务端返回 V2 账务数据。")}</span>
    </div>}
    {summary.isV2 && !summary.rewardsEnabled && <div className={styles.programNotice} role="status">
      <WarningCircle size={18}/>
      <span><strong>{t("invite.disabled.title", "邀请奖励当前未开启")}</strong>{t("invite.disabled.body", "页面展示已确认规则，实际计提以服务端启用状态为准。")}</span>
    </div>}

    <section className={styles.hero}>
      <div className={styles.codeBlock}>
        <span>{t("invite.code.label", "我的邀请码")}</span>
        <strong>{summary.code || "-"}</strong>
        <div className={styles.codeActions}>
          <button type="button" onClick={() => void copyCode()} disabled={!summary.code}>
            {copied ? <CheckCircle size={17}/> : <Copy size={17}/>}
            {copied ? t("invite.code.copied", "已复制") : t("invite.code.copy", "复制邀请码")}
          </button>
          <button type="button" className={styles.secondaryAction} onClick={() => void shareInvite()} disabled={!summary.code}>
            {linkCopied ? <CheckCircle size={17}/> : <ShareNetwork size={17}/>}
            {linkCopied ? t("invite.link.copied", "邀请链接已复制") : t("invite.link.share", "分享邀请链接")}
          </button>
        </div>
        <small aria-live="polite">{copyError || linkError ? t("invite.code.copyFailed", "复制失败，请手动复制邀请码") : t("invite.code.caption", "好友打开链接即可自动填写邀请码，邀请关系绑定后不可更改")}</small>
      </div>

      <div className={styles.quotaBlock}>
        <header>
          <span><ClockCountdown size={18}/>{t("invite.quota.title", "今日合格名额")}</span>
          <strong>{summary.dailySlotsUsed ?? "-"} / {summary.dailyLimit}</strong>
        </header>
        <div className={styles.slotGrid} aria-label={summary.dailySlotsUsed === null ? t("invite.sync.hint", "邀请 V2 数据待服务端同步") : t("invite.quota.progress", "今日已使用 {used} 个，共 {limit} 个名额", { used: summary.dailySlotsUsed, limit: summary.dailyLimit })}>
          {Array.from({ length: visibleSlots }, (_, index) => <i className={summary.dailySlotsUsed === null ? styles.slotUnknown : index < summary.dailySlotsUsed ? styles.slotUsed : ""} key={index}/>) }
        </div>
        <dl>
          <div><dt>{t("invite.quota.pendingIdentity", "待完成实名")}</dt><dd>{summary.pendingIdentityCount ?? "-"}</dd></div>
          <div><dt>{t("invite.quota.pendingOrder", "待完成首单")}</dt><dd>{summary.pendingOrderCount ?? "-"}</dd></div>
          <div><dt>{t("invite.quota.remaining", "剩余名额")}</dt><dd>{summary.dailySlotsRemaining ?? "-"}</dd></div>
          <div><dt>{t("invite.quota.exceeded", "超出名额")}</dt><dd>{summary.dailyCapExceededCount ?? "-"}</dd></div>
        </dl>
        <small>{summary.isV2 ? t("invite.quota.reset", "重置时间：{time}", { time: resetTime(summary.nextResetAt, dateLocale) }) : t("invite.sync.hint", "邀请 V2 数据待服务端同步")}</small>
      </div>
    </section>

    <section className={styles.mechanismGrid}>
      <article className={styles.fixedReward}>
        <header>
          <span className={styles.iconBox}><Gift size={22}/></span>
          <div><h2>{t("invite.fixed.title", "邀请达标奖励")}</h2><p>{t("invite.fixed.subtitle", "每位合格好友固定奖励")}</p></div>
          <strong>+{amount(summary.fixedRewardCardHours, dateLocale)}</strong>
        </header>
        <div className={styles.mechanismStats}>
          <div><small>{t("invite.fixed.settled", "累计已发")}</small><strong>{optionalAmount(summary.fixedRewardTotal, dateLocale)}</strong><span>{t("invite.unit.cardHours", "卡时")}</span></div>
          <div><small>{t("invite.fixed.pending", "待发奖励")}</small><strong>{optionalAmount(summary.fixedRewardPending, dateLocale)}</strong><span>{t("invite.unit.cardHours", "卡时")}</span></div>
        </div>
        <ol className={styles.qualificationSteps}>
          <li><UserCheck size={18}/><span><strong>{t("invite.fixed.identity", "完成实名认证")}</strong><small>{t("invite.fixed.identityNote", "好友身份审核通过")}</small></span></li>
          <li><Receipt size={18}/><span><strong>{t("invite.fixed.firstOrder", "完成首笔有效订单")}</strong><small>{t("invite.fixed.firstOrderNote", "订单由真实充值卡时支持并完成")}</small></span></li>
          <li><Coins size={18}/><span><strong>{t("invite.fixed.credit", "奖励邀请人")}</strong><small>{t("invite.fixed.creditNote", "58 卡时进入站内消费余额")}</small></span></li>
        </ol>
        <p className={styles.quotaRule}>{t("invite.fixed.quotaRule", "每日名额按好友完成“实名 + 首笔有效订单”的北京时间日期占用，不按注册日期计算。每天最多 5 位；第 6 位及以后仍保留邀请关系，但不发 58 卡时、不计入等级，也不产生后续消费返佣。")}</p>
      </article>

      <article className={styles.rebatePanel}>
        <header>
          <div><span><TrendUp size={18}/>{t("invite.rebate.title", "好友消费返佣")}</span><p>{tierHint}</p></div>
          <strong>{summary.friendRebateCurrentRate === null ? "-" : `${rate(summary.friendRebateCurrentRate, dateLocale)}%`}</strong>
        </header>
        <div className={styles.rebateStats}>
          <div><small>{t("invite.rebate.eligibleFriends", "合格好友")}</small><strong>{summary.eligibleFriendCount ?? "-"}</strong><span>{t("invite.unit.people", "人")}</span></div>
          <div><small>{t("invite.rebate.eligibleSpend", "有效消费基数")}</small><strong>{optionalAmount(summary.eligibleFriendSpendCardHours, dateLocale)}</strong><span>{t("invite.unit.cardHours", "卡时")}</span></div>
          <div><small>{t("invite.rebate.pending", "待结算返佣")}</small><strong>{optionalAmount(summary.friendRebatePending, dateLocale)}</strong><span>{t("invite.unit.cardHours", "卡时")}</span></div>
          <div><small>{t("invite.rebate.settled", "累计已结算")}</small><strong>{optionalAmount(summary.friendRebateSettled, dateLocale)}</strong><span>{t("invite.unit.cardHours", "卡时")}</span></div>
        </div>
        <div className={styles.tierGrid}>
          {summary.friendRebateTiers.map((tier) => {
            const current = summary.friendRebateCurrentRate !== null
              && summary.friendRebateCurrentRate === tier.ratePercent;
            const range = tier.maximumFriends === null
              ? `${tier.minimumFriends}+`
              : `${tier.minimumFriends}-${tier.maximumFriends}`;
            return <div className={current ? styles.currentTier : ""} key={`${tier.minimumFriends}-${tier.ratePercent}`}>
              <span>{range} {t("invite.unit.people", "人")}</span>
              <strong>{rate(tier.ratePercent, dateLocale)}%</strong>
              {current && <small>{t("invite.tier.current", "当前")}</small>}
            </div>;
          })}
        </div>
        <p className={styles.rebateRule}>{t("invite.rebate.rule", "仅计算一级好友由真实充值支持且已完成的有效消费。好友再次邀请的人不计入；退款、取消、争议和奖励卡时消费不计返佣。")}</p>
      </article>
    </section>

    <section className={styles.records}>
      <header>
        <div><h2>{t("invite.records.title", "邀请奖励记录")}</h2><p>{t("invite.records.subtitle", "固定奖励和好友消费返佣分别核对")}</p></div>
        <span>{fixedTotal + rebateTotal}</span>
      </header>
      <div className={styles.recordTabs} role="tablist" aria-label={t("invite.records.tabs", "奖励记录分类")}>
        <button type="button" role="tab" aria-selected={activeTab === "fixed"} className={activeTab === "fixed" ? styles.activeTab : ""} onClick={() => setActiveTab("fixed")}>
          <Gift size={17}/>{t("invite.records.fixedTab", "达标奖励")}<span>{fixedTotal}</span>
        </button>
        <button type="button" role="tab" aria-selected={activeTab === "rebate"} className={activeTab === "rebate" ? styles.activeTab : ""} onClick={() => setActiveTab("rebate")}>
          <TrendUp size={17}/>{t("invite.records.rebateTab", "消费返佣")}<span>{rebateTotal}</span>
        </button>
      </div>
      <div className={styles.recordList} role="tabpanel">
        {displayedRecords.length
          ? displayedRecords.map((row) => <RecordRow row={row} summary={summary} key={row.key}/>)
          : <div className={styles.empty}><UsersThree size={28}/><strong>{activeTab === "fixed" ? t("invite.records.emptyFixed", "还没有达标奖励记录") : t("invite.records.emptyRebate", "还没有消费返佣记录")}</strong><span>{t("invite.records.emptyHint", "好友满足对应条件后，记录会由服务端自动生成。")}</span></div>}
      </div>
      {displayedRecords.length < (activeTab === "fixed" ? fixedTotal : rebateTotal) && <button className={styles.loadMore} type="button" disabled={loadingMore} onClick={() => void loadMoreRecords()}>
        {loadingMore ? t("invite.records.loadingMore", "正在加载…") : t("invite.records.loadMore", "加载更多记录")}
      </button>}
    </section>

    <section className={styles.complianceNote}>
      <ShieldCheck size={20}/>
      <div>
        <strong>{t("invite.rules.title", "奖励边界")}</strong>
        <p>{t("invite.rules.body", "本计划仅限一级好友，不要求缴纳入门费。禁止自邀和关联账号参与；所有资格、有效消费和结算结果以服务端风控与账务记录为准。")}</p>
      </div>
      <span><LockKey size={16}/>{restrictions}</span>
    </section>
  </div>;
}
