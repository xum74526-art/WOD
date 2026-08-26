"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CalendarPlus, Check, Clock, PencilSimple, Prohibit, Star } from "@phosphor-icons/react";
import { BuyRequestEditor } from "@/components/buy-request-editor";
import { acceptQuote, closeBuyRequest, decideQuote, extendBuyRequest, getBuyerRequest, listBuyerQuotes, publishBuyRequest, type BuyRequest, type Quote } from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, quoteStatusLabel, requestStatusLabel } from "@/lib/commerce-ui";

export function BuyerRequestDetail({ requestId }: { requestId: number }) {
  const router = useRouter();
  const [row, setRow] = useState<BuyRequest | null>(null); const [quotes, setQuotes] = useState<Quote[]>([]);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(""); const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState(false); const [extending, setExtending] = useState(false); const [newDeadline, setNewDeadline] = useState("");
  const load = useCallback(async () => { setError(""); try { const [request, quoteResult] = await Promise.all([getBuyerRequest(requestId), listBuyerQuotes(requestId)]); setRow(request); setQuotes(quoteResult.data.quotes); } catch (reason) { setError(errorMessage(reason)); } }, [requestId]);
  useEffect(() => { void load(); }, [load]);
  async function act(name: string, action: () => Promise<unknown>) { setBusy(name); setError(""); setSuccess(""); try { await action(); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); } }
  if (error && !row) return <section className="workspace-page"><div className="commerce-error">{error}<Link href="/account/requests">返回列表</Link></div></section>;
  if (!row) return <section className="workspace-page"><div className="commerce-loading">正在读取采购台账…</div></section>;
  return <section className="workspace-page commerce-workspace">
    <Link className="dossier-back" href="/account/requests"><ArrowLeft size={14} />返回我的求购</Link>
    <div className="buyer-brief"><header><div><p>{row.request_no}</p><h1>{row.title}</h1><span className={`status-chip status-chip--${row.status}`}>{requestStatusLabel[row.status]}</span></div><aside><small>预算上限</small><strong>{formatMoney(row.budget.amount, row.budget.currency, row.budget.unit)}</strong><span><Clock size={13} />{formatDate(row.quote_deadline_at)} 截止</span></aside></header>
      <div className="buyer-brief__actions">{row.status === "draft" && <><button disabled={Boolean(busy)} onClick={() => setEditing((value) => !value)}><PencilSimple size={15} />{editing ? "收起编辑" : "编辑草稿"}</button><button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void act("publish", () => publishBuyRequest(requestId, row.version!))}>{busy === "publish" ? "发布中…" : "确认并公开求购"}</button></>}{["published", "negotiating"].includes(row.status) && <><button disabled={Boolean(busy)} onClick={() => { setExtending((value) => !value); setNewDeadline(""); }}><CalendarPlus size={15} />延长截止时间</button><button className="commerce-danger" disabled={Boolean(busy)} onClick={() => { const reason = window.prompt("请输入关闭原因", "需求已变化"); if (reason) void act("close", () => closeBuyRequest(requestId, row.version!, reason)); }}>关闭求购</button></>}</div>
      {extending && <form className="deadline-editor" onSubmit={(event) => { event.preventDefault(); if (!newDeadline) return; void act("extend", async () => { await extendBuyRequest(requestId, row.version!, new Date(newDeadline).toISOString()); setExtending(false); setSuccess("报价截止时间已延长"); }); }}><div><strong>延长报价窗口</strong><span>新时间必须晚于当前截止时间 {formatDate(row.quote_deadline_at)}</span></div><input required type="datetime-local" value={newDeadline} onChange={(event) => setNewDeadline(event.target.value)} /><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "extend" ? "更新中…" : "确认延期"}</button></form>}
      <dl><div><dt>GPU 配置</dt><dd>{row.gpu_model} × {row.gpu_quantity}</dd></div><div><dt>地区</dt><dd>{row.region_codes.join(" / ") || "不限"}</dd></div><div><dt>预计时长</dt><dd>{row.expected_duration_hours ? `${row.expected_duration_hours} 小时` : "待协商"}</dd></div><div><dt>当前版本</dt><dd>V{row.version}</dd></div></dl>
      <section><h2>部署要求</h2><p>{row.requirements || "未补充其他要求。"}</p></section>
    </div>
    {row.status === "draft" && editing && <BuyRequestEditor row={row} onSaved={async () => { await load(); setEditing(false); setSuccess("求购草稿已保存"); }} onDeleted={() => router.push("/account/requests")} />}
    {error && <div className="commerce-error">{error}</div>}{success && <div className="commerce-success">{success}</div>}
    <section className="quote-comparison"><header><div><p>QUOTE COMPARISON</p><h2>商家报价</h2></div><span>{quotes.length} 份可见报价</span></header>
      {quotes.length === 0 ? <div className="commerce-empty"><strong>{row.status === "draft" ? "公开求购后才能接收报价" : "正在等待商家报价"}</strong><span>草稿报价不会向买家展示。</span></div> : quotes.map((quote) => <article key={quote.id}><header><div><small>{quote.quote_no}</small><strong>{quote.supplier?.company_name || quote.supplier?.display_name || "第三方商家"}</strong></div><b className={`status-chip status-chip--${quote.status}`}>{quoteStatusLabel[quote.status]}</b></header><div className="quote-price"><small>单位报价</small><strong>{formatMoney(quote.price.amount, quote.price.currency, quote.price.unit)}</strong></div><dl><div><dt>可用数量</dt><dd>{quote.available_quantity}</dd></div><div><dt>交付时间</dt><dd>{quote.delivery_time_hours === null ? "待协商" : `${quote.delivery_time_hours} 小时`}</dd></div><div><dt>有效期</dt><dd>{formatDate(quote.valid_until)}</dd></div></dl><p>{quote.service_description || "商家未补充服务说明。"}</p>{["submitted", "shortlisted"].includes(quote.status) && !["matched", "closed"].includes(row.status) && <footer>{quote.status === "submitted" && <button disabled={Boolean(busy)} onClick={() => void act(`shortlist-${quote.id}`, () => decideQuote(requestId, quote.id, "shortlist", quote.version))}><Star size={14} />列为候选</button>}<button disabled={Boolean(busy)} onClick={() => void act(`reject-${quote.id}`, () => decideQuote(requestId, quote.id, "reject", quote.version))}><Prohibit size={14} />不采用</button><button className="commerce-primary" disabled={Boolean(busy) || quote.is_expired} onClick={() => void act(`accept-${quote.id}`, async () => { const order = await acceptQuote(requestId, quote.id, row.version!, quote.version); setSuccess(`已生成订单 ${order.order_no}，当前状态：待确认`); })}><Check size={14} />接受并生成订单</button></footer>}</article>)}
    </section>
  </section>;
}
