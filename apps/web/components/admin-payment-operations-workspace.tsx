"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowClockwise, Check, ClipboardText, Coins, MagnifyingGlass, Receipt, Warning, X } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import {
  createAdminPaymentRefund,
  getAdminPaymentRefund,
  getAdminPaymentRefundRequest,
  getAdminRechargeOrder,
  listAdminPaymentRefunds,
  listAdminPaymentRefundRequests,
  listAdminRechargeOrders,
  resolveAdminPaymentRefund,
  reviewAdminPaymentRefundRequest,
  reviewAdminRechargeOrder,
  type AdminPaymentEvent,
  type AdminPaymentRefund,
  type AdminPaymentRefundRequest,
  type AdminRechargeDetail,
  type AdminRechargeItem,
} from "@/lib/admin-audit-api";
import {
  adminRechargeActions,
  canReviewPaymentRefundRequest,
  canResolveUnknownPaymentRefund,
  paymentRefundRequestStatusLabel,
  paymentRefundStatusLabel,
  paymentStatusLabel,
  paymentStatusTone,
} from "@/lib/admin-payment-operations";
import { ADMIN_QUEUE_PAGE_SIZE, adminQueuePageCount } from "@/lib/admin-queue-pagination";
import { isUncertainApiFailure } from "@/lib/api";
import {
  clearClientRequestIntent,
  clientRequestFingerprint,
  ensureClientRequestIntent,
  readClientRequestIntent,
  saveClientRequestIntent,
  type ClientRequestIntent,
} from "@/lib/client-request-intent";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import type { AuditPlatform } from "@/lib/mobile-finance-api";
import { formatFinancialAmount } from "@/lib/financial-format";
import { useI18n } from "@/components/locale-root";

const PAYMENT_OPERATION_INTENT_KEY = "kai-admin-payment-operation-intent:v1";

type WorkspaceTab = "orders" | "requests" | "refunds";

function money(value: number) {
  return formatFinancialAmount(value);
}

function cardHours(value: number) {
  return formatFinancialAmount(value);
}

function browserSessionStorage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function paymentOperationIntentKey(paymentOrderId: number) {
  return `${PAYMENT_OPERATION_INTENT_KEY}:${paymentOrderId}`;
}

function refundHoldLabel(status: string) {
  return ({
    not_required: "无需冻结",
    held: "对应卡时已冻结",
    settled: "对应卡时已扣回",
    released: "冻结卡时已释放",
  } as Record<string, string>)[status] || status;
}

function paymentReviewProviderLabel(provider: string) {
  if (provider === "qixiangpay") return "七相商户后台";
  if (provider === "mapay") return "历史 MaPay 商户后台";
  return "对应支付渠道后台";
}

function eventTransition(event: AdminPaymentEvent) {
  if (!event.from_status && !event.to_status) return "未改变充值单状态";
  return `${event.from_status ? paymentStatusLabel(event.from_status) : "未记录"} → ${event.to_status ? paymentStatusLabel(event.to_status) : "未记录"}`;
}

export function AdminPaymentOperationsWorkspace() {
  const { t } = useI18n();
  const [tab, setTab] = useState<WorkspaceTab>("orders");
  const [orders, setOrders] = useState<AdminRechargeItem[]>([]);
  const [orderStatus, setOrderStatus] = useState("review");
  const [orderPlatform, setOrderPlatform] = useState<AuditPlatform | "">("");
  const [orderSearch, setOrderSearch] = useState("");
  const [orderNo, setOrderNo] = useState("");
  const [orderPage, setOrderPage] = useState(1);
  const [orderTotal, setOrderTotal] = useState(0);
  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [orderDetail, setOrderDetail] = useState<AdminRechargeDetail | null>(null);
  const [orderNote, setOrderNote] = useState("");
  const [refunds, setRefunds] = useState<AdminPaymentRefund[]>([]);
  const [refundStatus, setRefundStatus] = useState("unknown");
  const [refundPage, setRefundPage] = useState(1);
  const [refundTotal, setRefundTotal] = useState(0);
  const [selectedRefundId, setSelectedRefundId] = useState<number | null>(null);
  const [refundDetail, setRefundDetail] = useState<AdminPaymentRefund | null>(null);
  const [refundNote, setRefundNote] = useState("");
  const [refundRequests, setRefundRequests] = useState<AdminPaymentRefundRequest[]>([]);
  const [refundRequestStatus, setRefundRequestStatus] = useState("pending_review");
  const [refundRequestPlatform, setRefundRequestPlatform] = useState<AuditPlatform | "">("");
  const [refundRequestNoSearch, setRefundRequestNoSearch] = useState("");
  const [refundRequestOrderSearch, setRefundRequestOrderSearch] = useState("");
  const [refundRequestNo, setRefundRequestNo] = useState("");
  const [refundRequestOrderNo, setRefundRequestOrderNo] = useState("");
  const [refundRequestPage, setRefundRequestPage] = useState(1);
  const [refundRequestTotal, setRefundRequestTotal] = useState(0);
  const [selectedRefundRequestId, setSelectedRefundRequestId] = useState<number | null>(null);
  const [refundRequestDetail, setRefundRequestDetail] = useState<AdminPaymentRefundRequest | null>(null);
  const [refundRequestNote, setRefundRequestNote] = useState("");
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [loadingRefunds, setLoadingRefunds] = useState(false);
  const [loadingRefundRequests, setLoadingRefundRequests] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const orderRequestSequence = useRef(0);
  const refundRequestSequence = useRef(0);
  const refundApplicationRequestSequence = useRef(0);
  const detailRequestSequence = useRef(0);
  const mutationInFlight = useRef(false);
  const paymentIntent = useRef<ClientRequestIntent | null>(null);

  const loadOrders = useCallback(async () => {
    const sequence = ++orderRequestSequence.current;
    setLoadingOrders(true);
    setError("");
    try {
      const result = await listAdminRechargeOrders({
        status: orderStatus || undefined,
        platform: orderPlatform || undefined,
        orderNo: orderNo || undefined,
        page: orderPage,
        pageSize: ADMIN_QUEUE_PAGE_SIZE,
      });
      if (sequence !== orderRequestSequence.current) return;
      const pageCount = adminQueuePageCount(result.total);
      setOrderTotal(result.total);
      if (orderPage > pageCount) {
        setOrders([]);
        setOrderPage(pageCount);
        return;
      }
      setOrders(result.items);
      setSelectedOrderId((current) => result.items.some((row) => row.id === current) ? current : result.items[0]?.id ?? null);
    } catch (reason) {
      if (sequence === orderRequestSequence.current) setError(errorMessage(reason));
    } finally {
      if (sequence === orderRequestSequence.current) setLoadingOrders(false);
    }
  }, [orderNo, orderPage, orderPlatform, orderStatus]);

  const loadRefunds = useCallback(async () => {
    const sequence = ++refundRequestSequence.current;
    setLoadingRefunds(true);
    setError("");
    try {
      const result = await listAdminPaymentRefunds({ status: refundStatus || undefined, page: refundPage, pageSize: ADMIN_QUEUE_PAGE_SIZE });
      if (sequence !== refundRequestSequence.current) return;
      const pageCount = adminQueuePageCount(result.total);
      setRefundTotal(result.total);
      if (refundPage > pageCount) {
        setRefunds([]);
        setRefundPage(pageCount);
        return;
      }
      setRefunds(result.items);
      setSelectedRefundId((current) => result.items.some((row) => row.id === current) ? current : result.items[0]?.id ?? null);
    } catch (reason) {
      if (sequence === refundRequestSequence.current) setError(errorMessage(reason));
    } finally {
      if (sequence === refundRequestSequence.current) setLoadingRefunds(false);
    }
  }, [refundPage, refundStatus]);

  const loadRefundRequests = useCallback(async () => {
    const sequence = ++refundApplicationRequestSequence.current;
    setLoadingRefundRequests(true);
    setError("");
    try {
      const result = await listAdminPaymentRefundRequests({
        status: refundRequestStatus || undefined,
        platform: refundRequestPlatform || undefined,
        requestNo: refundRequestNo || undefined,
        orderNo: refundRequestOrderNo || undefined,
        page: refundRequestPage,
        pageSize: ADMIN_QUEUE_PAGE_SIZE,
      });
      if (sequence !== refundApplicationRequestSequence.current) return;
      const pageCount = adminQueuePageCount(result.total);
      setRefundRequestTotal(result.total);
      if (refundRequestPage > pageCount) {
        setRefundRequests([]);
        setRefundRequestPage(pageCount);
        return;
      }
      setRefundRequests(result.items);
      setSelectedRefundRequestId((current) => result.items.some((row) => row.id === current) ? current : result.items[0]?.id ?? null);
    } catch (reason) {
      if (sequence === refundApplicationRequestSequence.current) setError(errorMessage(reason));
    } finally {
      if (sequence === refundApplicationRequestSequence.current) setLoadingRefundRequests(false);
    }
  }, [refundRequestNo, refundRequestOrderNo, refundRequestPage, refundRequestPlatform, refundRequestStatus]);

  const loadOrderDetail = useCallback(async (id: number) => {
    const sequence = ++detailRequestSequence.current;
    setLoadingDetail(true);
    setError("");
    try {
      const result = await getAdminRechargeOrder(id);
      if (sequence === detailRequestSequence.current) setOrderDetail(result);
    } catch (reason) {
      if (sequence === detailRequestSequence.current) {
        setOrderDetail(null);
        setError(errorMessage(reason));
      }
    } finally {
      if (sequence === detailRequestSequence.current) setLoadingDetail(false);
    }
  }, []);

  const loadRefundDetail = useCallback(async (id: number) => {
    const sequence = ++detailRequestSequence.current;
    setLoadingDetail(true);
    setError("");
    try {
      const result = await getAdminPaymentRefund(id);
      if (sequence === detailRequestSequence.current) setRefundDetail(result);
    } catch (reason) {
      if (sequence === detailRequestSequence.current) {
        setRefundDetail(null);
        setError(errorMessage(reason));
      }
    } finally {
      if (sequence === detailRequestSequence.current) setLoadingDetail(false);
    }
  }, []);

  const loadRefundRequestDetail = useCallback(async (id: number) => {
    const sequence = ++detailRequestSequence.current;
    setLoadingDetail(true);
    setError("");
    try {
      const result = await getAdminPaymentRefundRequest(id);
      if (sequence === detailRequestSequence.current) setRefundRequestDetail(result);
    } catch (reason) {
      if (sequence === detailRequestSequence.current) {
        setRefundRequestDetail(null);
        setError(errorMessage(reason));
      }
    } finally {
      if (sequence === detailRequestSequence.current) setLoadingDetail(false);
    }
  }, []);

  useEffect(() => { if (tab === "orders") void loadOrders(); }, [loadOrders, tab]);
  useEffect(() => { if (tab === "requests") void loadRefundRequests(); }, [loadRefundRequests, tab]);
  useEffect(() => { if (tab === "refunds") void loadRefunds(); }, [loadRefunds, tab]);
  useEffect(() => {
    if (tab !== "orders" || selectedOrderId == null) { setOrderDetail(null); return; }
    void loadOrderDetail(selectedOrderId);
  }, [loadOrderDetail, selectedOrderId, tab]);
  useEffect(() => {
    if (tab !== "requests" || selectedRefundRequestId == null) { setRefundRequestDetail(null); return; }
    void loadRefundRequestDetail(selectedRefundRequestId);
  }, [loadRefundRequestDetail, selectedRefundRequestId, tab]);
  useEffect(() => {
    if (tab !== "refunds" || selectedRefundId == null) { setRefundDetail(null); return; }
    void loadRefundDetail(selectedRefundId);
  }, [loadRefundDetail, selectedRefundId, tab]);

  function changeTab(next: WorkspaceTab) {
    if (next === tab) return;
    detailRequestSequence.current += 1;
    setTab(next);
    setError("");
    setSuccess("");
    setOrderNote("");
    setRefundNote("");
    setRefundRequestNote("");
  }

  function applyOrderSearch(event: FormEvent) {
    event.preventDefault();
    setOrderPage(1);
    setOrderNo(orderSearch.trim().toUpperCase());
  }

  function applyRefundRequestSearch(event: FormEvent) {
    event.preventDefault();
    setRefundRequestPage(1);
    setRefundRequestNo(refundRequestNoSearch.trim().toUpperCase());
    setRefundRequestOrderNo(refundRequestOrderSearch.trim().toUpperCase());
  }

  function beginMutation(key: string) {
    if (mutationInFlight.current) return false;
    mutationInFlight.current = true;
    setBusy(key);
    setError("");
    setSuccess("");
    return true;
  }

  function finishMutation() {
    mutationInFlight.current = false;
    setBusy("");
  }

  async function submitOrderAction(action: "credit" | "refund") {
    if (!orderDetail) return;
    const order = orderDetail.order;
    const note = orderNote.trim();
    if (note.length < 3) { setError("执行资金操作前，请填写至少 3 个字的核验依据或处理原因。"); return; }
    const isReview = ["review", "late_paid_review"].includes(order.status);
    const wording = action === "credit"
      ? t("admin.payment.confirmCredit", "确认{provider}已显示支付成功，并为用户入账 {cardHours} 卡时？", {
        provider: t(`admin.payment.provider.${order.provider}`, paymentReviewProviderLabel(order.provider)),
        cardHours: cardHours(order.card_hours),
      })
      : t("admin.payment.confirmRefund", "确认对充值单 {orderNo} 发起人民币 ¥{amount} 全额原支付渠道退款？这不是钱包订单退卡时。", {
        orderNo: order.order_no,
        amount: money(order.amount_cny),
      });
    if (!window.confirm(`${wording}\n\n${t("admin.payment.confirmEvidence", "确认前请再次核对商户后台交易号、金额和支付状态。")}`)) return;
    if (!beginMutation(`order-${order.id}-${action}`)) return;

    const storage = browserSessionStorage();
    let intent: ClientRequestIntent | null = null;
    if (action === "refund") {
      const fingerprint = clientRequestFingerprint(["admin-payment", order.id, action]);
      const storageKey = paymentOperationIntentKey(order.id);
      const persisted = storage ? readClientRequestIntent(storage, storageKey) : null;
      const existingRefundId = orderDetail.refund?.status === "failed"
        ? orderDetail.refund.client_request_id
        : null;
      const currentIntent = existingRefundId
        ? { fingerprint, requestId: existingRefundId }
        : paymentIntent.current?.fingerprint === fingerprint ? paymentIntent.current : persisted;
      intent = ensureClientRequestIntent(currentIntent, fingerprint, "admin-refund");
      paymentIntent.current = intent;
      if (storage) saveClientRequestIntent(storage, storageKey, intent);
    }

    try {
      let refundResult: AdminPaymentRefund | null = null;
      if (isReview) {
        if (action === "credit") {
          await reviewAdminRechargeOrder(order.id, { action, note });
        } else {
          const result = await reviewAdminRechargeOrder(order.id, { action, note, client_request_id: intent!.requestId });
          if ("refund_no" in result) refundResult = result;
        }
      } else {
        refundResult = await createAdminPaymentRefund(order.id, { reason: note, client_request_id: intent!.requestId });
      }
      if (intent) {
        paymentIntent.current = null;
        if (storage) clearClientRequestIntent(storage, paymentOperationIntentKey(order.id));
      }
      setOrderNote("");
      setSuccess(action === "credit"
        ? t("admin.payment.creditSuccess", "充值单 {orderNo} 已按服务端核验结果完成入账。", { orderNo: order.order_no })
        : refundResult
          ? t("admin.payment.refundAccepted", "人民币原路退款 {refundNo} 当前状态：{status}；请以退款记录和商户后台为准。", {
            refundNo: refundResult.refund_no,
            status: t(`admin.payment.refundStatus.${refundResult.status}`, paymentRefundStatusLabel(refundResult.status)),
          })
          : t("admin.payment.refundQueued", "充值单 {orderNo} 的人民币原路退款请求已受理；请刷新退款记录核对最终结果。", { orderNo: order.order_no }));
      await Promise.all([loadOrders(), loadOrderDetail(order.id)]);
    } catch (reason) {
      setError(isUncertainApiFailure(reason)
        ? t("admin.payment.uncertain", "本次{action}结果暂不确定，请先刷新详情核对；以相同备注重试时会复用同一请求标识。", {
          action: t(`admin.payment.action.${action}`, action === "credit" ? "入账" : "原路退款"),
        })
        : errorMessage(reason));
    } finally {
      finishMutation();
    }
  }

  function openRefundRequest(request: AdminPaymentRefundRequest) {
    detailRequestSequence.current += 1;
    setRefundRequestStatus("");
    setRefundRequestNoSearch(request.request_no);
    setRefundRequestNo(request.request_no);
    setRefundRequestOrderSearch("");
    setRefundRequestOrderNo("");
    setRefundRequestPage(1);
    setSelectedRefundRequestId(request.id);
    setRefundRequestNote("");
    setError("");
    setSuccess("");
    setTab("requests");
  }

  async function submitRefundRequestReview(action: "approve" | "reject") {
    if (!refundRequestDetail || !canReviewPaymentRefundRequest(refundRequestDetail.status)) return;
    const note = refundRequestNote.trim();
    if (note.length < 3) { setError("请填写至少 3 个字的审核依据或驳回原因。"); return; }
    const wording = action === "approve"
      ? t("admin.payment.approveRequestConfirm", "确认批准退款申请 {requestNo}？系统将立即尝试发起人民币 ¥{amount} 全额原支付渠道退款，并冻结或冲正对应卡时。", {
        requestNo: refundRequestDetail.request_no,
        amount: money(refundRequestDetail.amount_cny),
      })
      : t("admin.payment.rejectRequestConfirm", "确认驳回退款申请 {requestNo}？本次操作不会发起人民币退款，也不会扣减用户卡时。", { requestNo: refundRequestDetail.request_no });
    if (!window.confirm(`${wording}\n\n${t("admin.payment.reviewAuditConfirm", "审核结论会写入支付审计记录，请确认申请原因、充值单和支付状态已核对。")}`)) return;
    if (!beginMutation(`refund-request-${refundRequestDetail.id}-${action}`)) return;
    try {
      const result = await reviewAdminPaymentRefundRequest(refundRequestDetail.id, { action, note });
      setRefundRequestDetail(result);
      setRefundRequestNote("");
      setSuccess(action === "reject"
        ? t("admin.payment.requestRejected", "退款申请 {requestNo} 已驳回，未发起人民币退款。", { requestNo: result.request_no })
        : t("admin.payment.requestApproved", "退款申请 {requestNo} 已批准，当前状态：{status}。请继续以原路退款记录和支付渠道结果为准。", {
          requestNo: result.request_no,
          status: t(`admin.payment.requestStatus.${result.status}`, paymentRefundRequestStatusLabel(result.status)),
        }));
      await loadRefundRequests();
    } catch (reason) {
      setError(isUncertainApiFailure(reason)
        ? "退款申请审核结果暂不确定，请先刷新申请详情和原路退款记录；系统不会重复创建退款。"
        : errorMessage(reason));
    } finally {
      finishMutation();
    }
  }

  async function submitRefundResolution(outcome: "succeeded" | "failed") {
    if (!refundDetail || !canResolveUnknownPaymentRefund(refundDetail.status)) return;
    const note = refundNote.trim();
    if (note.length < 3) { setError("请填写至少 3 个字的商户后台核验依据。"); return; }
    const wording = outcome === "succeeded"
      ? "商户后台明确显示退款成功；确认后将完成卡时冲正，并把充值单标记为已原路退款。"
      : "商户后台明确显示退款失败；确认后将释放被冻结的卡时，并恢复充值单原状态。";
    if (!window.confirm(t("admin.payment.resolveConfirm", "{decision}\n\n退款号：{refundNo}\n该结论必须来自商户后台证据，不能根据用户截图或页面回跳判断。", {
      decision: t(`admin.payment.resolveDecision.${outcome}`, wording),
      refundNo: refundDetail.refund_no,
    }))) return;
    if (!beginMutation(`refund-${refundDetail.id}-${outcome}`)) return;
    try {
      const result = await resolveAdminPaymentRefund(refundDetail.id, { outcome, note });
      setRefundDetail(result);
      setRefundNote("");
      setSuccess(t("admin.payment.resolveSuccess", "人民币原路退款 {refundNo} 已确认{outcome}。", {
        refundNo: result.refund_no,
        outcome: t(`admin.payment.outcome.${outcome}`, outcome === "succeeded" ? "成功" : "失败"),
      }));
      await loadRefunds();
    } catch (reason) {
      setError(isUncertainApiFailure(reason)
        ? "人工确认结果暂不确定，请先刷新退款详情核对；系统不会自动重复提交。"
        : errorMessage(reason));
    } finally {
      finishMutation();
    }
  }

  const orderActions = orderDetail
    ? adminRechargeActions(
      orderDetail.order.status,
      orderDetail.refund?.status,
      orderDetail.order.provider,
      orderDetail.refund_request?.status,
    )
    : { canCredit: false, canRefund: false };

  return <section className="workspace-page commerce-workspace admin-payment-operations">
    <div className="workspace-page__head">
      <p>FINANCE / PAYMENT OPERATIONS</p>
      <h1>充值与人民币原路退款</h1>
      <span>复核支付渠道充值、追踪支付事件，并在商户后台证据充分时执行入账；人民币原支付渠道退款仅支持七相充值。</span>
    </div>
    <div className="payment-operation-boundary"><Warning size={19}/><div><strong>两类退款必须分开处理</strong><span>{t("admin.payment.boundaryPrefix", "本页处理七相充值的人民币原支付渠道退款，并可能冻结或冲正对应卡时；")} <Link href="/admin/disputes">{t("admin.payment.walletDisputeLink", "钱包订单争议退款")}</Link> {t("admin.payment.boundarySuffix", "只退回买家钱包卡时，不会自动退回人民币。")}</span></div></div>
    <nav className="payment-operation-tabs" aria-label="支付运营视图">
      <button type="button" className={tab === "orders" ? "active" : ""} aria-current={tab === "orders" ? "page" : undefined} onClick={() => changeTab("orders")}><Coins size={17}/>充值订单</button>
      <button type="button" className={tab === "requests" ? "active" : ""} aria-current={tab === "requests" ? "page" : undefined} onClick={() => changeTab("requests")}><ClipboardText size={17}/>用户退款申请</button>
      <button type="button" className={tab === "refunds" ? "active" : ""} aria-current={tab === "refunds" ? "page" : undefined} onClick={() => changeTab("refunds")}><Receipt size={17}/>人民币原路退款</button>
    </nav>
    {error && <div className="commerce-error" role="alert">{error}</div>}
    {success && <div className="commerce-success" role="status">{success}</div>}

    {tab === "orders" ? <>
      <form className="payment-operation-toolbar" onSubmit={applyOrderSearch}>
        <label><MagnifyingGlass size={15}/><input aria-label="搜索充值订单号" placeholder="充值订单号" value={orderSearch} onChange={(event) => setOrderSearch(event.target.value)}/></label>
        <select aria-label="充值订单状态" value={orderStatus} onChange={(event) => { setOrderStatus(event.target.value); setOrderPage(1); }}>
          <option value="review">待支付复核</option><option value="late_paid_review">超时到账复核</option><option value="paid">已支付并入账</option><option value="refund_unknown">原路退款待核验</option><option value="refund_pending">原路退款提交中</option><option value="refunded">已原路退款</option><option value="pending">等待支付</option><option value="failed">支付失败</option><option value="expired">已过期</option><option value="canceled">已取消</option><option value="">全部状态</option>
        </select>
        <AdminPlatformFilter value={orderPlatform} onChange={(value) => { setOrderPlatform(value); setOrderPage(1); }}/>
        <button type="submit">筛选</button>
        <button type="button" disabled={loadingOrders} onClick={() => void Promise.all([loadOrders(), selectedOrderId ? loadOrderDetail(selectedOrderId) : Promise.resolve()])}><ArrowClockwise size={15}/>{loadingOrders ? "读取中" : "刷新"}</button>
      </form>
      <div className="review-console admin-payment-console">
        <aside>
          {orders.length ? <div className="review-queue">{orders.map((row) => <button type="button" className={selectedOrderId === row.id ? "active" : ""} key={row.id} onClick={() => { setSelectedOrderId(row.id); setOrderNote(""); setError(""); setSuccess(""); }}><span><small>{row.order_no} · {platformLabel(row.created_platform)}</small><strong data-i18n-skip={Boolean(row.user.username) || undefined}>{row.user.username || `用户 #${row.user.id}`}</strong><em>¥{money(row.amount_cny)} · {row.provider_trade_no || "暂无渠道交易号"}</em></span><b className={`status-chip status-chip--${paymentStatusTone(row.status)}`}>{paymentStatusLabel(row.status)}</b></button>)}</div> : <div className="commerce-empty"><Coins size={24}/><strong>{loadingOrders ? "正在读取充值订单…" : "当前筛选条件下没有充值订单"}</strong></div>}
          <AdminQueuePagination page={orderPage} total={orderTotal} loading={loadingOrders} onPageChange={setOrderPage}/>
        </aside>
        <article className="review-dossier payment-operation-dossier">
          {orderDetail ? <>
            <header><div><p>{orderDetail.order.order_no} / PAYMENT #{orderDetail.order.id}</p><h2 data-i18n-skip={Boolean(orderDetail.order.user.username) || undefined}>{orderDetail.order.user.username || `用户 #${orderDetail.order.user.id}`}</h2></div><span className={`status-chip status-chip--${paymentStatusTone(orderDetail.order.status)}`}>{paymentStatusLabel(orderDetail.order.status)}</span></header>
            <dl>
              <div><dt>人民币 / 入账卡时</dt><dd>¥ {money(orderDetail.order.amount_cny)} / {cardHours(orderDetail.order.card_hours)} 卡时</dd></div>
              <div><dt>支付渠道</dt><dd>{orderDetail.order.provider} · {orderDetail.order.channel || "未记录"}<small>{orderDetail.order.provider_trade_no || "暂无渠道交易号"}</small></dd></div>
              <div><dt>渠道状态</dt><dd>{orderDetail.order.provider_status || "尚未记录"}</dd></div>
              <div><dt>失败原因</dt><dd data-i18n-skip={Boolean(orderDetail.order.failure_reason) || undefined}>{orderDetail.order.failure_reason || "无"}</dd></div>
              <div><dt>支付 / 入账时间</dt><dd>{formatDate(orderDetail.order.paid_at)}<small>入账：{formatDate(orderDetail.order.credited_at)}</small></dd></div>
              <div><dt>最近查单</dt><dd>{formatDate(orderDetail.order.last_reconciled_at)}<small>累计 {orderDetail.order.reconcile_attempts || 0} 次</small></dd></div>
              <div><dt>创建 / 最后修改来源</dt><dd>{platformLabel(orderDetail.order.created_platform)} / {platformLabel(orderDetail.order.last_modified_platform)}</dd></div>
              <div><dt>客户端请求标识</dt><dd className="payment-operation-mono">{orderDetail.order.client_request_id || "历史订单未记录"}</dd></div>
            </dl>
            {orderDetail.refund_request && <section className="payment-refund-summary payment-refund-request-summary"><div><h3>关联用户退款申请</h3><p><strong>{orderDetail.refund_request.request_no}</strong> · {paymentRefundRequestStatusLabel(orderDetail.refund_request.status)}<br/><span data-i18n-skip>{orderDetail.refund_request.reason}</span></p></div><button type="button" onClick={() => openRefundRequest(orderDetail.refund_request!)}>查看申请</button></section>}
            {orderDetail.refund && <section className="payment-refund-summary"><h3>关联人民币原路退款</h3><p><strong>{orderDetail.refund.refund_no}</strong> · {paymentRefundStatusLabel(orderDetail.refund.status)} · {refundHoldLabel(orderDetail.refund.wallet_hold_status)}<br/><span data-i18n-skip>{orderDetail.refund.reason}</span></p></section>}
            <section><h3>支付事件（服务端审计记录）</h3>{orderDetail.events.length ? <ol className="payment-event-list">{orderDetail.events.map((event) => <li key={event.id}><header><strong>{event.event_type}</strong><time>{formatDate(event.created_at)}</time></header><p>{eventTransition(event)} · {event.source} / {event.actor_type}{event.actor_user_id ? ` #${event.actor_user_id}` : ""}</p>{event.detail && <dl>{Object.entries(event.detail).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? "未记录")}</dd></div>)}</dl>}</li>)}</ol> : <p>尚无支付事件记录。</p>}</section>
            {(orderActions.canCredit || orderActions.canRefund) && <footer className="payment-operation-actions">
              <label><span>核验依据 / 处理原因（至少 3 字）</span><textarea maxLength={500} rows={4} value={orderNote} onChange={(event) => setOrderNote(event.target.value)} placeholder="记录商户后台交易号、支付状态、金额及核验结论；不要填写密钥或签名"/></label>
              <div>
                {orderActions.canRefund && <button type="button" className="commerce-danger" disabled={Boolean(busy) || orderNote.trim().length < 3} onClick={() => void submitOrderAction("refund")}><X size={15}/>{orderDetail.refund?.status === "failed" ? "重试全额人民币原路退款" : "发起全额人民币原路退款"}</button>}
                {orderActions.canCredit && <button type="button" className="commerce-primary" disabled={Boolean(busy) || orderNote.trim().length < 3} onClick={() => void submitOrderAction("credit")}><Check size={15}/>确认支付成功并入账</button>}
              </div>
              <small>只有服务端向支付渠道查单确认成功后才能入账；页面回跳、用户截图和客户端参数都不是成功凭据。</small>
            </footer>}
          </> : <div className="commerce-empty"><Coins size={25}/><strong>{loadingDetail ? "正在读取充值详情…" : "选择一笔充值订单查看渠道状态、事件和退款记录"}</strong></div>}
        </article>
      </div>
    </> : tab === "requests" ? <>
      <form className="payment-operation-toolbar payment-operation-toolbar--requests" onSubmit={applyRefundRequestSearch}>
        <label><MagnifyingGlass size={15}/><input aria-label="搜索退款申请号" placeholder="退款申请号" value={refundRequestNoSearch} onChange={(event) => setRefundRequestNoSearch(event.target.value)}/></label>
        <label><MagnifyingGlass size={15}/><input aria-label="搜索关联充值单号" placeholder="关联充值单号" value={refundRequestOrderSearch} onChange={(event) => setRefundRequestOrderSearch(event.target.value)}/></label>
        <select aria-label="退款申请状态" value={refundRequestStatus} onChange={(event) => { setRefundRequestStatus(event.target.value); setRefundRequestPage(1); }}><option value="pending_review">待审核</option><option value="processing">退款处理中</option><option value="succeeded">退款成功</option><option value="failed">退款失败</option><option value="rejected">已驳回</option><option value="canceled">已取消</option><option value="approved">已批准</option><option value="">全部状态</option></select>
        <AdminPlatformFilter value={refundRequestPlatform} onChange={(value) => { setRefundRequestPlatform(value); setRefundRequestPage(1); }}/>
        <button type="submit">筛选</button>
        <button type="button" disabled={loadingRefundRequests} onClick={() => void Promise.all([loadRefundRequests(), selectedRefundRequestId ? loadRefundRequestDetail(selectedRefundRequestId) : Promise.resolve()])}><ArrowClockwise size={15}/>{loadingRefundRequests ? "读取中" : "刷新"}</button>
      </form>
      <div className="review-console admin-payment-console">
        <aside>
          {refundRequests.length ? <div className="review-queue">{refundRequests.map((row) => <button type="button" className={selectedRefundRequestId === row.id ? "active" : ""} key={row.id} onClick={() => { setSelectedRefundRequestId(row.id); setRefundRequestNote(""); setError(""); setSuccess(""); }}><span><small>{row.request_no} · {platformLabel(row.created_platform)}</small><strong data-i18n-skip={Boolean(row.user.username) || undefined}>{row.user.username || `用户 #${row.user.id}`}</strong><em>{row.order_no || `PAYMENT #${row.payment_order_id}`} · ¥{money(row.amount_cny)}</em></span><b className={`status-chip status-chip--${paymentStatusTone(row.status)}`}>{paymentRefundRequestStatusLabel(row.status)}</b></button>)}</div> : <div className="commerce-empty"><ClipboardText size={24}/><strong>{loadingRefundRequests ? "正在读取退款申请…" : "当前筛选条件下没有退款申请"}</strong></div>}
          <AdminQueuePagination page={refundRequestPage} total={refundRequestTotal} loading={loadingRefundRequests} onPageChange={setRefundRequestPage}/>
        </aside>
        <article className="review-dossier payment-operation-dossier">
          {refundRequestDetail ? <>
            <header><div><p>{refundRequestDetail.request_no} / REQUEST #{refundRequestDetail.id}</p><h2 data-i18n-skip={Boolean(refundRequestDetail.user.username) || undefined}>{refundRequestDetail.user.username || `用户 #${refundRequestDetail.user.id}`}</h2></div><span className={`status-chip status-chip--${paymentStatusTone(refundRequestDetail.status)}`}>{paymentRefundRequestStatusLabel(refundRequestDetail.status)}</span></header>
            <dl>
              <div><dt>关联充值单</dt><dd>{refundRequestDetail.order_no || `PAYMENT #${refundRequestDetail.payment_order_id}`}<small>{paymentStatusLabel(refundRequestDetail.payment_status || "未知状态")}</small></dd></div>
              <div><dt>人民币 / 对应卡时</dt><dd>¥ {money(refundRequestDetail.amount_cny)} / {cardHours(refundRequestDetail.card_hours)} 卡时</dd></div>
              <div><dt>申请用户</dt><dd><span data-i18n-skip={Boolean(refundRequestDetail.user.username) || undefined}>{refundRequestDetail.user.username || "未设置用户名"}</span><small>USER #{refundRequestDetail.user.id}</small></dd></div>
              <div><dt>申请来源 / 时间</dt><dd>{platformLabel(refundRequestDetail.created_platform)}<small>{formatDate(refundRequestDetail.created_at)}</small></dd></div>
              <div><dt>审核管理员</dt><dd>{refundRequestDetail.reviewed_by ? `ADMIN #${refundRequestDetail.reviewed_by}` : "尚未审核"}<small>{formatDate(refundRequestDetail.reviewed_at)}</small></dd></div>
              <div><dt>客户端请求标识</dt><dd className="payment-operation-mono">{refundRequestDetail.client_request_id}</dd></div>
            </dl>
            <section><h3>用户申请原因</h3><p data-i18n-skip>{refundRequestDetail.reason}</p></section>
            {refundRequestDetail.review_note && <section><h3>管理员审核说明</h3><p data-i18n-skip>{refundRequestDetail.review_note}</p></section>}
            {refundRequestDetail.payment_refund && <section className="payment-refund-summary payment-refund-request-summary"><div><h3>已关联人民币原路退款</h3><p><strong>{refundRequestDetail.payment_refund.refund_no}</strong> · {paymentRefundStatusLabel(refundRequestDetail.payment_refund.status)} · {refundHoldLabel(refundRequestDetail.payment_refund.wallet_hold_status)}<br/>{refundRequestDetail.payment_refund.provider_message || "支付渠道尚未返回补充说明"}</p></div><button type="button" onClick={() => { setRefundStatus(""); setSelectedRefundId(refundRequestDetail.payment_refund!.id); setRefundNote(""); setError(""); setSuccess(""); setTab("refunds"); }}>查看原路退款</button></section>}
            {canReviewPaymentRefundRequest(refundRequestDetail.status) && <footer className="payment-operation-actions">
              <div className="payment-provider-evidence"><Warning size={18}/><span>批准后系统会立即尝试原支付渠道全额退款，并冻结或冲正对应卡时。驳回只记录审核结论，不退款，也不扣减用户卡时。</span></div>
              <label><span>审核依据或驳回原因（至少 3 字）</span><textarea maxLength={500} rows={4} value={refundRequestNote} onChange={(event) => setRefundRequestNote(event.target.value)} placeholder="记录充值单、支付状态、退款条件和审核结论；不要填写密钥或签名"/></label>
              <div><button type="button" className="commerce-danger" disabled={Boolean(busy) || refundRequestNote.trim().length < 3} onClick={() => void submitRefundRequestReview("reject")}><X size={15}/>驳回申请</button><button type="button" className="commerce-primary" disabled={Boolean(busy) || refundRequestNote.trim().length < 3} onClick={() => void submitRefundRequestReview("approve")}><Check size={15}/>批准并发起原路退款</button></div>
              <small>批准不等于渠道已退款成功。若渠道返回处理中或结果未知，必须继续在“人民币原路退款”中核验最终结果。</small>
            </footer>}
          </> : <div className="commerce-empty"><ClipboardText size={25}/><strong>{loadingDetail ? "正在读取退款申请详情…" : "选择一笔退款申请查看原因、审核记录和执行结果"}</strong></div>}
        </article>
      </div>
    </> : <>
      <div className="payment-operation-toolbar payment-operation-toolbar--refunds">
        <select aria-label="人民币退款状态" value={refundStatus} onChange={(event) => { setRefundStatus(event.target.value); setRefundPage(1); }}><option value="unknown">渠道结果待核验</option><option value="submitting">已提交渠道</option><option value="preparing">准备中</option><option value="succeeded">原路退款成功</option><option value="failed">原路退款失败</option><option value="">全部状态</option></select>
        <button type="button" disabled={loadingRefunds} onClick={() => void Promise.all([loadRefunds(), selectedRefundId ? loadRefundDetail(selectedRefundId) : Promise.resolve()])}><ArrowClockwise size={15}/>{loadingRefunds ? "读取中" : "刷新"}</button>
      </div>
      <div className="review-console admin-payment-console">
        <aside>
          {refunds.length ? <div className="review-queue">{refunds.map((row) => <button type="button" className={selectedRefundId === row.id ? "active" : ""} key={row.id} onClick={() => { setSelectedRefundId(row.id); setRefundNote(""); setError(""); setSuccess(""); }}><span><small>{row.refund_no} · PAYMENT #{row.payment_order_id}</small><strong>¥{money(row.amount_cny)} 原路退款</strong><em>{refundHoldLabel(row.wallet_hold_status)} · 尝试 {row.attempt_count} 次</em></span><b className={`status-chip status-chip--${paymentStatusTone(row.status)}`}>{paymentRefundStatusLabel(row.status)}</b></button>)}</div> : <div className="commerce-empty"><Receipt size={24}/><strong>{loadingRefunds ? "正在读取退款记录…" : "当前筛选条件下没有人民币退款记录"}</strong></div>}
          <AdminQueuePagination page={refundPage} total={refundTotal} loading={loadingRefunds} onPageChange={setRefundPage}/>
        </aside>
        <article className="review-dossier payment-operation-dossier">
          {refundDetail ? <>
            <header><div><p>{refundDetail.refund_no} / REFUND #{refundDetail.id}</p><h2>¥ {money(refundDetail.amount_cny)} 人民币原路退款</h2></div><span className={`status-chip status-chip--${paymentStatusTone(refundDetail.status)}`}>{paymentRefundStatusLabel(refundDetail.status)}</span></header>
            <dl>
              <div><dt>关联充值单</dt><dd>PAYMENT #{refundDetail.payment_order_id}</dd></div>
              <div><dt>人民币 / 对应卡时</dt><dd>¥ {money(refundDetail.amount_cny)} / {cardHours(refundDetail.card_hours)} 卡时</dd></div>
              <div><dt>钱包卡时处理</dt><dd>{refundHoldLabel(refundDetail.wallet_hold_status)}</dd></div>
              <div><dt>退款前充值状态</dt><dd>{paymentStatusLabel(refundDetail.previous_payment_status)}</dd></div>
              <div><dt>支付渠道结果</dt><dd>{refundDetail.provider_code || "暂无渠道代码"}<small>{refundDetail.provider_message || "暂无渠道说明"}</small></dd></div>
              <div><dt>提交 / 完成时间</dt><dd>{formatDate(refundDetail.requested_at)}<small>完成：{formatDate(refundDetail.resolved_at)}</small></dd></div>
              <div><dt>操作管理员</dt><dd>ADMIN #{refundDetail.actor_user_id}</dd></div>
              <div><dt>幂等请求标识</dt><dd className="payment-operation-mono">{refundDetail.client_request_id}</dd></div>
            </dl>
            <section><h3>退款原因</h3><p data-i18n-skip>{refundDetail.reason}</p></section>
            {refundDetail.resolution_note && <section><h3>最终核验结论</h3><p data-i18n-skip>{refundDetail.resolution_note}</p></section>}
            {canResolveUnknownPaymentRefund(refundDetail.status) && <footer className="payment-operation-actions">
              <div className="payment-provider-evidence"><Warning size={18}/><span>必须由另一名管理员登录七相商户后台，核对退款号与最终状态。不要根据用户截图、页面回跳或一次网络超时做结论。</span></div>
              <label><span>商户后台证据与核验结论（至少 3 字）</span><textarea maxLength={500} rows={4} value={refundNote} onChange={(event) => setRefundNote(event.target.value)} placeholder="记录商户后台退款状态、核验时间及可追溯依据；不要填写密钥或签名"/></label>
              <div><button type="button" className="commerce-danger" disabled={Boolean(busy) || refundNote.trim().length < 3} onClick={() => void submitRefundResolution("failed")}><X size={15}/>确认渠道退款失败</button><button type="button" className="commerce-primary" disabled={Boolean(busy) || refundNote.trim().length < 3} onClick={() => void submitRefundResolution("succeeded")}><Check size={15}/>确认渠道退款成功</button></div>
            </footer>}
          </> : <div className="commerce-empty"><Receipt size={25}/><strong>{loadingDetail ? "正在读取退款详情…" : "选择一笔人民币退款查看渠道响应和钱包冻结状态"}</strong></div>}
        </article>
      </div>
    </>}
  </section>;
}
