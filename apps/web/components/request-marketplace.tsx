"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Clock, FunnelSimple, MapPin, Plus, SquaresFour } from "@phosphor-icons/react";
import { listPublicRequests, type BuyRequest, type PageMeta } from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, requestStatusLabel } from "@/lib/commerce-ui";

export function RequestMarketplace() {
  const [rows, setRows] = useState<BuyRequest[]>([]);
  const [meta, setMeta] = useState<PageMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ gpu_model: "", region: "", sort: "latest" });

  async function load(next = filters) {
    setLoading(true); setError("");
    try { const result = await listPublicRequests(next); setRows(result.data); setMeta(result.meta); }
    catch (reason) { setError(errorMessage(reason, "无法读取公开求购")); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  function submit(event: FormEvent) { event.preventDefault(); void load(filters); }
  return <>
    <section className="request-command">
      <div><span>OPEN DISPATCHES</span><strong>{meta?.total ?? "—"}</strong><small>条公开采购任务</small></div>
      <Link className="primary-link" href="/requests/new"><Plus size={16} />发布求购</Link>
    </section>
    <form className="request-filter" onSubmit={submit}>
      <FunnelSimple size={18} />
      <label><span>GPU 型号</span><input value={filters.gpu_model} onChange={(event) => setFilters({ ...filters, gpu_model: event.target.value })} placeholder="例如 H100" /></label>
      <label><span>地区代码</span><input value={filters.region} onChange={(event) => setFilters({ ...filters, region: event.target.value })} placeholder="例如 CN-SH" /></label>
      <label><span>排序</span><select value={filters.sort} onChange={(event) => setFilters({ ...filters, sort: event.target.value })}><option value="latest">最新发布</option><option value="deadline">即将截止</option><option value="budget">预算从低到高</option></select></label>
      <button type="submit">应用筛选</button>
    </form>
    <section className="dispatch-ledger" aria-live="polite">
      <header><span>采购任务</span><span>需求配置</span><span>预算上限</span><span>报价窗口</span><span>状态</span></header>
      {loading ? <div className="commerce-loading">正在同步采购任务…</div> : error ? <div className="commerce-error">{error}<button type="button" onClick={() => void load()}>重新加载</button></div> : rows.length === 0 ? <div className="commerce-empty"><SquaresFour size={25} /><strong>当前没有符合条件的公开求购</strong><span>买家发布后会实时出现在这里。</span></div> : rows.map((row) => <Link href={`/requests/${row.request_no}`} className="dispatch-row" key={row.request_no}>
        <span className="dispatch-title"><small>{row.request_no}</small><strong>{row.title}</strong><em><MapPin size={12} />{row.region_codes.join(" / ") || "地区不限"}</em></span>
        <span><small>GPU / 数量</small><strong>{row.gpu_model} × {row.gpu_quantity}</strong><em>{row.min_gpu_memory_gb ? `≥ ${row.min_gpu_memory_gb} GB` : "显存不限"}</em></span>
        <span className="dispatch-money"><small>单位预算</small><strong>{formatMoney(row.budget.amount, row.budget.currency, row.budget.unit)}</strong></span>
        <span><small>截止</small><strong><Clock size={13} />{formatDate(row.quote_deadline_at)}</strong></span>
        <span><b className={`status-chip status-chip--${row.status}`}>{requestStatusLabel[row.status]}</b><ArrowRight size={16} /></span>
      </Link>)}
    </section>
  </>;
}
