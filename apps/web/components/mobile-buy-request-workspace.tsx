"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwise, CheckCircle, Handshake, Key, LockKey, Plus, Receipt, Storefront, WarningCircle } from "@phosphor-icons/react";
import {
  confirmMobileBuyRequestDeal,
  confirmMobileBuyRequestDelivery,
  counterMobileBuyQuote,
  createMobileBuyQuote,
  createMobileBuyRequest,
  declineMobileBuyRequestDeal,
  getMobileBuyRequest,
  getMobileBuyRequestCredential,
  listMobileBuyRequests,
  reportMobileBuyRequestDelivery,
  selectMobileBuyQuote,
  submitMobileBuyRequestCredential,
  withdrawMobileBuyQuote,
  type MobileBuyQuote,
  type MobileBuyQuoteInput,
  type MobileBuyRequest,
  type MobileBuyRequestCredential,
  type MobileBuyRequestDetail,
} from "@/lib/mobile-buy-request-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";
import {
  buyRequestIntentSignature,
  ensureBuyRequestIntent,
  normalizeBuyRequestContactPhone,
  type BuyRequestIntent,
} from "@/lib/web-business-contract";

const statuses: Record<string, string> = {
  published: "已提交",
  quoting: "方案协商中",
  active: "待回应",
  countered: "待回应",
  withdrawn: "已撤回",
  selected: "已选定",
  quote_selected: "已选定方案",
  buyer_selected: "等待商家确认",
  supplier_confirmed: "商家已确认",
  supplier_declined: "商家无法承接",
  platform_review: "平台审核中",
  platform_rejected: "平台未通过",
  credential_pending: "等待商家提交凭据",
  credential_submitted: "凭据审核中",
  credential_rejected: "凭据需重新提交",
  credential_released: "凭据已交付",
  delivery_disputed: "交付异议处理中",
  completed: "已完成",
  expired: "已过期",
  cancelled: "已取消",
};
const openRequestStatuses = new Set(["published", "quoting", "active"]);
const activeQuoteStatuses = new Set(["active", "countered", "revised"]);

type RequestPrefill = {
  create?: boolean;
  product_id?: number;
  supplier_id?: number;
  source?: string;
  product_name?: string;
  seller_name?: string;
  gpu_model?: string;
  gpu_variant?: string;
  quantity?: number;
  gpu_hours?: number;
  region?: string;
};

type QuoteDraft = { unit_price: string; total_price: string; available_at: string; message: string; expires_in_hours: string };
const emptyQuote: QuoteDraft = { unit_price: "", total_price: "", available_at: "", message: "", expires_in_hours: "24" };

function latestQuote(item: MobileBuyQuote) {
  return item.latest_revision || item.revisions?.at(-1) || item;
}

function dateTimeInput(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function canCounterQuote(view: "buyer" | "seller", request: MobileBuyRequest, item: MobileBuyQuote, hasDeal: boolean, enabled: boolean) {
  if (!enabled || hasDeal || !openRequestStatuses.has(request.status) || !activeQuoteStatuses.has(item.status) || item.can_counter === false) return false;
  const latest = latestQuote(item);
  const lastActor = "actor_role" in latest ? latest.actor_role : undefined;
  if (view === "buyer") return request.is_own === true && lastActor !== "buyer";
  return request.is_own !== true && lastActor !== "supplier" && lastActor !== "seller";
}

export function MobileBuyRequestWorkspace({ view, initialId, initialPrefill }: { view: "buyer" | "seller"; initialId?: number; initialPrefill?: RequestPrefill }) {
  const { capabilities } = usePlatformCapabilities();
  const directTradeEnabled = capabilities.direct_trade_enabled === true;
  const matchmakingEnabled = capabilities.matchmaking_enabled === true;
  const requestFlowEnabled = matchmakingEnabled;
  const [type, setType] = useState<"online" | "offline">("online");
  const [rows, setRows] = useState<MobileBuyRequest[]>([]);
  const [selected, setSelected] = useState<number | null>(initialId || null);
  const [detail, setDetail] = useState<MobileBuyRequestDetail | null>(null);
  const [creating, setCreating] = useState(Boolean(initialPrefill?.create));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [editingQuoteId, setEditingQuoteId] = useState<number | null>(null);
  const [quote, setQuote] = useState<QuoteDraft>(emptyQuote);
  const [credential, setCredential] = useState<MobileBuyRequestCredential | null>(null);
  const [credentialForm, setCredentialForm] = useState({ host: "", port: "22", username: "", auth_type: "password" as "password" | "private_key", secret: "", note: "" });
  const [issueReason, setIssueReason] = useState("");
  const requestSubmissionInFlight = useRef(false);
  const pendingBuyRequestIntent = useRef<BuyRequestIntent | null>(null);
  const [form, setForm] = useState({
    gpu_model: initialPrefill?.gpu_model || "",
    quantity: String(initialPrefill?.quantity || 1),
    gpu_hours: String(initialPrefill?.gpu_hours || 24),
    region: initialPrefill?.region || "",
    contact: "",
    phone: "",
    requirements_text: "",
    expires_in_hours: "72",
  });

  const loadDetail = useCallback(async (id: number) => {
    const next = await getMobileBuyRequest(id);
    setDetail(next);
    setSelected(id);
    setCredential(null);
    return next;
  }, []);

  const load = useCallback(async (preferredId?: number) => {
    setError("");
    try {
      const result = await listMobileBuyRequests(type, view);
      setRows(result);
      const id = preferredId || initialId || selected || result[0]?.id;
      if (id && result.some((row) => row.id === id)) await loadDetail(id);
      else if (result[0]) await loadDetail(result[0].id);
      else setDetail(null);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }, [initialId, loadDetail, selected, type, view]);

  useEffect(() => { void load(); }, [type, view]);

  const sellerQuote = useMemo(() => view === "seller" ? detail?.quotes[0] || null : null, [detail, view]);
  const canCreateSellerQuote = Boolean(
    view === "seller" && detail && !detail.request.is_own && !detail.deal && requestFlowEnabled &&
    openRequestStatuses.has(detail.request.status) && !sellerQuote,
  );

  function quoteInput(): MobileBuyQuoteInput {
    return {
      unit_price: quote.unit_price ? Number(quote.unit_price) : undefined,
      total_price: Number(quote.total_price),
      currency: detail?.request.currency || "CNY",
      available_at: quote.available_at ? new Date(quote.available_at).toISOString() : undefined,
      message: quote.message.trim() || undefined,
      expires_in_hours: Number(quote.expires_in_hours),
    };
  }

  function beginCounter(item: MobileBuyQuote) {
    const latest = latestQuote(item);
    setEditingQuoteId(item.id);
    setQuote({
      unit_price: latest.unit_price == null ? "" : String(latest.unit_price),
      total_price: String(latest.total_price),
      available_at: dateTimeInput(latest.available_at),
      message: latest.message || "",
      expires_in_hours: "24",
    });
  }

  function toggleCreateForm() {
    if (creating) pendingBuyRequestIntent.current = null;
    setCreating((value) => !value);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (requestSubmissionInFlight.current) return;
    const phone = normalizeBuyRequestContactPhone(form.phone);
    if (!phone) {
      setError("请输入有效联系电话（可使用 +国家区号）。");
      return;
    }
    const input = {
      request_type: type,
      gpu_model: form.gpu_model,
      quantity: Number(form.quantity),
      gpu_hours: type === "online" ? Number(form.gpu_hours) : undefined,
      currency: "CNY",
      region: form.region || undefined,
      billing_mode: type === "online" ? "card_hour" : "device",
      requirements: {
        product_id: initialPrefill?.product_id,
        supplier_id: initialPrefill?.supplier_id,
        source: initialPrefill?.source,
        product_name: initialPrefill?.product_name,
        seller_name: initialPrefill?.seller_name,
        gpu_variant: initialPrefill?.gpu_variant,
        note: form.requirements_text.trim() || undefined,
      },
      contact: form.contact.trim(), phone, expires_in_hours: Number(form.expires_in_hours),
    };
    const intent = ensureBuyRequestIntent(
      pendingBuyRequestIntent.current,
      buyRequestIntentSignature(input),
      () => crypto.randomUUID(),
    );
    pendingBuyRequestIntent.current = intent;
    requestSubmissionInFlight.current = true;
    setBusy("request"); setError(""); setMessage("");
    try {
      const row = await createMobileBuyRequest({
        ...input,
        client_request_id: intent.requestId,
      });
      pendingBuyRequestIntent.current = null;
      setCreating(false);
      setMessage("需求已提交，联系方式仅平台管理员可见。");
      await load(row.id);
    } catch (reason) { setError(errorMessage(reason)); } finally {
      requestSubmissionInFlight.current = false;
      setBusy("");
    }
  }

  async function submitQuote(event: FormEvent) {
    event.preventDefault();
    if (!detail || !Number.isFinite(Number(quote.total_price)) || Number(quote.total_price) < 0) return;
    setBusy("quote"); setError(""); setMessage("");
    try {
      if (editingQuoteId) await counterMobileBuyQuote(detail.request.id, editingQuoteId, quoteInput());
      else await createMobileBuyQuote(detail.request.id, quoteInput());
      setQuote(emptyQuote); setEditingQuoteId(null);
      setMessage(editingQuoteId ? "新一轮报价已提交，等待对方回应。" : "报价已提交，购买人不会看到您的私人联系方式。");
      await load(detail.request.id);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function selectQuote(item: MobileBuyQuote) {
    if (!detail) return;
    const prompt = directTradeEnabled
      ? `确认选择 ${item.supplier_name} 的报价 ¥${latestQuote(item).total_price}？`
      : `确认选择 ${item.supplier_name} 的方案？选择后商家仍需确认资源，平台审核通过后才进入 SSH 凭据交付。`;
    if (!window.confirm(prompt)) return;
    setBusy(`select-${item.id}`); setError(""); setMessage("");
    try {
      const result = await selectMobileBuyQuote(detail.request.id, item.id);
      setMessage(result.commerce_mode === "matchmaking" ? "方案已选定，正在等待商家确认资源；当前未创建资金订单，也未扣除卡时。请等待工作人员联系确认平台审核进度。" : "报价已选择，请按订单流程继续处理。");
      await load(detail.request.id);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function withdrawQuote(item: MobileBuyQuote) {
    if (!detail || !window.confirm("确认撤回当前报价？撤回后需要重新提交方案。")) return;
    setBusy("withdraw"); setError("");
    try { await withdrawMobileBuyQuote(detail.request.id, item.id); setMessage("报价已撤回。"); await load(detail.request.id); }
    catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function dealAction(action: "confirm" | "decline" | "delivery" | "report") {
    if (!detail?.deal) return;
    const deal = detail.deal;
    if (action === "decline" && !window.confirm("确认无法承接该需求？平台会结束本次撮合。")) return;
    if (action === "delivery" && !window.confirm("确认 SSH 凭据可正常连接并完成本次交付？")) return;
    if (action === "report" && !issueReason.trim()) return;
    setBusy(action); setError(""); setMessage("");
    try {
      if (action === "confirm") await confirmMobileBuyRequestDeal(detail.request.id, deal.id);
      if (action === "decline") await declineMobileBuyRequestDeal(detail.request.id, deal.id);
      if (action === "delivery") await confirmMobileBuyRequestDelivery(detail.request.id, deal.id);
      if (action === "report") await reportMobileBuyRequestDelivery(detail.request.id, deal.id, issueReason.trim());
      setIssueReason("");
      setMessage(action === "confirm" ? "资源已确认，等待平台审核。" : action === "decline" ? "已告知平台无法承接。" : action === "delivery" ? "交付已确认完成。" : "连接问题已提交平台处理。");
      await load(detail.request.id);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function submitCredential(event: FormEvent) {
    event.preventDefault();
    if (!detail?.deal) return;
    setBusy("credential"); setError(""); setMessage("");
    try {
      await submitMobileBuyRequestCredential(detail.request.id, detail.deal.id, {
        host: credentialForm.host.trim(), port: Number(credentialForm.port), username: credentialForm.username.trim(),
        auth_type: credentialForm.auth_type, secret: credentialForm.secret, note: credentialForm.note.trim() || undefined,
      });
      setCredentialForm({ host: "", port: "22", username: "", auth_type: "password", secret: "", note: "" });
      setMessage("SSH 凭据已加密提交，平台审核放行前购买人不可见。");
      await load(detail.request.id);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function revealCredential() {
    if (!detail?.deal) return;
    setBusy("reveal"); setError("");
    try { setCredential(await getMobileBuyRequestCredential(detail.request.id, detail.deal.id)); }
    catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function copyCredential() {
    if (!credential) return;
    await navigator.clipboard.writeText(`${credential.username}@${credential.host}:${credential.port}\n${credential.secret || ""}`);
    setMessage("连接信息已复制，请妥善保管。");
  }

  return <section className="workspace-page mobile-request-workspace">
    <div className="workspace-page__head">
      <p>{view === "buyer" ? "BUYER / REQUESTS" : "SUPPLIER / REQUESTS"}</p>
      <h1>{view === "buyer" ? "需求与方案" : "需求市场"}</h1>
      <span>{view === "buyer" ? "匿名接收商家报价，双方确认后由平台审核并托管交付凭据。" : "按需求编号提供方案；购买人的身份与联系方式不会向商家公开。"}</span>
    </div>
    <div className="commerce-tabs">
      <button className={type === "online" ? "active" : ""} onClick={() => setType("online")}>在线算力</button>
      <button className={type === "offline" ? "active" : ""} onClick={() => setType("offline")}>线下设备</button>
      {view === "buyer" && requestFlowEnabled && <button className="request-create-trigger" onClick={toggleCreateForm}><Plus size={14}/>提交需求</button>}
    </div>
    {error && <div className="commerce-error">{error}</div>}
    {message && <div className="commerce-success">{message}</div>}
    {creating && requestFlowEnabled && <form className="mobile-request-form" onSubmit={create}>
      <label>GPU 型号<input required value={form.gpu_model} onChange={(event) => setForm({ ...form, gpu_model: event.target.value })} placeholder="RTX4090 / A800"/></label>
      <label>数量<input required min="1" type="number" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })}/></label>
      {type === "online" && <label>预计使用时长（小时）<input required min="1" type="number" value={form.gpu_hours} onChange={(event) => setForm({ ...form, gpu_hours: event.target.value })}/></label>}
      <label>联系人<input required maxLength={50} value={form.contact} onChange={(event) => setForm({ ...form, contact: event.target.value })} placeholder="仅平台管理员可见"/></label>
      <label>联系电话<input required type="tel" inputMode="tel" maxLength={32} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value.slice(0, 32) })} placeholder="可填写国家区号，仅平台管理员可见"/></label>
      <label>地区<input value={form.region} onChange={(event) => setForm({ ...form, region: event.target.value })}/></label>
      <label>有效小时<input min="1" max="720" type="number" value={form.expires_in_hours} onChange={(event) => setForm({ ...form, expires_in_hours: event.target.value })}/></label>
      <label className="mobile-request-form__wide">补充需求<textarea rows={3} maxLength={1000} value={form.requirements_text} onChange={(event) => setForm({ ...form, requirements_text: event.target.value })} placeholder="网络、CUDA、镜像、交付时间等，可留空"/></label>
      <button className="commerce-primary" disabled={Boolean(busy)}>{busy === "request" ? "正在提交…" : "提交需求"}</button>
      <p className="mobile-request-form__notice">提交不会扣除卡时，也不会自动生成订单。本流程不充值，联系方式仅平台管理员用于协调。</p>
    </form>}
    <div className="mobile-request-console">
      <aside>
        <header><strong>{view === "buyer" ? "我的需求" : "可接需求"}</strong><b>{rows.length}</b></header>
        {rows.length ? rows.map((row) => <button className={selected === row.id ? "active" : ""} key={row.id} onClick={() => void loadDetail(row.id)}>
          <span><strong>{row.gpu_model} × {row.quantity}</strong><small>{view === "seller" ? `匿名需求 #${row.id}` : `我的需求 #${row.id}`} · {formatDate(row.created_at)}</small></span>
          <b>{view === "seller" && row.is_own ? "我的需求 · 仅查看" : view === "seller" && row.targeted_to_me ? "定向需求" : statuses[row.status] || row.status}</b>
        </button>) : <div className="mobile-inline-empty">暂无需求</div>}
      </aside>
      <main>{detail ? <>
        <header><div><small>{view === "seller" ? `ANONYMOUS REQUEST #${detail.request.id}` : `REQUEST #${detail.request.id}`}</small><h2>{detail.request.gpu_model} × {detail.request.quantity}</h2><span>{detail.request.request_type === "online" ? `${detail.request.gpu_hours || 0} 卡时` : "线下设备"} · {detail.request.region || "地区不限"}</span></div><b>{statuses[detail.deal?.status || detail.request.status] || detail.deal?.status || detail.request.status}</b></header>
        <div className="mobile-request-facts">
          <span><small>服务价格</small><strong>询价</strong></span><span><small>交易方式</small><strong>平台撮合</strong></span><span><small>报价数</small><strong>{detail.request.quote_count}</strong></span><span><small>截止时间</small><strong>{formatDate(detail.request.expires_at)}</strong></span>
        </div>
        {view === "seller" && <div className="workspace-service-note"><LockKey size={16}/>购买人身份、联系人和手机号已隐藏；您只能查看和修改自己的报价。</div>}
        <section className="mobile-quote-list">
          <h3><Receipt size={17}/>{view === "buyer" ? "报价记录" : "我的报价"}</h3>
          {detail.quotes.length ? detail.quotes.map((item) => {
            const latest = latestQuote(item);
            return <article key={item.id} className="matchmaking-quote-card">
              <span><strong>{view === "seller" ? "我的方案" : item.supplier_name || "认证商家"}</strong><small>{latest.message || "无补充说明"}</small><small>第 {item.revision_count || item.revisions?.length || 1} 轮 · {latest.available_at ? `${formatDate(latest.available_at)} 可交付` : "交付时间待确认"}</small></span>
              <b>¥{latest.total_price}</b><em>{statuses[item.status] || item.status}</em>
              <div className="matchmaking-actions">
                {canCounterQuote(view, detail.request, item, Boolean(detail.deal), matchmakingEnabled) && <button type="button" disabled={Boolean(busy)} onClick={() => beginCounter(item)}>{view === "buyer" ? "还价" : "修改方案"}</button>}
                {view === "seller" && item.can_withdraw !== false && !detail.deal && matchmakingEnabled && openRequestStatuses.has(detail.request.status) && activeQuoteStatuses.has(item.status) && <button className="danger" type="button" disabled={Boolean(busy)} onClick={() => void withdrawQuote(item)}>撤回</button>}
                {view === "buyer" && activeQuoteStatuses.has(item.status) && !detail.deal && (directTradeEnabled || matchmakingEnabled) && <button className="commerce-primary" type="button" disabled={Boolean(busy)} onClick={() => void selectQuote(item)}>{directTradeEnabled ? "选择报价" : "选择方案"}</button>}
              </div>
              {editingQuoteId === item.id && (
                <QuoteForm
                  value={quote}
                  onChange={setQuote}
                  onSubmit={submitQuote}
                  onCancel={() => {
                    setEditingQuoteId(null);
                    setQuote(emptyQuote);
                  }}
                  busy={busy === "quote"}
                  label={view === "buyer" ? "提交还价" : "保存新方案"}
                />
              )}
            </article>;
          }) : <div className="mobile-inline-empty">暂无报价</div>}
        </section>
        {view === "seller" && detail.request.is_own && <div className="workspace-service-note">这是当前账号提交的需求，不能给自己的需求报价。</div>}
        {view === "seller" && canCreateSellerQuote && <QuoteForm value={quote} onChange={setQuote} onSubmit={submitQuote} busy={busy === "quote"} label="提交商家方案"/>}
        {detail.deal && <section className="matchmaking-deal">
          <header><div><small>PLATFORM ESCROW</small><h3>撮合与交付</h3></div><b>#{detail.deal.id}</b></header>
          <ol className="matchmaking-timeline">
            {(detail.events || []).length ? detail.events!.map((event) => <li key={event.id}><span><CheckCircle size={16}/></span><div><strong>{event.label || statuses[event.status || ""] || event.event_type || "状态更新"}</strong><small>{event.message || formatDate(event.created_at)}</small></div></li>) : <li><span><CheckCircle size={16}/></span><div><strong>{statuses[detail.deal.status] || detail.deal.status}</strong><small>{formatDate(detail.deal.updated_at)}</small></div></li>}
          </ol>
          {view === "seller" && (detail.deal.can_supplier_confirm || detail.deal.can_supplier_decline) && <div className="matchmaking-action-panel"><h4>确认资源</h4><p>确认后由平台审核方案；无法提供时请及时拒绝。</p><div className="matchmaking-actions">{detail.deal.can_supplier_decline && <button className="danger" disabled={Boolean(busy)} onClick={() => void dealAction("decline")}>无法承接</button>}{detail.deal.can_supplier_confirm && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void dealAction("confirm")}>确认可提供</button>}</div></div>}
          {view === "seller" && detail.deal.can_submit_credential && <form className="matchmaking-credential-form" onSubmit={submitCredential}><h4><Key size={17}/>提交 SSH 凭据</h4><p>凭据会加密托管，平台审核放行前购买人不可见。</p><label>主机地址<input required value={credentialForm.host} onChange={(event) => setCredentialForm({ ...credentialForm, host: event.target.value })}/></label><label>端口<input required min="1" max="65535" type="number" value={credentialForm.port} onChange={(event) => setCredentialForm({ ...credentialForm, port: event.target.value })}/></label><label>用户名<input required value={credentialForm.username} onChange={(event) => setCredentialForm({ ...credentialForm, username: event.target.value })}/></label><label>认证方式<select value={credentialForm.auth_type} onChange={(event) => setCredentialForm({ ...credentialForm, auth_type: event.target.value as "password" | "private_key" })}><option value="password">密码</option><option value="private_key">私钥</option></select></label><label className="wide">{credentialForm.auth_type === "password" ? "密码" : "私钥"}<textarea required rows={credentialForm.auth_type === "password" ? 2 : 6} value={credentialForm.secret} onChange={(event) => setCredentialForm({ ...credentialForm, secret: event.target.value })}/></label><label className="wide">交付说明<textarea rows={2} value={credentialForm.note} onChange={(event) => setCredentialForm({ ...credentialForm, note: event.target.value })}/></label><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "credential" ? "加密提交中…" : "提交平台审核"}</button></form>}
          {view === "buyer" && detail.deal.can_buyer_view_credential && !credential && <button className="matchmaking-reveal" disabled={Boolean(busy)} onClick={() => void revealCredential()}><Key size={17}/>{busy === "reveal" ? "正在安全读取…" : "查看平台已放行的 SSH 凭据"}</button>}
          {view === "buyer" && credential && <div className="matchmaking-credential-card"><header><div><small>SSH CONNECTION</small><h4>{credential.username}@{credential.host}:{credential.port}</h4></div><button onClick={() => void copyCredential()}>复制</button></header><pre>{credential.secret || "凭据内容不可用"}</pre>{credential.note && <p>{credential.note}</p>}<div className="matchmaking-actions">{detail.deal.can_report && <button className="danger" onClick={() => setIssueReason((value) => value || "无法连接 SSH")}>报告问题</button>}{detail.deal.can_buyer_confirm && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void dealAction("delivery")}>确认可用并完成</button>}</div>{issueReason && <div className="matchmaking-issue"><label>问题说明<textarea maxLength={500} value={issueReason} onChange={(event) => setIssueReason(event.target.value)}/></label><button disabled={Boolean(busy) || !issueReason.trim()} onClick={() => void dealAction("report")}><WarningCircle size={15}/>提交平台处理</button></div>}</div>}
        </section>}
      </> : <div className="commerce-empty"><Receipt size={26}/><strong>选择一条需求</strong></div>}</main>
    </div>
  </section>;
}

function QuoteForm({ value, onChange, onSubmit, onCancel, busy, label }: { value: QuoteDraft; onChange: (next: QuoteDraft) => void; onSubmit: (event: FormEvent) => void; onCancel?: () => void; busy: boolean; label: string }) {
  return <form className="mobile-quote-form matchmaking-quote-form" onSubmit={onSubmit}>
    <header><Storefront size={18}/><strong>{label}</strong></header>
    <label>单位价格<input min="0" step="0.01" type="number" value={value.unit_price} onChange={(event) => onChange({ ...value, unit_price: event.target.value })}/></label>
    <label>总报价<input required min="0" step="0.01" type="number" value={value.total_price} onChange={(event) => onChange({ ...value, total_price: event.target.value })}/></label>
    <label>最早交付时间<input type="datetime-local" value={value.available_at} onChange={(event) => onChange({ ...value, available_at: event.target.value })}/></label>
    <label>有效小时<input required min="1" max="720" type="number" value={value.expires_in_hours} onChange={(event) => onChange({ ...value, expires_in_hours: event.target.value })}/></label>
    <label className="wide">方案说明<textarea maxLength={1000} rows={3} value={value.message} onChange={(event) => onChange({ ...value, message: event.target.value })}/></label>
    <div className="matchmaking-actions">{onCancel && <button type="button" onClick={onCancel}>取消</button>}<button className="commerce-primary" disabled={busy}><Handshake size={15}/>{busy ? "提交中…" : label}</button></div>
  </form>;
}
