"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ClipboardText, Plus } from "@phosphor-icons/react";
import { listBuyerRequests, type BuyRequest, type PageMeta } from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, requestStatusLabel } from "@/lib/commerce-ui";

export function BuyerRequests() {
  const [rows, setRows] = useState<BuyRequest[]>([]); const [meta, setMeta] = useState<PageMeta | null>(null);
  const [status, setStatus] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  async function load(next = status) { setLoading(true); setError(""); try { const result = await listBuyerRequests(next); setRows(result.data); setMeta(result.meta); } catch (reason) { setError(errorMessage(reason)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head commerce-head"><div><p>BUYER / PROCUREMENT</p><h1>我的求购</h1><span>草稿、公开报价和匹配结果都以真实业务状态展示。</span></div><Link className="primary-link" href="/requests/new"><Plus size={16} />发布求购</Link></div>
    <div className="commerce-tabs" role="tablist">{[["", "全部"], ["draft", "草稿"], ["published", "开放报价"], ["negotiating", "洽谈中"], ["matched", "已匹配"], ["closed", "已关闭"]].map(([value, label]) => <button className={status === value ? "active" : ""} type="button" key={value} onClick={() => { setStatus(value); void load(value); }}>{label}</button>)}</div>
    <div className="workspace-ledger"><header><span>任务</span><span>配置</span><span>预算</span><span>截止 / 状态</span></header>
      {loading ? <div className="commerce-loading">正在读取求购记录…</div> : error ? <div className="commerce-error">{error}<Link href="/login">检查登录</Link></div> : rows.length === 0 ? <div className="commerce-empty"><ClipboardText size={25} /><strong>这个分类还没有求购</strong><span>发布后会先保存为草稿，由你确认公开。</span></div> : rows.map((row) => <Link href={`/account/requests/${row.id}`} key={row.request_no}><span><small>{row.request_no}</small><strong>{row.title}</strong></span><span><small>GPU / 数量</small><strong>{row.gpu_model} × {row.gpu_quantity}</strong></span><span><small>单位预算</small><strong>{formatMoney(row.budget.amount, row.budget.currency, row.budget.unit)}</strong></span><span><small>{formatDate(row.quote_deadline_at)}</small><b className={`status-chip status-chip--${row.status}`}>{requestStatusLabel[row.status]}</b><ArrowRight size={15} /></span></Link>)}
    </div><p className="ledger-count">共 {meta?.total ?? 0} 条记录</p>
  </section>;
}
