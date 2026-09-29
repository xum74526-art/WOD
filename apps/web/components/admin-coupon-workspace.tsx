"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Check, Copy, Ticket, ToggleLeft, ToggleRight } from "@phosphor-icons/react";
import { useI18n } from "@/components/locale-root";
import {
  createAdminCouponCampaign,
  listAdminCouponCampaigns,
  updateAdminCouponCampaignStatus,
  type AdminCouponCampaign,
  type AdminCouponCampaignStatus,
} from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { convertDisplayToCardHours } from "@/lib/display-currency";

const PAGE_SIZE = 20;

function defaultExpiry() {
  const value = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
  value.setSeconds(0, 0);
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function AdminCouponWorkspace() {
  const { locale, displayCurrency, displayCurrencyConfig, formatLedgerMoney } = useI18n();
  const en = locale === "en";
  const label = (zh: string, english: string) => en ? english : zh;
  const [rows, setRows] = useState<AdminCouponCampaign[]>([]);
  const [status, setStatus] = useState<AdminCouponCampaignStatus | "">("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [generatedCode, setGeneratedCode] = useState("");
  const [form, setForm] = useState({
    name: "",
    amount: "",
    minAmount: "",
    maxRedemptions: "100",
    ttlDays: "30",
    productId: "",
    expiresAt: defaultExpiry(),
    code: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listAdminCouponCampaigns({ status, page, pageSize: PAGE_SIZE });
      setRows(result.items);
      setTotal(result.total);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const displayAmount = Number(form.amount);
      const displayMinimum = Number(form.minAmount);
      if (!Number.isFinite(displayAmount) || !Number.isFinite(displayMinimum) || displayAmount <= 0 || displayMinimum < 0) {
        throw new Error(label("券面额必须大于 0，使用门槛不能为负数。", "The value must be positive and the minimum spend cannot be negative."));
      }
      const amount = convertDisplayToCardHours(displayAmount, locale, displayCurrencyConfig, displayCurrency);
      const minimum = convertDisplayToCardHours(displayMinimum, locale, displayCurrencyConfig, displayCurrency);
      const created = await createAdminCouponCampaign({
        name: form.name.trim(),
        amount,
        min_amount: minimum,
        max_redemptions: Number(form.maxRedemptions),
        coupon_ttl_days: Number(form.ttlDays),
        ...(form.productId ? { product_id: Number(form.productId) } : {}),
        expires_at: new Date(form.expiresAt).toISOString(),
        ...(form.code.trim() ? { code: form.code.trim() } : {}),
      });
      setGeneratedCode(created.code);
      setForm((current) => ({ ...current, name: "", amount: "", minAmount: "", code: "" }));
      setPage(1);
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(row: AdminCouponCampaign) {
    if (busy || !["active", "disabled", "scheduled"].includes(row.status)) return;
    setBusy(true);
    setError("");
    try {
      await updateAdminCouponCampaignStatus(row.id, {
        status: row.status === "disabled" ? "active" : "disabled",
        expected_version: row.version,
      });
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    await navigator.clipboard.writeText(generatedCode);
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const statusText = (value: AdminCouponCampaignStatus) => ({
    active: label("进行中", "Active"),
    scheduled: label("待开始", "Scheduled"),
    disabled: label("已停用", "Disabled"),
    expired: label("已过期", "Expired"),
    exhausted: label("已领完", "Exhausted"),
  }[value]);

  return <section className="workspace-page admin-coupon-page">
    <div className="workspace-page__head"><p>OPERATIONS / COUPONS</p><h1>{label("优惠券活动", "Coupon campaigns")}</h1><span>{label("创建受总量、时间、账号和商品限制的兑换活动；兑换码明文只在创建成功后显示一次。", "Create bounded campaigns. The plaintext code is shown only once after creation.")}</span></div>
    {error && <div className="commerce-error">{error}</div>}
    {generatedCode && <div className="admin-coupon-code"><Check size={20}/><div><strong>{label("请立即保存兑换码", "Save this code now")}</strong><code>{generatedCode}</code><small>{label("服务器仅保存不可逆摘要，关闭后无法再次查看明文。", "Only a non-reversible digest is stored; the plaintext cannot be displayed again.")}</small></div><button type="button" onClick={() => void copyCode()}><Copy size={17}/>{label("复制", "Copy")}</button><button type="button" onClick={() => setGeneratedCode("")}>{label("已保存", "Saved")}</button></div>}
    <form className="admin-coupon-form" onSubmit={submit}>
      <label>{label("活动名称", "Campaign name")}<input required minLength={2} maxLength={64} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })}/></label>
      <label>{label(`券面额（${displayCurrency}）`, `Value (${displayCurrency})`)}<input required type="number" min="0.001" step="0.001" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })}/></label>
      <label>{label(`使用门槛（${displayCurrency}）`, `Minimum spend (${displayCurrency})`)}<input required type="number" min="0" step="0.001" value={form.minAmount} onChange={(event) => setForm({ ...form, minAmount: event.target.value })}/></label>
      <label>{label("最大发放量", "Redemption limit")}<input required type="number" min="1" max="1000000" value={form.maxRedemptions} onChange={(event) => setForm({ ...form, maxRedemptions: event.target.value })}/></label>
      <label>{label("领取后有效天数", "Coupon validity (days)")}<input required type="number" min="1" max="3650" value={form.ttlDays} onChange={(event) => setForm({ ...form, ttlDays: event.target.value })}/></label>
      <label>{label("活动截止时间", "Campaign expiry")}<input required type="datetime-local" value={form.expiresAt} onChange={(event) => setForm({ ...form, expiresAt: event.target.value })}/></label>
      <label>{label("限定商品 ID（可选）", "Product ID (optional)")}<input type="number" min="1" value={form.productId} onChange={(event) => setForm({ ...form, productId: event.target.value })}/></label>
      <label>{label("自定义兑换码（可选）", "Custom code (optional)")}<input minLength={8} maxLength={48} autoComplete="off" value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} placeholder={label("留空自动生成", "Leave blank to generate")}/></label>
      <button type="submit" disabled={busy}><Ticket size={18}/>{busy ? label("正在创建…", "Creating…") : label("创建兑换活动", "Create campaign")}</button>
    </form>
    <div className="admin-coupon-toolbar"><select value={status} onChange={(event) => { setPage(1); setStatus(event.target.value as AdminCouponCampaignStatus | ""); }}><option value="">{label("全部状态", "All statuses")}</option><option value="active">{label("进行中", "Active")}</option><option value="scheduled">{label("待开始", "Scheduled")}</option><option value="disabled">{label("已停用", "Disabled")}</option><option value="expired">{label("已过期", "Expired")}</option><option value="exhausted">{label("已领完", "Exhausted")}</option></select><button type="button" disabled={loading} onClick={() => void load()}><ArrowClockwise size={17}/>{label("刷新", "Refresh")}</button></div>
    <div className="admin-coupon-list">{rows.map((row) => <article key={row.id}><header><div><small>#{row.id} · {row.code_hint}</small><h2>{row.name}</h2></div><span className={`coupon-campaign-status status-${row.status}`}>{statusText(row.status)}</span></header><dl><div><dt>{label("面额 / 门槛", "Value / minimum")}</dt><dd>{formatLedgerMoney(row.amount)} / {formatLedgerMoney(row.min_amount)}</dd></div><div><dt>{label("已领取 / 上限", "Redeemed / limit")}</dt><dd>{row.redeemed_count} / {row.max_redemptions}</dd></div><div><dt>{label("适用商品", "Product")}</dt><dd>{row.product_id ? `#${row.product_id}` : label("全部使用型商品", "All usage products")}</dd></div><div><dt>{label("截止时间", "Expires")}</dt><dd>{formatDate(row.expires_at)}</dd></div></dl>{["active", "scheduled", "disabled"].includes(row.status) && <button type="button" disabled={busy} onClick={() => void toggle(row)}>{row.status === "disabled" ? <ToggleRight size={18}/> : <ToggleLeft size={18}/>} {row.status === "disabled" ? label("启用", "Enable") : label("停用", "Disable")}</button>}</article>)}</div>
    {!loading && !rows.length && <div className="data-empty">{label("当前筛选条件下没有兑换活动。", "No campaigns match this filter.")}</div>}
    <div className="admin-coupon-pagination"><button type="button" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>{label("上一页", "Previous")}</button><span>{page} / {pages} · {total}</span><button type="button" disabled={page >= pages || loading} onClick={() => setPage((value) => value + 1)}>{label("下一页", "Next")}</button></div>
  </section>;
}
