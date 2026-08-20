"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Bank, Check, Copy, Money, X } from "@phosphor-icons/react";
import {
  approveAdminWithdrawal,
  completeAdminWithdrawal,
  listAdminWithdrawals,
  rejectAdminWithdrawal,
  type SupplierWithdrawal,
} from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const statusLabels: Record<SupplierWithdrawal["status"], string> = {
  requested: "待审核", approved: "待打款", rejected: "已驳回", paid: "已打款", cancelled: "已取消",
};

export function AdminWithdrawalWorkspace() {
  const [rows, setRows] = useState<SupplierWithdrawal[]>([]);
  const [status, setStatus] = useState("requested");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try { setRows(await listAdminWithdrawals(status || undefined)); }
    catch (reason) { setError(errorMessage(reason)); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  async function action(row: SupplierWithdrawal, kind: "approve" | "reject" | "complete") {
    let task: Promise<SupplierWithdrawal>;
    if (kind === "approve") {
      const note = window.prompt("审核备注（可选）", "收款账户已核对") || undefined;
      task = approveAdminWithdrawal(row.id, row.version, note);
    } else if (kind === "reject") {
      const note = window.prompt("请输入驳回原因");
      if (!note?.trim()) return;
      task = rejectAdminWithdrawal(row.id, row.version, note.trim());
    } else {
      const reference = window.prompt("请输入银行转账流水号");
      if (!reference?.trim()) return;
      const note = window.prompt("打款备注（可选）", "线下银行转账已完成") || undefined;
      task = completeAdminWithdrawal(row.id, row.version, reference.trim(), note);
    }
    setBusy(row.id); setError("");
    try { await task; await load(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(null); }
  }

  return <section className="workspace-page commerce-workspace admin-settlement">
    <div className="workspace-page__head"><p>ADMIN / PAYOUTS</p><h1>商家提现结算</h1><span>先核对收款账户，再线下打款；银行流水登记后系统才扣除冻结余额。</span></div>
    <div className="refund-toolbar"><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="requested">待审核</option><option value="approved">待打款</option><option value="paid">已打款</option><option value="rejected">已驳回</option><option value="cancelled">已取消</option><option value="">全部</option></select><button onClick={() => void load()}><ArrowClockwise size={15}/>刷新</button></div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="admin-settlement-list">{rows.length ? rows.map((row) => <article key={row.id}>
      <header><div><small>{row.withdrawal_no}</small><h2>{row.supplier?.company_name || row.supplier?.display_name || `商家 #${row.supplier_id}`}</h2><span>{row.supplier?.email}</span></div><strong>{row.currency} {row.amount}</strong><b className={`status-chip status-chip--${row.status === "paid" ? "published" : row.status === "rejected" || row.status === "cancelled" ? "rejected" : "pending_review"}`}>{statusLabels[row.status]}</b></header>
      <div className="admin-bank-slip"><Bank size={20}/><dl><div><dt>收款人</dt><dd>{row.payout.beneficiary_name}</dd></div><div><dt>开户银行</dt><dd>{row.payout.bank_name}</dd></div><div><dt>银行账号</dt><dd>{row.payout.account_no}<button aria-label="复制银行账号" onClick={() => void navigator.clipboard.writeText(row.payout.account_no)}><Copy size={14}/></button></dd></div><div><dt>申请时间</dt><dd>{formatDate(row.requested_at)}</dd></div></dl></div>
      {row.review_note && <p>{row.review_note}</p>}{row.payment_reference && <p>银行流水：<strong>{row.payment_reference}</strong></p>}
      <footer>{row.status === "requested" && <><button disabled={busy === row.id} onClick={() => void action(row, "reject")}><X size={15}/>驳回并解冻</button><button className="commerce-primary" disabled={busy === row.id} onClick={() => void action(row, "approve")}><Check size={15}/>批准提现</button></>}{row.status === "approved" && <><button disabled={busy === row.id} onClick={() => void action(row, "reject")}><X size={15}/>驳回并解冻</button><button className="commerce-primary" disabled={busy === row.id} onClick={() => void action(row, "complete")}><Money size={15}/>登记已打款</button></>}</footer>
    </article>) : <div className="commerce-empty"><Bank size={25}/><strong>当前队列为空</strong><span>新的商家提现申请会进入这里。</span></div>}</div>
  </section>;
}
