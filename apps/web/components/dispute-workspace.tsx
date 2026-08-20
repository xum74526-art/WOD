"use client";

import { useCallback, useEffect, useState } from "react";
import { Gavel, Plus, ShieldWarning } from "@phosphor-icons/react";
import { createDispute, listDisputableOrders, listDisputes, type Dispute } from "@/lib/internal-api";
import type { Order } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

export function DisputeWorkspace() {
  const [rows, setRows] = useState<Dispute[]>([]); const [orders, setOrders] = useState<Order[]>([]); const [open, setOpen] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ order_id: "", reason: "service_unavailable", description: "" });
  const load = useCallback(async () => { try { const [cases, candidates] = await Promise.all([listDisputes(), listDisputableOrders()]); setRows(cases); setOrders(candidates); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await createDispute({ order_id: Number(form.order_id), reason: form.reason, description: form.description }); setOpen(false); setForm({ order_id: "", reason: "service_unavailable", description: "" }); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); } }
  return <section className="workspace-page internal-workspace"><div className="workspace-page__head"><p>ACCOUNT / RESOLUTION</p><h1>争议工单</h1><span>争议必须关联真实订单，平台处理过程会留下事件记录。</span></div>
    <div className="internal-toolbar"><strong>{rows.filter((row) => ["open", "under_review"].includes(row.status)).length} 个处理中</strong><button disabled={!orders.length} onClick={() => setOpen(!open)}><Plus size={16}/>发起争议</button></div>{error && <div className="commerce-error">{error}</div>}
    {open && <form className="dispute-form" onSubmit={submit}><label>关联订单<select value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })} required><option value="">选择订单</option>{orders.map((order) => <option value={order.id} key={order.id}>{order.order_no} · {order.snapshot.product?.name || order.snapshot.request?.title || "服务器租赁订单"}</option>)}</select></label><label>争议原因<select value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}><option value="service_unavailable">服务不可用</option><option value="not_delivered">未按约交付</option><option value="configuration_mismatch">配置不符</option><option value="billing_issue">计费问题</option><option value="other">其他</option></select></label><label>问题说明<textarea minLength={10} maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required /></label><button className="commerce-primary" disabled={busy}>{busy ? "提交中…" : "提交工单"}</button></form>}
    <div className="dispute-list">{rows.length === 0 ? <div className="internal-empty"><Gavel size={30}/><strong>没有争议工单</strong><span>{orders.length ? "如交付或计费出现问题，可关联订单发起。" : "当前没有可发起争议的订单。"}</span></div> : rows.map((row) => <article key={row.id}><ShieldWarning size={22}/><div><header><strong>{row.dispute_no}</strong><span>{row.status}</span></header><h2>{row.description}</h2><p>订单 #{row.order_id} · {row.reason}</p>{row.resolution && <blockquote>{row.resolution}</blockquote>}<time>{formatDate(row.updated_at)}</time></div></article>)}</div>
  </section>;
}
