"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Bank, CheckCircle, Coins, LockKey, XCircle } from "@phosphor-icons/react";
import {
  cancelSupplierWithdrawal,
  createSupplierWithdrawal,
  getSupplierRevenue,
  type SupplierRevenue,
  type SupplierWithdrawal,
} from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const statusLabels: Record<SupplierWithdrawal["status"], string> = {
  requested: "待审核",
  approved: "待打款",
  rejected: "已驳回",
  paid: "已打款",
  cancelled: "已取消",
};

const initialForm = { amount: "", beneficiary_name: "", bank_name: "", bank_account_no: "" };

export function SupplierRevenueWorkspace() {
  const [data, setData] = useState<SupplierRevenue | null>(null);
  const [form, setForm] = useState(initialForm);
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState<number | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try { setData(await getSupplierRevenue()); }
    catch (reason) { setError(errorMessage(reason)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      await createSupplierWithdrawal(form);
      setForm(initialForm);
      await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  async function cancel(row: SupplierWithdrawal) {
    if (!window.confirm(`取消提现 ${row.currency} ${row.amount}？金额会立即退回可用余额。`)) return;
    setCancelling(row.id); setError("");
    try { await cancelSupplierWithdrawal(row.id, row.version); await load(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setCancelling(null); }
  }

  if (!data) return <section className="workspace-page"><div className="workspace-skeleton" />{error && <div className="commerce-error">{error}</div>}</section>;
  const cny = data.balances.find((item) => item.currency === "CNY") || { currency: "CNY", available: "0", frozen: "0" };
  return <section className="workspace-page settlement-workspace">
    <div className="workspace-page__head settlement-head"><div><p>SUPPLIER / SETTLEMENT</p><h1>收益与提现</h1><span>租期结束且无争议后 T+{data.policy.settlement_hold_hours / 24} 结算；提现由平台审核并线下打款。</span></div><button onClick={() => void load()}><ArrowClockwise size={16}/>刷新账本</button></div>

    <div className="settlement-balance-line">
      <article><small>可提现余额</small><strong><em>CNY</em>{cny.available}</strong><span>已扣除 {Number(data.policy.commission_rate) * 100}% 平台佣金</span></article>
      <div className="settlement-flow" aria-label="结算流程"><span className="active"><Coins/>可用余额</span><i>→</i><span><LockKey/>提现冻结</span><i>→</i><span><CheckCircle/>财务打款</span></div>
      <article><small>冻结余额</small><strong><em>CNY</em>{cny.frozen}</strong><span>含 T+1 待结算、争议及待审核提现</span></article>
    </div>

    <div className="settlement-columns">
      <form className="settlement-form" onSubmit={submit}>
        <header><Bank size={22}/><div><h2>申请提现</h2><p>管理员审核后通过银行转账打款。</p></div></header>
        <label><span>提现金额（CNY）</span><input required type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })}/></label>
        <label><span>收款人姓名</span><input required minLength={2} maxLength={64} autoComplete="name" value={form.beneficiary_name} onChange={(event) => setForm({ ...form, beneficiary_name: event.target.value })}/></label>
        <label><span>开户银行</span><input required minLength={2} maxLength={128} placeholder="例如 招商银行上海分行" value={form.bank_name} onChange={(event) => setForm({ ...form, bank_name: event.target.value })}/></label>
        <label><span>银行账号</span><input required inputMode="numeric" pattern="[0-9]{6,32}" autoComplete="off" placeholder="仅填写数字" value={form.bank_account_no} onChange={(event) => setForm({ ...form, bank_account_no: event.target.value.replace(/\D/g, "") })}/></label>
        <div className="settlement-security"><LockKey size={16}/><span>账户信息加密保存，商家列表只显示末四位。</span></div>
        <button className="commerce-primary" disabled={busy}>{busy ? "正在冻结余额…" : "冻结余额并提交审核"}</button>
      </form>

      <section className="settlement-history">
        <header><div><small>WITHDRAWAL LEDGER</small><h2>提现记录</h2></div><span>待处理 {data.summary.requested} · 已打款 {data.summary.paid}</span></header>
        {data.withdrawals.length ? data.withdrawals.map((row) => <article key={row.id}>
          <div className="settlement-history__main"><small>{row.withdrawal_no}</small><strong>{row.currency} {row.amount}</strong><span>{row.payout.bank_name} · {row.payout.account_no}</span></div>
          <div className="settlement-history__state"><b className={`status-chip status-chip--${row.status === "paid" ? "published" : row.status === "rejected" || row.status === "cancelled" ? "rejected" : "pending_review"}`}>{statusLabels[row.status]}</b><time>{formatDate(row.requested_at)}</time>{row.payment_reference && <small>流水 {row.payment_reference}</small>}</div>
          {row.status === "requested" && <button className="settlement-cancel" disabled={cancelling === row.id} onClick={() => void cancel(row)}><XCircle size={15}/>{cancelling === row.id ? "取消中…" : "取消申请"}</button>}
          {row.review_note && <p>{row.review_note}</p>}
        </article>) : <div className="commerce-empty"><Bank size={24}/><strong>暂无提现记录</strong><span>服务器收入结算后，可以从左侧提交第一笔提现。</span></div>}
      </section>
    </div>
    {error && <div className="commerce-error">{error}</div>}
  </section>;
}
