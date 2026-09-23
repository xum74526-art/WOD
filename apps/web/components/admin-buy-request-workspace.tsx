"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowClockwise, CheckCircle, ClipboardText, Key, LockKey, ShieldCheck, Storefront, User, WarningCircle } from "@phosphor-icons/react";
import {
  approveAdminBuyRequestDeal,
  getAdminBuyRequest,
  getAdminBuyRequestCredential,
  listAdminBuyRequests,
  rejectAdminBuyRequestCredential,
  rejectAdminBuyRequestDeal,
  releaseAdminBuyRequestCredential,
  type AdminBuyRequestCredential,
  type AdminBuyRequestDetail,
  type AdminBuyRequestItem,
} from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { buyRequestAdditionalRequirements } from "@/lib/web-business-contract";
import { useI18n } from "@/components/locale-root";

const statusLabels: Record<string, string> = {
  published: "待报价",
  quoting: "方案协商中",
  active: "待回应",
  countered: "待回应",
  revised: "待回应",
  withdrawn: "已撤回",
  selected: "已选定",
  coordination_requested: "平台协调中",
  declined: "未选中",
  quote_selected: "已选定方案",
  buyer_selected: "等待商家确认",
  supplier_confirmed: "商家已确认",
  supplier_declined: "商家无法承接",
  platform_review: "待平台审核",
  platform_rejected: "平台未通过",
  credential_pending: "等待提交凭据",
  credential_submitted: "待审核凭据",
  credential_rejected: "凭据已退回",
  credential_released: "凭据已放行",
  delivery_disputed: "交付异议",
  completed: "已完成",
  expired: "已过期",
  closed: "已关闭",
  cancelled: "已取消",
  processing: "处理中",
  rejected: "未通过",
  pending_payment: "待付款",
};

const statusFilterGroups = [
  {
    label: "需要平台处理",
    values: ["platform_review", "credential_submitted", "delivery_disputed"],
  },
  {
    label: "撮合进行中",
    values: [
      "published",
      "quoting",
      "buyer_selected",
      "credential_pending",
      "credential_rejected",
      "credential_released",
      "quote_selected",
      "processing",
    ],
  },
  {
    label: "已结束",
    values: ["completed", "expired", "closed", "rejected"],
  },
] as const;

const eventLabels: Record<string, string> = {
  quote_history_initialized: "报价记录已建立",
  quote_submitted: "商家已提交方案",
  quote_countered: "方案已更新",
  quote_withdrawn: "商家已撤回方案",
  buyer_selected_quote: "买家已选择方案",
  supplier_confirmed: "商家已确认资源",
  supplier_declined: "商家无法承接",
  platform_approved: "平台审核已通过",
  platform_rejected: "平台审核未通过",
  credential_submitted: "商家已提交交付凭据",
  credential_released: "平台已放行交付凭据",
  credential_rejected: "交付凭据需重新提交",
  delivery_confirmed: "买家已确认交付",
  delivery_reported: "买家已报告交付问题",
};

function statusLabel(status?: string | null) {
  return (status && statusLabels[status]) || "状态待确认";
}

function timelineEventLabel(event: { event_type?: string; label?: string; status?: string }) {
  const eventType = event.event_type || event.label || "";
  return eventLabels[eventType] || statusLabel(event.status);
}

function metadata(row: AdminBuyRequestItem, key: string) {
  const value = row.requirements?.[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function targetLabel(row: AdminBuyRequestItem, supplierFallback: (id: number) => string, marketFallback: string) {
  if (row.target_supplier?.company_name) return row.target_supplier.company_name;
  const sellerName = metadata(row, "seller_name");
  if (sellerName) return sellerName;
  return row.targeted_supplier_id ? supplierFallback(row.targeted_supplier_id) : marketFallback;
}

export function AdminBuyRequestWorkspace() {
  const { t } = useI18n();
  const [rows, setRows] = useState<AdminBuyRequestItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [requestType, setRequestType] = useState<"" | "online" | "offline">("");
  const [keyword, setKeyword] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminBuyRequestDetail | null>(null);
  const [credential, setCredential] = useState<AdminBuyRequestCredential | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const detailRequirementNote = buyRequestAdditionalRequirements(detail?.request.requirements);

  const loadDetail = useCallback(async (id: number) => {
    setSelectedId(id);
    setCredential(null);
    setDetail(await getAdminBuyRequest(id));
  }, []);

  const load = useCallback(async (preferredId?: number) => {
    setLoading(true); setError("");
    try {
      const page = await listAdminBuyRequests({ status: status || undefined, requestType: requestType || undefined, keyword: keyword.trim() || undefined, pageSize: 100 });
      setRows(page.items); setTotal(page.total);
      const id = preferredId || selectedId || page.items[0]?.id;
      if (id && page.items.some((row) => row.id === id)) await loadDetail(id);
      else if (page.items[0]) await loadDetail(page.items[0].id);
      else { setSelectedId(null); setDetail(null); }
    } catch (reason) { setError(errorMessage(reason)); } finally { setLoading(false); }
  }, [keyword, loadDetail, requestType, selectedId, status]);

  useEffect(() => { void load(); }, [status, requestType]);
  function submit(event: FormEvent) { event.preventDefault(); void load(); }

  async function dealAction(action: "approve" | "reject" | "release" | "reject-credential") {
    if (!detail?.deal) return;
    const reason = action === "reject" || action === "reject-credential" ? window.prompt(t("admin.buyRequest.returnPrompt", "请输入退回原因（购买人与商家都可看到）"))?.trim() : "";
    if ((action === "reject" || action === "reject-credential") && !reason) return;
    if (action === "release" && !window.confirm(t("admin.buyRequest.releaseConfirm", "确认凭据内容已核验，可向购买人放行？"))) return;
    setBusy(action); setError(""); setMessage("");
    try {
      if (action === "approve") await approveAdminBuyRequestDeal(detail.request.id, detail.deal.id);
      if (action === "reject") await rejectAdminBuyRequestDeal(detail.request.id, detail.deal.id, reason!);
      if (action === "release") await releaseAdminBuyRequestCredential(detail.request.id, detail.deal.id);
      if (action === "reject-credential") await rejectAdminBuyRequestCredential(detail.request.id, detail.deal.id, reason!);
      setCredential(null);
      setMessage(action === "approve"
        ? t("admin.buyRequest.approved", "撮合方案已通过，等待商家加密提交 SSH 凭据。")
        : action === "release"
          ? t("admin.buyRequest.released", "凭据已向购买人放行。")
          : t("admin.buyRequest.returned", "已退回并记录原因。"));
      await load(detail.request.id);
    } catch (reasonValue) { setError(errorMessage(reasonValue)); } finally { setBusy(""); }
  }

  async function inspectCredential() {
    if (!detail?.deal) return;
    setBusy("inspect"); setError("");
    try { setCredential(await getAdminBuyRequestCredential(detail.request.id, detail.deal.id)); }
    catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  return <section className="workspace-page commerce-workspace admin-request-workspace">
    <div className="workspace-page__head"><p>ADMIN / SERVICE REQUESTS</p><h1>撮合交易管理</h1><span>核验双方方案和加密托管的 SSH 凭据；资金交易、充值与提现开关保持关闭。</span></div>
    <form className="refund-toolbar" onSubmit={submit}>
      <select aria-label="需求类型" value={requestType} onChange={(event) => setRequestType(event.target.value as "" | "online" | "offline")}><option value="">全部类型</option><option value="online">在线算力</option><option value="offline">线下设备</option></select>
      <select aria-label="需求状态" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="">全部状态</option>
        {statusFilterGroups.map((group) => <optgroup key={group.label} label={group.label}>
          {group.values.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
        </optgroup>)}
      </select>
      <input aria-label="搜索需求" placeholder="GPU、买家、联系人或手机号" value={keyword} onChange={(event) => setKeyword(event.target.value)}/>
      <button disabled={loading}><ArrowClockwise size={15}/>{loading ? "加载中" : "查询"}</button>
    </form>
    {error && <div className="commerce-error">{error}</div>}{message && <div className="commerce-success">{message}</div>}
    <div className="admin-request-layout">
      <div className="admin-settlement-list admin-request-list">
        {rows.length ? rows.map((row) => {
          const productName = metadata(row, "product_name"); const source = metadata(row, "source");
          return <button type="button" className={selectedId === row.id ? "active" : ""} key={row.id} onClick={() => void loadDetail(row.id)}>
            <span><small>需求 #{row.id} · {row.request_type === "online" ? "在线算力" : "线下设备"}{source ? <> · <span data-i18n-skip>{source}</span></> : ""}</small><strong data-i18n-skip>{productName || row.gpu_model} × {row.quantity}</strong><em>{row.buyer_name ? <span data-i18n-skip>{row.buyer_name}</span> : `用户 #${row.user_id}`} · {formatDate(row.created_at)}</em></span>
            <b>{statusLabel(row.deal?.status || row.status)}</b>
          </button>;
        }) : !loading && <div className="commerce-empty"><ClipboardText size={25}/><strong>没有符合条件的需求</strong><span>用户提交成功后会在这里显示。</span></div>}
      </div>
      <main className="admin-request-detail">{detail ? <>
        <header><div><small>REQUEST #{detail.request.id}</small><h2 data-i18n-skip>{metadata(detail.request, "product_name") || detail.request.gpu_model} × {detail.request.quantity}</h2><span>{formatDate(detail.request.created_at)}</span></div><b>{statusLabel(detail.deal?.status || detail.request.status)}</b></header>
        <div className="mobile-request-facts"><span><small>需求人</small><strong><User size={14}/>{detail.request.contact ? <span data-i18n-skip>{detail.request.contact}</span> : "未填写"}</strong></span><span><small>联系电话</small><strong data-i18n-skip={Boolean(detail.request.phone) || undefined}>{detail.request.phone || "未填写"}</strong></span><span><small>分发对象</small><strong><Storefront size={14}/><span data-i18n-skip>{targetLabel(detail.request, (id) => t("admin.common.supplierFallback", "商家 #{id}", { id }), t("admin.buyRequest.publicMarket", "公开需求市场"))}</span></strong></span><span><small>截止时间</small><strong>{formatDate(detail.request.expires_at)}</strong></span></div>
        {detailRequirementNote && <div className="workspace-service-note"><strong>补充需求：</strong><span data-i18n-skip>{detailRequirementNote}</span></div>}
        <section className="admin-request-quotes"><h3>报价与协商记录</h3>{detail.quotes.length ? detail.quotes.map((quote) => <article key={quote.id}><div><strong data-i18n-skip={Boolean(quote.supplier_name) || undefined}>{quote.supplier_name || t("admin.common.supplierFallback", "商家 #{id}", { id: quote.supplier_id })}</strong><small>报价 #{quote.id} · {quote.revision_count || quote.revisions?.length || 1} 轮</small></div><b>¥{quote.latest_revision?.total_price ?? quote.total_price}</b><em>{statusLabel(quote.status)}</em></article>) : <div className="mobile-inline-empty">暂无报价</div>}</section>
        {detail.deal ? <section className="admin-deal-review"><header><div><small>DEAL #{detail.deal.id}</small><h3>撮合审核与凭据托管</h3></div><b>{statusLabel(detail.deal.status)}</b></header>
          {detail.events?.length ? <ol className="matchmaking-timeline">{detail.events.map((event) => <li key={event.id}><span><CheckCircle size={16}/></span><div><strong>{timelineEventLabel(event)}</strong><small data-i18n-skip={Boolean(event.message) || undefined}>{event.message || formatDate(event.created_at)}</small></div></li>)}</ol> : null}
          {["supplier_confirmed", "platform_review"].includes(detail.deal.status) && <div className="admin-review-actions"><button className="danger" disabled={Boolean(busy)} onClick={() => void dealAction("reject")}><WarningCircle size={15}/>退回方案</button><button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void dealAction("approve")}><ShieldCheck size={15}/>审核通过</button></div>}
          {["credential_submitted", "credential_released", "delivery_disputed", "completed"].includes(detail.deal.status) && <div className="admin-credential-review"><div><Key size={19}/><span><strong>SSH 凭据审核</strong><small>指纹 {detail.deal.credential?.fingerprint || detail.deal.credential_fingerprint || "待读取"} · 版本 {detail.deal.credential?.credential_version || detail.deal.credential_version || "-"}</small></span><button disabled={Boolean(busy)} onClick={() => void inspectCredential()}>{busy === "inspect" ? "读取中…" : credential ? "重新读取" : "安全查看"}</button></div>{credential && <section><dl><div><dt>连接地址</dt><dd data-i18n-skip>{credential.username}@{credential.host}:{credential.port}</dd></div><div><dt>认证方式</dt><dd>{credential.auth_type === "private_key" ? "SSH 私钥" : "密码"}</dd></div></dl><pre data-i18n-skip>{credential.secret}</pre>{credential.note && <p data-i18n-skip>{credential.note}</p>}{detail.deal.status === "credential_submitted" && <div className="admin-review-actions"><button className="danger" disabled={Boolean(busy)} onClick={() => void dealAction("reject-credential")}>退回重交</button><button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void dealAction("release")}><LockKey size={15}/>核验并放行</button></div>}</section>}</div>}
        </section> : <div className="workspace-service-note"><LockKey size={16}/>买家尚未选定方案，暂未生成撮合记录。</div>}
      </> : <div className="commerce-empty"><ClipboardText size={25}/><strong>选择一条需求</strong></div>}</main>
    </div>
    <div className="workspace-service-note"><LockKey size={16}/>共 {total} 条需求。购买人与商家的私人联系方式只向管理员开放，SSH 明文仅在凭据审核时按需读取。</div>
  </section>;
}
