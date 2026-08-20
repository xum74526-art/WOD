"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, NoteBlank } from "@phosphor-icons/react";
import { listSupplierQuotes, type Quote } from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, quoteStatusLabel } from "@/lib/commerce-ui";

export function SupplierQuotes() {
  const [rows, setRows] = useState<Quote[]>([]); const [status, setStatus] = useState(""); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  async function load(next = status) { setLoading(true); setError(""); try { setRows((await listSupplierQuotes(next)).data); } catch (reason) { setError(errorMessage(reason)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  return <section className="workspace-page commerce-workspace"><div className="workspace-page__head commerce-head"><div><p>SUPPLIER / QUOTES</p><h1>我的报价</h1><span>跟踪草稿、买家候选和最终接受结果。</span></div><Link className="primary-link" href="/supplier/requests">寻找求购</Link></div><div className="commerce-tabs">{[["", "全部"], ["draft", "草稿"], ["submitted", "已提交"], ["shortlisted", "候选"], ["accepted", "已接受"], ["withdrawn", "已撤回"]].map(([value, label]) => <button className={status === value ? "active" : ""} key={value} onClick={() => { setStatus(value); void load(value); }}>{label}</button>)}</div><div className="workspace-ledger"><header><span>报价 / 求购</span><span>报价</span><span>交付</span><span>状态</span></header>{loading ? <div className="commerce-loading">正在读取报价台账…</div> : error ? <div className="commerce-error">{error}</div> : rows.length === 0 ? <div className="commerce-empty"><NoteBlank size={25} /><strong>暂无报价</strong><span>进入可报价求购创建第一份报价。</span></div> : rows.map((quote) => <Link href={`/supplier/requests/${quote.buy_request_id}`} key={quote.id}><span><small>{quote.quote_no}</small><strong>{quote.request?.title}</strong><em>{quote.request?.request_no}</em></span><span><small>单位报价</small><strong>{formatMoney(quote.price.amount, quote.price.currency, quote.price.unit)}</strong></span><span><small>数量 / 有效期</small><strong>{quote.available_quantity} 张 · {formatDate(quote.valid_until)}</strong></span><span><b className={`status-chip status-chip--${quote.status}`}>{quoteStatusLabel[quote.status]}</b><ArrowRight size={15} /></span></Link>)}</div></section>;
}
