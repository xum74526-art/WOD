"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Bank, CheckCircle, Copy, Gift, Plus, Receipt, Ticket, Trash, TrendUp, UsersThree } from "@phosphor-icons/react";
import { errorMessage } from "@/lib/commerce-ui";
import {
  addBankCard,
  deleteBankCard,
  getBankCardBundle,
  getInviteBundle,
  getRevenueBundle,
  listCoupons,
  redeemCoupon,
  setDefaultBankCard,
  type BankCard,
  type BankCardConfig,
  type Coupon,
  type InviteRecord,
  type InviteSummary,
  type RebateSummary,
  type RevenuePoint,
  type RevenueRecord,
  type RevenueSummary,
} from "@/lib/mobile-business-api";

export type MobileAccountSection = "revenue" | "referrals" | "coupons" | "bank-accounts";

function amount(value: unknown) { const n = Number(value || 0); return Number.isFinite(n) ? n.toFixed(2) : "0.00"; }
function date(value?: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN") : "—"; }

function RevenueWorkspace() {
  const [summary, setSummary] = useState<RevenueSummary | null>(null);
  const [rebate, setRebate] = useState<RebateSummary | null>(null);
  const [points, setPoints] = useState<RevenuePoint[]>([]);
  const [records, setRecords] = useState<RevenueRecord[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { getRevenueBundle().then(([a, b, c, d]) => { setSummary(a); setPoints(b); setRecords(c); setRebate(d); }).catch((reason) => setError(errorMessage(reason))); }, []);
  const max = Math.max(1, ...points.map((point) => Number(point.amount || 0)));
  if (!summary && !error) return <div className="workspace-skeleton" />;
  return <>
    {error && <div className="commerce-error">{error}</div>}
    <div className="mobile-data-spine">
      <article><small>今日收益</small><strong>{amount(summary?.today)}</strong><span>卡时</span></article>
      <article><small>累计收益</small><strong>{amount(summary?.total)}</strong><span>卡时</span></article>
      <article><small>当前收益率</small><strong>{amount(summary?.rate)}%</strong><span>实时规则</span></article>
      <article><small>本月返佣</small><strong>{amount(rebate?.month_rebated)}</strong><span>{amount(rebate?.current_rate)}% 档位</span></article>
    </div>
    <div className="mobile-service-columns">
      <section className="mobile-trend-panel"><header><div><small>30 DAY REVENUE</small><h2>收益走势</h2></div><TrendUp size={21}/></header>{points.length ? <div className="mobile-mini-bars" aria-label="近 30 天收益图">{points.map((point, index) => <span title={`${point.date}: ${amount(point.amount)}`} key={`${point.date}-${index}`}><i style={{ height: `${Math.max(4, Number(point.amount || 0) / max * 100)}%` }}/><small>{point.date.slice(5)}</small></span>)}</div> : <div className="mobile-inline-empty">暂无收益曲线</div>}</section>
      <section className="mobile-rebate-panel"><header><Gift size={20}/><div><small>REBATE PROGRESS</small><h2>返佣进度</h2></div></header><strong>{amount(rebate?.pending_rebate)}</strong><span>待结算返佣（卡时）</span><p>{rebate?.next_tier_hint || "当前没有新的阶梯提示"}</p><footer>{rebate?.rewards_enabled ? `奖励模式：${rebate.reward_mode}` : "返佣服务暂未启用"}</footer></section>
    </div>
    <section className="mobile-record-panel"><header><Receipt size={19}/><div><small>REVENUE LEDGER</small><h2>收益记录</h2></div><b>{records.length}</b></header>{records.length ? records.map((row) => <article key={row.id}><span><strong>+{amount(row.amount)} 卡时</strong><small>资产 #{row.asset_id || "—"}</small></span><time>{date(row.date || row.created_at)}</time></article>) : <div className="mobile-inline-empty">暂无收益记录</div>}</section>
        {!summary?.revenue_settlement_enabled && <div className="workspace-service-note">当前收益统计仅包含已确认结算记录；未结算历史记录为 {amount(summary?.historical_test_total)} 卡时。</div>}
  </>;
}

function ReferralWorkspace() {
  const [summary, setSummary] = useState<InviteSummary | null>(null); const [rows, setRows] = useState<InviteRecord[]>([]); const [copied, setCopied] = useState(false); const [error, setError] = useState("");
  useEffect(() => { getInviteBundle().then(([a, b]) => { setSummary(a); setRows(b.items || []); }).catch((reason) => setError(errorMessage(reason))); }, []);
  async function copy() { if (!summary?.code) return; await navigator.clipboard.writeText(summary.code); setCopied(true); window.setTimeout(() => setCopied(false), 1600); }
  if (!summary && !error) return <div className="workspace-skeleton" />;
  return <>{error && <div className="commerce-error">{error}</div>}<div className="mobile-invite-hero"><div><small>YOUR INVITE CODE</small><strong>{summary?.code || "—"}</strong><button onClick={() => void copy()}>{copied ? <CheckCircle size={16}/> : <Copy size={16}/>} {copied ? "已复制" : "复制邀请码"}</button></div><UsersThree size={64} weight="thin"/></div><div className="mobile-data-spine"><article><small>已邀请</small><strong>{summary?.invited_count || 0}</strong><span>位用户</span></article><article><small>已达标</small><strong>{summary?.qualified_count || 0}</strong><span>位用户</span></article><article><small>累计奖励</small><strong>{amount(summary?.total_reward)}</strong><span>卡时</span></article><article><small>当前等级</small><strong>{summary?.current_tier || "—"}</strong><span>{summary?.next_tier_hint || "暂无升级提示"}</span></article></div><section className="mobile-record-panel"><header><UsersThree size={19}/><div><small>INVITE HISTORY</small><h2>邀请记录</h2></div><b>{rows.length}</b></header>{rows.length ? rows.map((row) => <article key={row.id}><span><strong>{row.invitee_phone}</strong><small>{row.status}</small></span><span className="mobile-record-amount">{row.reward_amount ? `+${amount(row.reward_amount)} 卡时` : "待达标"}</span><time>{date(row.created_at)}</time></article>) : <div className="mobile-inline-empty">还没有邀请记录</div>}</section></>;
}

function CouponWorkspace() {
  const [rows, setRows] = useState<Coupon[]>([]); const [status, setStatus] = useState(""); const [code, setCode] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const load = useCallback(() => listCoupons(status).then(setRows).catch((reason) => setError(errorMessage(reason))), [status]);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await redeemCoupon(code.trim()); setCode(""); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); } }
  return <>{error && <div className="commerce-error">{error}</div>}<div className="mobile-ops-toolbar"><nav>{[["", "全部"], ["available", "可使用"], ["used", "已使用"], ["expired", "已过期"]].map(([value, label]) => <button className={status === value ? "active" : ""} onClick={() => setStatus(value)} key={value}>{label}</button>)}</nav><form className="mobile-code-form" onSubmit={submit}><input placeholder="输入兑换码" value={code} onChange={(event) => setCode(event.target.value)} required/><button disabled={busy}><Plus size={15}/>{busy ? "兑换中" : "兑换"}</button></form></div><div className="mobile-coupon-grid">{rows.length ? rows.map((coupon) => <article className={`coupon-${coupon.status}`} key={coupon.id}><header><Ticket size={22}/><span>{coupon.status}</span></header><strong>{amount(coupon.amount)}<small>卡时</small></strong><h2>{coupon.name}</h2><p>满 {amount(coupon.min_amount)} 卡时可用</p><footer>有效期至 {date(coupon.expires_at)}</footer></article>) : <div className="mobile-empty-state"><Ticket size={30}/><strong>当前分类没有优惠券</strong><span>可在右上角输入兑换码。</span></div>}</div></>;
}

function BankCardWorkspace() {
  const [rows, setRows] = useState<BankCard[]>([]); const [config, setConfig] = useState<BankCardConfig | null>(null); const [form, setForm] = useState({ bank_name: "", card_number: "", holder: "", phone: "" }); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const load = useCallback(async () => { try { const [a, b] = await getBankCardBundle(); setRows(a); setConfig(b); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function act(action: () => Promise<unknown>) { setBusy(true); setError(""); try { await action(); await load(); return true; } catch (reason) { setError(errorMessage(reason)); return false; } finally { setBusy(false); } }
  async function submit(event: FormEvent) { event.preventDefault(); if (await act(() => addBankCard(form))) setForm({ bank_name: "", card_number: "", holder: "", phone: "" }); }
  return <>{error && <div className="commerce-error">{error}</div>}<div className="mobile-service-columns bank-layout"><section className="mobile-record-panel"><header><Bank size={20}/><div><small>SETTLEMENT CARDS</small><h2>已绑定银行卡</h2></div><b>{rows.length}</b></header>{rows.length ? rows.map((card) => <article className="mobile-bank-row" key={card.id}><span><strong>{card.bank_name || "银行卡"} ···· {card.card_last4 || card.card_number.slice(-4)}</strong><small>{card.holder} · {card.status}{card.is_default ? " · 默认卡" : ""}</small></span><div>{!card.is_default && <button disabled={busy} onClick={() => void act(() => setDefaultBankCard(card.id))}>设为默认</button>}<button className="danger" disabled={busy} onClick={() => { if (window.confirm("确定解绑这张银行卡？")) void act(() => deleteBankCard(card.id)); }}><Trash size={14}/>解绑</button></div></article>) : <div className="mobile-inline-empty">还没有绑定银行卡</div>}</section><form className="mobile-business-form" onSubmit={submit}><header><Plus size={20}/><div><small>ADD BANK CARD</small><h2>添加银行卡</h2></div></header><label>持卡人<input value={form.holder} onChange={(e) => setForm({ ...form, holder: e.target.value })} required/></label><label>银行卡号<input inputMode="numeric" value={form.card_number} onChange={(e) => setForm({ ...form, card_number: e.target.value.replace(/\s/g, "") })} required/></label><label>开户银行<input value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })}/></label><label>预留手机号<input inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}/></label><button className="commerce-primary" disabled={busy || config?.binding_enabled === false}>{busy ? "保存中…" : config?.binding_enabled === false ? "绑定服务未开放" : "添加银行卡"}</button><p>{config?.notice || "银行卡仅用于人工审核后的提现结算。"}</p></form></div></>;
}

const headers: Record<MobileAccountSection, { eyebrow: string; title: string; description: string }> = {
  revenue: { eyebrow: "ACCOUNT / EARNINGS", title: "收益与返佣", description: "查看算力收益、趋势、明细和返佣进度。" },
  referrals: { eyebrow: "ACCOUNT / REFERRALS", title: "邀请与记录", description: "管理邀请码、邀请关系和后端确认的奖励记录。" },
  coupons: { eyebrow: "ACCOUNT / COUPONS", title: "优惠券", description: "查看可用、已使用和已过期优惠券，并兑换新券。" },
  "bank-accounts": { eyebrow: "ACCOUNT / SETTLEMENT", title: "银行卡", description: "管理提现结算使用的实名银行卡，不在 Web 保存完整卡号。" },
};

export function MobileAccountServices({ section }: { section: MobileAccountSection }) {
  const header = headers[section];
  return <section className={`workspace-page mobile-account-service mobile-account-service--${section}`}><div className="workspace-page__head"><p>{header.eyebrow}</p><h1>{header.title}</h1><span>{header.description}</span></div>{section === "revenue" ? <RevenueWorkspace/> : section === "referrals" ? <ReferralWorkspace/> : section === "coupons" ? <CouponWorkspace/> : <BankCardWorkspace/>}</section>;
}
