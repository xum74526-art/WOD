"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Receipt, ShieldCheck } from "@phosphor-icons/react";
import { initiateAdminRefund, listAdminRefunds, type RefundRequest } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const labels: Record<RefundRequest["status"], string> = {
  requested: "待处理",
  requires_manual: "待平台退款",
  processing: "处理中",
  completed: "已退款",
  rejected: "已拒绝",
};

export function AdminRefundWorkspace() {
  const [rows, setRows] = useState<RefundRequest[]>([]);
  const [status, setStatus] = useState("requested");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try { setRows(await listAdminRefunds(status || undefined)); }
    catch (reason) { setError(errorMessage(reason)); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  async function initiate(row: RefundRequest) {
    if (!window.confirm(`确认通过 Ping++ 向买家原路退款 ${row.currency} ${row.amount}？提交后请勿重复操作。`)) return;
    const note = window.prompt("处理备注（可选）", "管理员审核通过，发起原路退款") || undefined;
    setBusy(row.id); setError("");
    try { await initiateAdminRefund(row.id, row.version, note); await load(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(null); }
  }

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / REFUNDS</p><h1>退款处理</h1><span>审核后由 Ping++ 发起原路退款；商家款项保持冻结，只有验签通过的 refund.succeeded 回调才会完成账本冲销。</span></div>
    <div className="refund-toolbar"><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="requested">待发起</option><option value="processing">Ping++ 处理中</option><option value="completed">已退款</option><option value="">全部</option></select><button onClick={() => void load()}><ArrowClockwise size={15}/>刷新</button></div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="refund-list">{rows.length ? rows.map((row) => <article key={row.id}>
      <header><div><small>{row.refund_no} · {row.payment_no}</small><h2>{row.order_no}</h2></div><b className={`status-chip status-chip--${row.status === "completed" ? "published" : "pending_review"}`}>{labels[row.status]}</b></header>
      <dl><div><dt>退款金额</dt><dd>{row.currency} {row.amount}</dd></div><div><dt>支付渠道</dt><dd>{row.provider}</dd></div><div><dt>失败原因</dt><dd>{row.reason}</dd></div><div><dt>申请时间</dt><dd>{formatDate(row.requested_at)}</dd></div></dl>
      <footer><span><ShieldCheck size={15}/>商家款项未释放</span>{row.status === "requested" && <button className="commerce-primary" disabled={busy === row.id} onClick={() => void initiate(row)}><Receipt size={15}/>{busy === row.id ? "提交中…" : "通过 Ping++ 退款"}</button>}</footer>
    </article>) : <div className="commerce-empty"><Receipt size={25}/><strong>当前没有退款工单</strong></div>}</div>
  </section>;
}
