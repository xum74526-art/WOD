"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Bank, Gift, Plus, Receipt, Ticket, Trash, TrendUp } from "@phosphor-icons/react";
import { errorMessage } from "@/lib/commerce-ui";
import {
  addBankCard,
  deleteBankCard,
  getBankCardBundle,
  getVerification,
  getRevenueBundle,
  listCoupons,
  redeemCoupon,
  setDefaultBankCard,
  type BankCard,
  type BankCardConfig,
  type Coupon,
  type RebateSummary,
  type RevenuePoint,
  type RevenueRecord,
  type RevenueSummary,
  type VerificationInfo,
} from "@/lib/mobile-business-api";
import { isRegisteredBankCardStatus, luhnCheckCardNumber } from "@/lib/finance-ui";
import { useI18n } from "@/components/locale-root";
import { localizeRebateHint } from "@/lib/product-purchase";
import { ReferralWorkspace } from "@/components/referral-workspace";

export type MobileAccountSection = "revenue" | "referrals" | "coupons" | "bank-accounts";

function amount(value: unknown) { const n = Number(value || 0); return Number.isFinite(n) ? n.toFixed(2) : "0.00"; }
function date(value?: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN") : "—"; }

function RevenueWorkspace() {
  const { locale, t } = useI18n();
  const [summary, setSummary] = useState<RevenueSummary | null>(null);
  const [rebate, setRebate] = useState<RebateSummary | null>(null);
  const [points, setPoints] = useState<RevenuePoint[]>([]);
  const [records, setRecords] = useState<RevenueRecord[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { getRevenueBundle().then(([a, b, c, d]) => { setSummary(a); setPoints(b); setRecords(c); setRebate(d); }).catch((reason) => setError(errorMessage(reason))); }, []);
  const max = Math.max(1, ...points.map((point) => Number(point.amount || 0)));
  const personalCap = Number(rebate?.monthly_cap ?? 0);
  const personalEntitled = Number(rebate?.month_entitled ?? 0);
  const personalCapUsed = Number(rebate?.cap_used ?? 0);
  const personalCapRemaining = Number(rebate?.cap_remaining ?? 0);
  const tierHint = localizeRebateHint(rebate?.next_tier_hint, locale)
    || t("rebate.personal.noHint", "当前没有新的等级提示。");
  const rewardMode = rebate?.reward_mode === "live"
    ? t("rebate.mode.live", "正式卡时")
    : rebate?.reward_mode === "test_card_hours"
      ? t("rebate.mode.cardHours", "站内卡时")
      : t("rebate.mode.disabled", "未开启");
  if (!summary && !error) return <div className="workspace-skeleton" />;
  return <>
    {error && <div className="commerce-error">{error}</div>}
    <div className="mobile-data-spine">
      <article><small>今日收益</small><strong>{amount(summary?.today)}</strong><span>卡时</span></article>
      <article><small>累计收益</small><strong>{amount(summary?.total)}</strong><span>卡时</span></article>
      <article><small>当前收益率</small><strong>{amount(summary?.rate)}%</strong><span>实时规则</span></article>
      <article><small>{t("rebate.personal.monthRebated", "本月个人购买返佣")}</small><strong>{amount(rebate?.month_rebated)}</strong><span>{t("rebate.personal.currentTier", "当前等级 {rate}%", { rate: amount(rebate?.current_rate) })}</span></article>
    </div>
    <div className="mobile-service-columns">
      <section className="mobile-trend-panel"><header><div><small>30 DAY REVENUE</small><h2>收益走势</h2></div><TrendUp size={21}/></header>{points.length ? <div className="mobile-mini-bars" aria-label="近 30 天收益图">{points.map((point, index) => <span title={`${point.date}: ${amount(point.amount)}`} key={`${point.date}-${index}`}><i style={{ height: `${Math.max(4, Number(point.amount || 0) / max * 100)}%` }}/><small>{point.date.slice(5)}</small></span>)}</div> : <div className="mobile-inline-empty">暂无收益曲线</div>}</section>
      <section className="mobile-rebate-panel"><header><Gift size={20}/><div><small>PERSONAL PURCHASE REBATE</small><h2>{t("rebate.personal.title", "个人购买返佣")}</h2></div></header><strong>{amount(rebate?.pending_rebate)}</strong><span>{t("rebate.personal.pending", "待到期结算（卡时）")}</span><p>{t("rebate.personal.mechanism", "仅统计已确认交付的使用模式订单；等级按本月个人购买卡时总额计算，资产服务期结束后返佣入账。")}</p><footer>{tierHint}<br/>{t("rebate.personal.capProgress", "本月应计 {entitled} · 已用额度 {used} · 剩余额度 {remaining} · 月度上限 {cap} 卡时 · {mode}", { entitled: amount(personalEntitled), used: amount(personalCapUsed), remaining: amount(personalCapRemaining), cap: amount(personalCap), mode: rewardMode })}</footer></section>
    </div>
    <section className="mobile-record-panel"><header><Receipt size={19}/><div><small>REVENUE LEDGER</small><h2>收益记录</h2></div><b>{records.length}</b></header>{records.length ? records.map((row) => <article key={row.id}><span><strong>+{amount(row.amount)} 卡时</strong><small>资产 #{row.asset_id || "—"}</small></span><time>{date(row.date || row.created_at)}</time></article>) : <div className="mobile-inline-empty">暂无收益记录</div>}</section>
        {!summary?.revenue_settlement_enabled && <div className="workspace-service-note">当前收益统计仅包含已确认结算记录；未结算历史记录为 {amount(summary?.historical_test_total)} 卡时。</div>}
  </>;
}

function CouponWorkspace() {
  const [rows, setRows] = useState<Coupon[]>([]); const [status, setStatus] = useState(""); const [code, setCode] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const load = useCallback(() => listCoupons(status).then(setRows).catch((reason) => setError(errorMessage(reason))), [status]);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await redeemCoupon(code.trim()); setCode(""); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); } }
  return <>{error && <div className="commerce-error">{error}</div>}<div className="mobile-ops-toolbar"><nav>{[["", "全部"], ["available", "可使用"], ["used", "已使用"], ["expired", "已过期"]].map(([value, label]) => <button className={status === value ? "active" : ""} onClick={() => setStatus(value)} key={value}>{label}</button>)}</nav><form className="mobile-code-form" onSubmit={submit}><input placeholder="输入兑换码" value={code} onChange={(event) => setCode(event.target.value)} required/><button disabled={busy}><Plus size={15}/>{busy ? "兑换中" : "兑换"}</button></form></div><div className="mobile-coupon-grid">{rows.length ? rows.map((coupon) => <article className={`coupon-${coupon.status}`} key={coupon.id}><header><Ticket size={22}/><span>{coupon.status}</span></header><strong>{amount(coupon.amount)}<small>卡时</small></strong><h2>{coupon.name}</h2><p>满 {amount(coupon.min_amount)} 卡时可用</p><footer>有效期至 {date(coupon.expires_at)}</footer></article>) : <div className="mobile-empty-state"><Ticket size={30}/><strong>当前分类没有优惠券</strong><span>可在右上角输入兑换码。</span></div>}</div></>;
}

function BankCardWorkspace() {
  const [rows, setRows] = useState<BankCard[]>([]);
  const [config, setConfig] = useState<BankCardConfig | null>(null);
  const [verification, setVerification] = useState<VerificationInfo | null>(null);
  const [form, setForm] = useState({ bank_name: "", card_number: "", holder: "", phone: "" });
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [[bankCards, bankConfig], identity] = await Promise.all([getBankCardBundle(), getVerification()]);
      setRows(bankCards);
      setConfig(bankConfig);
      setVerification(identity);
      setForm((current) => ({ ...current, holder: identity.real_name || "" }));
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await load(); return true; }
    catch (reason) { setError(errorMessage(reason)); return false; }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const cardNumber = form.card_number.replace(/\D/g, "");
    if (verification?.status !== "verified" || !form.holder) { setError("请先完成实名认证，持卡人必须与实名姓名一致"); return; }
    if (config?.binding_enabled === false) { setError("银行卡绑定服务未开放"); return; }
    if (!/^\d{12,19}$/.test(cardNumber)) { setError("请输入 12 至 19 位银行卡号"); return; }
    if (!luhnCheckCardNumber(cardNumber)) { setError("银行卡号校验未通过，请检查后重新输入"); return; }
    if (!form.bank_name.trim()) { setError("请输入开户银行"); return; }
    if (!/^1\d{10}$/.test(form.phone)) { setError("请输入 11 位有效预留手机号"); return; }
    if (!consent) { setError("请先同意银行卡登记与人工复核说明"); return; }
    const created = await act(() => addBankCard({
      bank_name: form.bank_name.trim(), card_number: cardNumber, holder: form.holder,
      phone: form.phone, is_default: rows.length === 0, sensitive_consent: consent,
    }));
    if (created) {
      setForm({ bank_name: "", card_number: "", holder: verification.real_name || "", phone: "" });
      setConsent(false);
    }
  }

  const statusLabel = (status: BankCard["status"]) => ({ registered: "已登记", pending_review: "待复核", active: "已启用", rejected: "已驳回", disabled: "已停用" })[status];
  const identityReady = verification?.status === "verified";

  if (loading) return <div className="workspace-skeleton" aria-label="正在读取银行卡资料" />;
  return <>
    {error && <div className="commerce-error">{error}</div>}
    {!identityReady && <div className="workspace-service-note">
      <strong>{verification?.status === "pending" ? "实名认证正在审核" : "绑定银行卡前需完成实名认证"}</strong>
      <span>持卡人姓名将从实名认证资料自动填写，不能自行修改。 </span>
      {verification?.status !== "pending" && <a href="/account/verification">去认证</a>}
    </div>}
    <div className="mobile-service-columns bank-layout">
      <section className="mobile-record-panel">
        <header><Bank size={20}/><div><small>SETTLEMENT CARDS</small><h2>已绑定银行卡</h2></div><b>{rows.length}</b></header>
        {rows.length ? rows.map((card) => <article className="mobile-bank-row" key={card.id}>
          <span><strong>{card.bank_name || "银行卡"} ···· {card.card_last4 || card.card_number.slice(-4)}</strong><small>{card.holder} · {statusLabel(card.status)}{card.is_default ? " · 默认卡" : ""}</small>{!card.consent_recorded && isRegisteredBankCardStatus(card.status) && <small className="finance-review-reason">需在右侧重新提交同一张卡并勾选同意后，才可用于提现。</small>}{card.reject_reason && <small className="finance-review-reason">驳回原因：{card.reject_reason}</small>}</span>
          <div>
            {!card.is_default && card.consent_recorded && isRegisteredBankCardStatus(card.status) && <button disabled={busy} onClick={() => void act(() => setDefaultBankCard(card.id))}>设为默认</button>}
            {card.status !== "disabled" && <button className="danger" disabled={busy} onClick={() => { if (window.confirm("确定停用这张银行卡？")) void act(() => deleteBankCard(card.id)); }}><Trash size={14}/>停用</button>}
          </div>
        </article>) : <div className="mobile-inline-empty">还没有绑定银行卡</div>}
      </section>
      <form className="mobile-business-form" onSubmit={submit}>
        <header><Plus size={20}/><div><small>ADD BANK CARD</small><h2>添加银行卡</h2></div></header>
        <label>持卡人<input value={form.holder} readOnly placeholder="完成实名认证后自动填写"/></label>
        <label>银行卡号<input inputMode="numeric" maxLength={19} value={form.card_number} onChange={(event) => setForm({ ...form, card_number: event.target.value.replace(/\D/g, "").slice(0, 19) })} required/></label>
        <label>开户银行<input value={form.bank_name} onChange={(event) => setForm({ ...form, bank_name: event.target.value })} required/></label>
        <label>预留手机号<input inputMode="tel" maxLength={11} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value.replace(/\D/g, "").slice(0, 11) })} required/></label>
        <label className="bank-card-consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)}/> 我确认收款银行卡属于本人，并同意平台为人工打款与复核而加密保存和使用；此登记不代表银行验证。</label>
        <button className="commerce-primary" disabled={busy || !identityReady || !consent || config?.binding_enabled === false}>{busy ? "保存中…" : config?.binding_enabled === false ? "绑定服务未开放" : !identityReady ? "请先完成实名认证" : "登记银行卡"}</button>
        <p>{config?.notice || "银行卡登记不代表银行已完成真实性验证；审核通过后才可用于提现。"}</p>
      </form>
    </div>
  </>;
}

const headers: Record<MobileAccountSection, { eyebrow: string; title: string; description: string }> = {
  revenue: { eyebrow: "ACCOUNT / EARNINGS", title: "收益与返佣", description: "查看算力收益、趋势、明细和返佣进度。" },
  referrals: { eyebrow: "ACCOUNT / REFERRALS", title: "邀请与记录", description: "管理邀请码、邀请关系和后端确认的奖励记录。" },
  coupons: { eyebrow: "ACCOUNT / COUPONS", title: "优惠券", description: "查看可用、已使用和已过期优惠券，并兑换新券。" },
  "bank-accounts": { eyebrow: "ACCOUNT / SETTLEMENT", title: "银行卡", description: "管理提现结算使用的实名银行卡，不在 Web 保存完整卡号。" },
};

export function MobileAccountServices({ section }: { section: MobileAccountSection }) {
  const { t } = useI18n();
  const header = section === "referrals" ? {
    eyebrow: "ACCOUNT / REFERRALS",
    title: t("invite.page.title", "邀请奖励"),
    description: t("invite.page.description", "查看每日名额、达标奖励、好友消费返佣和结算记录。"),
  } : headers[section];
  return <section className={`workspace-page mobile-account-service mobile-account-service--${section}`}><div className="workspace-page__head"><p>{header.eyebrow}</p><h1>{header.title}</h1><span>{header.description}</span></div>{section === "revenue" ? <RevenueWorkspace/> : section === "referrals" ? <ReferralWorkspace/> : section === "coupons" ? <CouponWorkspace/> : <BankCardWorkspace/>}</section>;
}
