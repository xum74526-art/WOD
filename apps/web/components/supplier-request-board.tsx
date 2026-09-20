"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Briefcase, FunnelSimple } from "@phosphor-icons/react";
import { listSupplierRequests, type BuyRequest, type PageMeta } from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, requestStatusLabel } from "@/lib/commerce-ui";

export function SupplierRequestBoard() {
  const [rows, setRows] = useState<(BuyRequest & { id: number })[]>([]); const [meta, setMeta] = useState<PageMeta | null>(null);
  const [filters, setFilters] = useState({ gpu_model: "", region: "", sort: "latest" }); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  async function load(next = filters) { setLoading(true); setError(""); try { const result = await listSupplierRequests(next); setRows(result.data); setMeta(result.meta); } catch (reason) { setError(errorMessage(reason)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  function submit(event: FormEvent) { event.preventDefault(); void load(filters); }
  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head commerce-head"><div><p>SUPPLIER / REQUEST RADAR</p><h1>可报价求购</h1><span>仅展示仍在报价窗口内的公开需求，自己的求购不会进入报价流程。</span></div><Link className="outline-link" href="/supplier/quotes">我的报价</Link></div>
    <form className="workspace-filter" onSubmit={submit}><FunnelSimple size={17} /><input value={filters.gpu_model} onChange={(e) => setFilters({ ...filters, gpu_model: e.target.value })} placeholder="筛选 GPU 型号" /><input value={filters.region} onChange={(e) => setFilters({ ...filters, region: e.target.value })} placeholder="地区代码" /><select value={filters.sort} onChange={(e) => setFilters({ ...filters, sort: e.target.value })}><option value="latest">最新发布</option><option value="deadline">即将截止</option><option value="budget">预算优先</option></select><button type="submit">查询</button></form>
    <div className="workspace-ledger supplier-ledger"><header><span>采购任务</span><span>供给匹配</span><span>预算</span><span>报价窗口</span></header>{loading ? <div className="commerce-loading">正在扫描可报价任务…</div> : error ? <div className="commerce-error">{error}{error.includes("审核") && <Link href="/supplier/apply">查看入驻状态</Link>}</div> : rows.length === 0 ? <div className="commerce-empty"><Briefcase size={25} /><strong>当前没有可报价任务</strong><span>新公开的采购任务会出现在这里。</span></div> : rows.map((row) => <Link href={`/supplier/requests/${row.id}`} key={row.id}><span><small>{row.request_no}</small><strong>{row.title}</strong></span><span><small>GPU / 数量</small><strong>{row.gpu_model} × {row.gpu_quantity}</strong><em>{row.region_codes.join(" / ") || "地区不限"}</em></span><span><small>单位预算</small><strong>{formatMoney(row.budget.amount, row.budget.currency, row.budget.unit)}</strong></span><span><small>{formatDate(row.quote_deadline_at)}</small><b className={`status-chip status-chip--${row.status}`}>{requestStatusLabel[row.status]}</b><ArrowRight size={15} /></span></Link>)}</div><p className="ledger-count">共 {meta?.total ?? 0} 条可报价任务</p>
  </section>;
}
