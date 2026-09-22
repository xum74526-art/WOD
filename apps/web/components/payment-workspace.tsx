"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwise, Bank, CheckCircle, ClockCountdown, Coins, LockKey, Receipt, WarningCircle } from "@phosphor-icons/react";
import { errorMessage } from "@/lib/commerce-ui";
import { formatFinancialAmount } from "@/lib/financial-format";
import {
  canPrepareRechargeRestart,
  isRegisteredBankCardStatus,
  minimumRechargeAmountCny,
  minimumWithdrawalCardHours,
  rechargeBlocksNewOrder,
  rechargeCanCancel,
  rechargeCanPay,
  rechargeCanQuery,
  rechargeCanRequestRefund,
  rechargeCanRestart,
  rechargeRefundRequestLabel,
  rechargeUiLabel,
  rechargeUiState,
} from "@/lib/finance-ui";
import {
  cancelRechargePayment, cancelWithdrawal, createRechargePayment, createRechargeRefundRequest, createWithdrawal, getMobileLedger, getMobileWallet,
  getRechargePayment, getRechargePaymentConfig, getWithdrawalBundle, listRechargePayments, queryRechargePayment,
  listRechargeRefundRequests,
  type BankCard, type MobileLedgerItem, type MobileWallet, type RechargePaymentConfig,
  type RechargePaymentOrder, type RechargeRefundRequest, type WithdrawalConfig, type WithdrawalOrder,
} from "@/lib/mobile-business-api";
import {
  clearClientRequestIntent,
  clientRequestFingerprint,
  ensureClientRequestIntent,
  readClientRequestIntent,
  saveClientRequestIntent,
  type ClientRequestIntent,
} from "@/lib/client-request-intent";
import { qixiangCheckoutHref } from "@/lib/payment-checkout-navigation";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";

const PENDING_PAYMENT_KEY = "wod-web-pending-recharge";
const RECHARGE_INTENT_KEY = "wod-web-recharge-request-intent";
const WITHDRAWAL_INTENT_KEY = "wod-web-withdrawal-request-intent";
const REFUND_REQUEST_INTENT_KEY_PREFIX = "wod-web-refund-request-intent";
type PendingRechargeSession = { order_no?: string; checkout_url?: string | null; expires_at?: string | null };
const amount = (value: unknown) => formatFinancialAmount(value as number | string | null | undefined);

function requestIntentStorage() {
  try { return window.sessionStorage; } catch { return null; }
}

function paymentLabel(order?: RechargePaymentOrder | null) {
  return rechargeUiLabel(order);
}

function paymentQueryNotice(order: RechargePaymentOrder) {
  const label = paymentLabel(order);
  const state = rechargeUiState(order);
  if (state === "pending") return `查询完成：订单仍在等待支付。${order.can_cancel ? "现在可以取消订单。" : "支付时限内不能安全取消。"}`;
  if (state === "processing") return "查询完成：支付平台已返回结果，正在等待服务端验签并入账，请勿重复充值。";
  if (state === "success") return "查询完成：充值已经到账。";
  return `查询完成：当前状态为“${label}”。${order.failure_reason || ""}`;
}

export function PaymentWorkspace() {
  const { capabilities } = usePlatformCapabilities();
  const directTradeEnabled = capabilities.direct_trade_enabled === true;
  const rechargeEntryEnabled = directTradeEnabled && capabilities.recharge_enabled === true;
  const withdrawalEntryEnabled = directTradeEnabled && capabilities.withdraw_enabled === true;
  const [wallet, setWallet] = useState<MobileWallet | null>(null);
  const [ledger, setLedger] = useState<MobileLedgerItem[]>([]);
  const [paymentConfig, setPaymentConfig] = useState<RechargePaymentConfig | null>(null);
  const [withdrawalConfig, setWithdrawalConfig] = useState<WithdrawalConfig | null>(null);
  const [withdrawals, setWithdrawals] = useState<WithdrawalOrder[]>([]);
  const [cards, setCards] = useState<BankCard[]>([]);
  const [pendingPayment, setPendingPayment] = useState<RechargePaymentOrder | null>(null);
  const [rechargeOrders, setRechargeOrders] = useState<RechargePaymentOrder[]>([]);
  const [rechargePage, setRechargePage] = useState(1);
  const [rechargeTotal, setRechargeTotal] = useState(0);
  const [rechargeStatus, setRechargeStatus] = useState("");
  const [rechargeSearchInput, setRechargeSearchInput] = useState("");
  const [rechargeOrderNo, setRechargeOrderNo] = useState("");
  const [refundRequests, setRefundRequests] = useState<RechargeRefundRequest[]>([]);
  const [refundRequestPage, setRefundRequestPage] = useState(1);
  const [refundRequestTotal, setRefundRequestTotal] = useState(0);
  const [refundRequestStatus, setRefundRequestStatus] = useState("");
  const [refundFormOrder, setRefundFormOrder] = useState<RechargePaymentOrder | null>(null);
  const [refundReason, setRefundReason] = useState("");
  const [withdrawalPage, setWithdrawalPage] = useState(1);
  const [withdrawalTotal, setWithdrawalTotal] = useState(0);
  const [withdrawalStatus, setWithdrawalStatus] = useState("");
  const [recharge, setRecharge] = useState({ amount: "100", payment_type: "alipay" as "alipay" | "wxpay" });
  const [withdrawal, setWithdrawal] = useState({ amount: "", bank_card_id: "" });
  const [tab, setTab] = useState<"ledger" | "recharges" | "refundRequests" | "withdrawals">("ledger");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [paymentChecking, setPaymentChecking] = useState(false);
  const [now, setNow] = useState(Date.now());
  const checkingPayment = useRef(false);
  const creatingRecharge = useRef(false);
  const creatingWithdrawal = useRef(false);
  const rechargeIntent = useRef<ClientRequestIntent | null>(null);
  const withdrawalIntent = useRef<ClientRequestIntent | null>(null);
  const refundRequestIntent = useRef<ClientRequestIntent | null>(null);
  const rechargeFormRef = useRef<HTMLFormElement>(null);

  const load = useCallback(async () => {
    setError("");
    const [walletResult, ledgerResult, paymentResult, rechargeOrderResult, refundRequestResult, withdrawalResult] = await Promise.allSettled([
      getMobileWallet(),
      getMobileLedger(),
      getRechargePaymentConfig(),
      listRechargePayments({ page: rechargePage, page_size: 20, status: rechargeStatus, order_no: rechargeOrderNo }),
      listRechargeRefundRequests({ page: refundRequestPage, page_size: 20, status: refundRequestStatus }),
      getWithdrawalBundle({ page: withdrawalPage, page_size: 20, status_filter: withdrawalStatus }),
    ]);
    if (walletResult.status === "fulfilled") setWallet(walletResult.value);
    if (ledgerResult.status === "fulfilled") setLedger(ledgerResult.value.items || []);
    if (paymentResult.status === "fulfilled") {
      setPaymentConfig(paymentResult.value);
      const first = paymentResult.value.payment_types?.[0];
      if (first) setRecharge((value) => paymentResult.value.payment_types?.includes(value.payment_type)
        ? value
        : { ...value, payment_type: first });
    }
    if (rechargeOrderResult.status === "fulfilled") {
      setRechargeOrders(rechargeOrderResult.value.items || []);
      setRechargeTotal(rechargeOrderResult.value.total || 0);
    }
    if (refundRequestResult.status === "fulfilled") {
      setRefundRequests(refundRequestResult.value.items || []);
      setRefundRequestTotal(refundRequestResult.value.total || 0);
    }
    if (withdrawalResult.status === "fulfilled") {
      const [config, page, bankCards] = withdrawalResult.value;
      const selectable = bankCards.filter((card) => (
        isRegisteredBankCardStatus(card.status) && card.consent_recorded
      ));
      setWithdrawalConfig(config); setWithdrawals(page.items || []); setWithdrawalTotal(page.total || 0); setCards(selectable);
      setWithdrawal((value) => ({
        ...value,
        bank_card_id: selectable.some((card) => String(card.id) === value.bank_card_id)
          ? value.bank_card_id
          : String(selectable.find((card) => card.is_default)?.id || selectable[0]?.id || ""),
      }));
    }
    const failed = [walletResult, ledgerResult, paymentResult, rechargeOrderResult, refundRequestResult, withdrawalResult].find((result) => result.status === "rejected");
    if (failed?.status === "rejected") setError(errorMessage(failed.reason));
  }, [rechargeOrderNo, rechargePage, rechargeStatus, refundRequestPage, refundRequestStatus, withdrawalPage, withdrawalStatus]);

  const refreshPayment = useCallback(async (showError = false) => {
    let stored: PendingRechargeSession | null = null;
    try { stored = JSON.parse(localStorage.getItem(PENDING_PAYMENT_KEY) || "null") as PendingRechargeSession | null; } catch { localStorage.removeItem(PENDING_PAYMENT_KEY); }
    const orderNo = stored?.order_no;
    if (!orderNo || checkingPayment.current) return;
    checkingPayment.current = true; setPaymentChecking(true);
    if (showError) { setError(""); setMessage(""); }
    try {
      let order = await getRechargePayment(orderNo);
      let providerQueryFailed = false;
      if (rechargeBlocksNewOrder(order) && rechargeCanQuery(order)) {
        try { order = await queryRechargePayment(orderNo); }
        catch (reason) {
          providerQueryFailed = true;
          if (showError) setError(`暂时无法查询支付平台：${errorMessage(reason)}`);
        }
      }
      setPendingPayment(order);
      setRechargeOrders((rows) => rows.map((row) => row.order_no === order.order_no ? order : row));
      localStorage.setItem(PENDING_PAYMENT_KEY, JSON.stringify({ ...stored, order_no: order.order_no, checkout_url: order.checkout_url || stored?.checkout_url, expires_at: order.expires_at }));
      if (showError && !providerQueryFailed) setMessage(paymentQueryNotice(order));
      if (order.credited_at) await load();
    } catch (reason) { if (showError) setError(errorMessage(reason)); }
    finally { checkingPayment.current = false; setPaymentChecking(false); }
  }, [load]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void refreshPayment(false); }, [refreshPayment]);
  useEffect(() => {
    if (!rechargeBlocksNewOrder(pendingPayment)) return;
    const timer = window.setInterval(() => { if (!document.hidden) void refreshPayment(false); }, 5000);
    return () => window.clearInterval(timer);
  }, [pendingPayment?.credited_at, pendingPayment?.status, refreshPayment]);
  useEffect(() => {
    if (!pendingPayment?.expires_at || pendingPayment.status !== "pending") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pendingPayment?.expires_at, pendingPayment?.status]);

  const paymentTypes = paymentConfig?.payment_types || [];
  const rechargeEnabled = Boolean(paymentConfig?.enabled && paymentTypes.length);
  const rechargeMinimum = minimumRechargeAmountCny(paymentConfig?.min_amount_cny);
  const withdrawalMinimum = minimumWithdrawalCardHours(withdrawalConfig?.min_card_hours);
  const remainingSeconds = useMemo(() => pendingPayment?.expires_at
    ? Math.max(0, Math.ceil((new Date(pendingPayment.expires_at).getTime() - now) / 1000))
    : Number(pendingPayment?.remaining_seconds || 0), [now, pendingPayment]);

  async function submitRecharge(event: FormEvent) {
    event.preventDefault();
    if (creatingRecharge.current) return;
    const value = Number(recharge.amount);
    if (!Number.isFinite(value) || value < rechargeMinimum || value > Number(paymentConfig?.max_amount_cny || Infinity)) {
      setError(`充值金额须在 ${amount(rechargeMinimum)} 至 ${amount(paymentConfig?.max_amount_cny)} 元之间`); return;
    }
    const normalizedValue = Number(value.toFixed(2));
    if (!paymentTypes.includes(recharge.payment_type)) { setError("当前支付渠道未启用"); return; }
    if (rechargeBlocksNewOrder(pendingPayment)) {
      setMessage("当前充值仍在等待支付或入账，请继续支付、查询状态，或使用“更换充值金额”。");
      return;
    }
    const rate = Number(paymentConfig?.card_hour_rmb_rate || 0);
    const cardHours = rate > 0 ? normalizedValue / rate : 0;
    if (!window.confirm(`请确认充值金额：¥ ${amount(normalizedValue)}\n预计到账：${amount(cardHours)} 卡时\n\n确认金额无误后再前往支付。`)) return;
    creatingRecharge.current = true;
    setBusy("recharge"); setError(""); setMessage("");
    try {
      const fingerprint = clientRequestFingerprint([normalizedValue.toFixed(2), recharge.payment_type]);
      const storage = requestIntentStorage();
      const intent = ensureClientRequestIntent(
        rechargeIntent.current || (storage ? readClientRequestIntent(storage, RECHARGE_INTENT_KEY) : null),
        fingerprint,
        "recharge",
      );
      rechargeIntent.current = intent;
      if (storage) saveClientRequestIntent(storage, RECHARGE_INTENT_KEY, intent);
      const order = await createRechargePayment(normalizedValue, recharge.payment_type, intent.requestId);
      rechargeIntent.current = null;
      if (storage) clearClientRequestIntent(storage, RECHARGE_INTENT_KEY);
      setPendingPayment(order);
      setRechargeOrders((rows) => [order, ...rows.filter((row) => row.order_no !== order.order_no)]);
      setRechargeTotal((total) => total + 1);
      setRechargePage(1);
      setRechargeStatus(""); setRechargeSearchInput(""); setRechargeOrderNo("");
      localStorage.setItem(PENDING_PAYMENT_KEY, JSON.stringify({ order_no: order.order_no, checkout_url: order.checkout_url, expires_at: order.expires_at }));
      if (order.checkout_url) {
        const href = qixiangCheckoutHref(order.checkout_url, window.location.origin);
        if (!href) {
          setError("支付服务返回了无法识别的收银台地址，请勿继续跳转并联系平台处理。");
          return;
        }
        window.location.assign(href);
      } else await load();
    } catch (reason) { setError(errorMessage(reason)); } finally { creatingRecharge.current = false; setBusy(""); }
  }

  async function submitWithdrawal(event: FormEvent) {
    event.preventDefault();
    if (creatingWithdrawal.current) return;
    const value = Number(withdrawal.amount);
    const card = cards.find((item) => item.id === Number(withdrawal.bank_card_id));
    if (!Number.isFinite(value) || value < withdrawalMinimum || value > Number(withdrawalConfig?.max_card_hours || Infinity)) {
      setError(`提现卡时须在 ${amount(withdrawalMinimum)} 至 ${amount(withdrawalConfig?.max_card_hours)} 之间`); return;
    }
    const normalizedValue = Number(value.toFixed(3));
    if (normalizedValue > Number(wallet?.withdrawable_balance || 0)) { setError("提现金额超过当前可提现余额"); return; }
    if (!card) { setError("请选择状态可用的银行卡"); return; }
    creatingWithdrawal.current = true;
    setBusy("withdraw"); setError("");
    try {
      const fingerprint = clientRequestFingerprint([normalizedValue.toFixed(3), card.id]);
      const storage = requestIntentStorage();
      const intent = ensureClientRequestIntent(
        withdrawalIntent.current || (storage ? readClientRequestIntent(storage, WITHDRAWAL_INTENT_KEY) : null),
        fingerprint,
        "withdrawal",
      );
      withdrawalIntent.current = intent;
      if (storage) saveClientRequestIntent(storage, WITHDRAWAL_INTENT_KEY, intent);
      await createWithdrawal({ amount_card_hours: normalizedValue, bank_card_id: card.id, client_request_id: intent.requestId });
      withdrawalIntent.current = null;
      if (storage) clearClientRequestIntent(storage, WITHDRAWAL_INTENT_KEY);
      setWithdrawal((current) => ({ ...current, amount: "" }));
      setWithdrawalPage(1); setWithdrawalStatus(""); setTab("withdrawals"); await load();
    } catch (reason) { setError(errorMessage(reason)); } finally { creatingWithdrawal.current = false; setBusy(""); }
  }

  async function cancel(id: number) {
    if (!window.confirm("确定取消这笔提现申请？")) return;
    setBusy(`cancel-${id}`); setError("");
    try { await cancelWithdrawal(id); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function refreshRechargeOrder(row: RechargePaymentOrder) {
    if (!rechargeCanQuery(row)) return;
    setBusy(`recharge-query-${row.order_no}`); setError(""); setMessage("");
    try {
      const order = await queryRechargePayment(row.order_no);
      if (pendingPayment?.order_no === order.order_no) setPendingPayment(order);
      setRechargeOrders((rows) => rows.map((item) => item.order_no === order.order_no ? order : item));
      setMessage(paymentQueryNotice(order));
      if (order.credited_at) await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  async function cancelRechargeOrder(row: RechargePaymentOrder) {
    if (!rechargeCanCancel(row)) {
      setMessage("七相支付没有主动关闭订单接口。支付时限内不能安全取消，请在倒计时结束并查询确认未支付后再取消。");
      return;
    }
    if (!window.confirm(`确定取消充值订单 ${row.order_no}？取消前会再次向支付平台确认该订单未支付。`)) return;
    setBusy(`recharge-cancel-${row.order_no}`); setError(""); setMessage("");
    try {
      const order = await cancelRechargePayment(row.order_no);
      setRechargeOrders((rows) => rows.map((item) => item.order_no === order.order_no ? order : item));
      if (pendingPayment?.order_no === order.order_no) {
        setPendingPayment(order);
        localStorage.removeItem(PENDING_PAYMENT_KEY);
      }
      setMessage(`充值订单 ${order.order_no} 已取消，可以选择“再来一单”。`);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  function restartRecharge(row: RechargePaymentOrder) {
    let storedOrderNo = "";
    try {
      const stored = JSON.parse(localStorage.getItem(PENDING_PAYMENT_KEY) || "null") as PendingRechargeSession | null;
      storedOrderNo = String(stored?.order_no || "");
    } catch {
      // A malformed value cannot identify a valid live checkout; remove only
      // that unreadable value before preparing a terminal-order restart.
      localStorage.removeItem(PENDING_PAYMENT_KEY);
    }
    if (!canPrepareRechargeRestart(pendingPayment, storedOrderNo, row.order_no)) {
      setError("");
      setMessage("本机还有另一笔充值订单等待处理。请先继续支付、查询状态或更换该订单金额，不能覆盖它的恢复信息。");
      return;
    }
    const paymentType = row.channel === "wxpay" ? "wxpay" : "alipay";
    setRecharge({ amount: String(row.amount_cny), payment_type: paymentType });
    localStorage.removeItem(PENDING_PAYMENT_KEY);
    if (pendingPayment?.order_no === row.order_no) setPendingPayment(null);
    setError("");
    setMessage(`已带入上一单的 ${amount(row.amount_cny)} 元和${paymentType === "wxpay" ? "微信支付" : "支付宝"}，确认后即可重新下单。`);
    window.requestAnimationFrame(() => rechargeFormRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }

  async function replaceRechargeAmount() {
    if (!pendingPayment || busy || checkingPayment.current) return;
    checkingPayment.current = true;
    setBusy("payment-replace"); setError(""); setMessage("");
    try {
      const order = await queryRechargePayment(pendingPayment.order_no);
      setPendingPayment(order);
      setRechargeOrders((rows) => rows.map((row) => row.order_no === order.order_no ? order : row));
      if (rechargeUiState(order) !== "pending") {
        setMessage(`订单状态已经变为“${paymentLabel(order)}”，不能更换金额，请继续等待或查看订单记录。`);
        return;
      }
      if (!window.confirm(`当前 ¥ ${amount(order.amount_cny)} 订单不会被支付平台立即关闭，仍会保留在充值订单中，并可能继续被支付。\n\n请不要再支付旧订单。确认后仅放弃本机支付会话并重新填写金额。`)) return;
      localStorage.removeItem(PENDING_PAYMENT_KEY);
      setPendingPayment(null);
      setMessage(`已放弃订单 ${order.order_no} 的本机支付会话，原订单仍保留在充值记录中。请填写正确金额。`);
      window.requestAnimationFrame(() => rechargeFormRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
    } catch (reason) {
      setError(`暂时无法查询支付平台，未更换金额：${errorMessage(reason)}`);
    } finally { checkingPayment.current = false; setBusy(""); }
  }

  function continueCheckout() {
    try {
      const stored = JSON.parse(localStorage.getItem(PENDING_PAYMENT_KEY) || "null") as { checkout_url?: string } | null;
      if (stored?.checkout_url) {
        const href = qixiangCheckoutHref(stored.checkout_url, window.location.origin);
        if (!href) {
          setError("已保存的收银台地址无效，请查询订单状态或联系平台处理。");
          return;
        }
        window.location.assign(href);
      }
    } catch { localStorage.removeItem(PENDING_PAYMENT_KEY); }
  }

  function dismissPayment() { localStorage.removeItem(PENDING_PAYMENT_KEY); setPendingPayment(null); }

  function applyRechargeSearch(event: FormEvent) {
    event.preventDefault();
    setRechargePage(1);
    setRechargeOrderNo(rechargeSearchInput.trim().toUpperCase());
  }

  function openRefundRequest(row: RechargePaymentOrder) {
    if (!rechargeCanRequestRefund(row)) return;
    setRefundFormOrder(row);
    setRefundReason("");
    setError("");
    setMessage("");
  }

  async function submitRefundRequest(event: FormEvent) {
    event.preventDefault();
    if (!refundFormOrder || busy === "refund-request") return;
    const reason = refundReason.trim().replace(/\s+/g, " ");
    if (reason.length < 5 || reason.length > 500) {
      setError("退款原因需填写 5–500 个字符。");
      return;
    }
    setBusy("refund-request"); setError(""); setMessage("");
    const intentKey = `${REFUND_REQUEST_INTENT_KEY_PREFIX}:${refundFormOrder.order_no}`;
    try {
      const storage = requestIntentStorage();
      const fingerprint = clientRequestFingerprint([refundFormOrder.order_no, reason]);
      const intent = ensureClientRequestIntent(
        refundRequestIntent.current || (storage ? readClientRequestIntent(storage, intentKey) : null),
        fingerprint,
        "refund-request",
      );
      refundRequestIntent.current = intent;
      if (storage) saveClientRequestIntent(storage, intentKey, intent);
      const created = await createRechargeRefundRequest(refundFormOrder.order_no, {
        client_request_id: intent.requestId,
        reason,
      });
      refundRequestIntent.current = null;
      if (storage) clearClientRequestIntent(storage, intentKey);
      setRefundFormOrder(null); setRefundReason(""); setRefundRequestPage(1); setRefundRequestStatus(""); setTab("refundRequests");
      try {
        const pageResult = await listRechargeRefundRequests({ page: 1, page_size: 20 });
        setRefundRequests(pageResult.items || [created]);
        setRefundRequestTotal(pageResult.total || 1);
      } catch {
        setRefundRequests((rows) => [created, ...rows.filter((row) => row.id !== created.id)].slice(0, 20));
        setRefundRequestTotal((total) => Math.max(1, total));
      }
      setMessage(`退款申请 ${created.request_no} 已提交，平台审核前不会直接扣减或退回资金。`);
    } catch (reasonValue) { setError(errorMessage(reasonValue)); }
    finally { setBusy(""); }
  }

  const pendingState = rechargeUiState(pendingPayment);
  const rechargePages = Math.max(1, Math.ceil(rechargeTotal / 20));
  const withdrawalPages = Math.max(1, Math.ceil(withdrawalTotal / 20));
  const refundRequestPages = Math.max(1, Math.ceil(refundRequestTotal / 20));

  if (!wallet) return <section className="workspace-page"><div className="workspace-skeleton" aria-label="正在读取钱包" />{error && <div className="commerce-error">{error}</div>}</section>;
  return <section className="workspace-page mobile-wallet-workspace">
    <div className="mobile-ops-head"><div><p>ACCOUNT / WALLET</p><h1>{directTradeEnabled ? "钱包与结算" : "钱包与历史记录"}</h1><span>{directTradeEnabled ? "查看余额、流水、充值和提现记录。" : "查看已有余额、流水、充值和提现记录。新充值与提现暂未开放。"}</span></div><button onClick={() => void load()}><ArrowClockwise size={16}/>刷新</button></div>
    {error && <div className="commerce-error">{error}</div>}
    {message && <div className="commerce-success">{message}</div>}
    <div className="mobile-data-spine"><article><small>可用余额</small><strong>{amount(wallet.balance)}</strong><span>卡时</span></article><article><small>可提现余额</small><strong>{amount(wallet.withdrawable_balance)}</strong><span>已结算收益</span></article><article><small>提现冻结</small><strong>{amount(wallet.withdraw_frozen)}</strong><span>卡时</span></article><article><small>累计收益</small><strong>{amount(wallet.total_income)}</strong><span>卡时</span></article></div>
    {pendingPayment && <section className={`wallet-payment-state state-${pendingState}`}>
      <div>{pendingState === "success" ? <CheckCircle size={28}/> : ["failed", "expired", "canceled", "refund_unknown", "refunded"].includes(pendingState) ? <WarningCircle size={28}/> : <ClockCountdown size={28}/>}<span><small>RECHARGE ORDER · {pendingPayment.order_no}</small><strong>{paymentLabel(pendingPayment)}</strong><em>¥ {amount(pendingPayment.amount_cny)} · {amount(pendingPayment.card_hours)} 卡时{pendingPayment.failure_reason ? ` · ${pendingPayment.failure_reason}` : ""}</em></span></div>
      {pendingState === "pending" && <b>{Math.floor(remainingSeconds / 60).toString().padStart(2, "0")}:{(remainingSeconds % 60).toString().padStart(2, "0")}</b>}
      <nav>
        {rechargeEntryEnabled && pendingState === "pending" && rechargeCanPay(pendingPayment) && <button onClick={continueCheckout}>继续支付</button>}
        {rechargeEntryEnabled && pendingState === "pending" && rechargeCanQuery(pendingPayment) && <button onClick={() => void replaceRechargeAmount()} disabled={busy === "payment-replace" || paymentChecking}>{busy === "payment-replace" || paymentChecking ? "查询中…" : "更换充值金额"}</button>}
        {rechargeCanQuery(pendingPayment) && <button onClick={() => void refreshPayment(true)} disabled={paymentChecking}>{paymentChecking ? "查询中…" : "查询状态"}</button>}
        {rechargeCanCancel(pendingPayment) && <button className="danger" onClick={() => void cancelRechargeOrder(pendingPayment)} disabled={busy === `recharge-cancel-${pendingPayment.order_no}`} title="取消前会再次确认订单未支付">{busy === `recharge-cancel-${pendingPayment.order_no}` ? "取消中…" : "取消订单"}</button>}
        {rechargeEntryEnabled && rechargeCanRestart(pendingPayment) && <button onClick={() => restartRecharge(pendingPayment)} title="使用相同金额和支付方式重新填写">再来一单</button>}
        {!["pending", "processing"].includes(pendingState) && <button onClick={dismissPayment}>完成</button>}
      </nav>
    </section>}
    {(rechargeEntryEnabled || withdrawalEntryEnabled) ? <div className="mobile-service-columns wallet-actions">
      {rechargeEntryEnabled && <form ref={rechargeFormRef} className="mobile-business-form" onSubmit={submitRecharge}><header><Coins size={21}/><div><small>RECHARGE</small><h2>账户充值</h2></div></header><label>充值金额（人民币，最低 {amount(rechargeMinimum)} 元）<input type="number" min={rechargeMinimum} max={paymentConfig?.max_amount_cny || undefined} step="0.01" value={recharge.amount} onChange={(event) => setRecharge({ ...recharge, amount: event.target.value })} required/></label><label>支付方式<select value={recharge.payment_type} onChange={(event) => setRecharge({ ...recharge, payment_type: event.target.value as "alipay" | "wxpay" })} disabled={!paymentTypes.length}>{paymentTypes.length ? paymentTypes.map((type) => <option value={type} key={type}>{type === "alipay" ? "支付宝" : "微信支付"}</option>) : <option>暂无可用渠道</option>}</select></label><button className="commerce-primary" disabled={!rechargeEnabled || busy === "recharge" || rechargeBlocksNewOrder(pendingPayment)}>{busy === "recharge" ? "正在创建…" : rechargeBlocksNewOrder(pendingPayment) ? "请先处理当前充值订单" : rechargeEnabled ? "确认金额并前往支付" : "充值服务未开放"}</button><p><LockKey size={14}/>创建订单前会再次确认金额；只有服务端确认卡时到账后才显示充值成功。</p></form>}
      {withdrawalEntryEnabled && <form className="mobile-business-form" onSubmit={submitWithdrawal}><header><Bank size={21}/><div><small>WITHDRAWAL</small><h2>申请提现</h2></div></header><label>提现卡时（最低 {amount(withdrawalMinimum)} 卡时）<input type="number" min={withdrawalMinimum} max={Math.min(Number(withdrawalConfig?.max_card_hours || Infinity), Number(wallet.withdrawable_balance || 0)) || undefined} step="0.001" value={withdrawal.amount} onChange={(event) => setWithdrawal({ ...withdrawal, amount: event.target.value })} required/></label><label>到账银行卡<select value={withdrawal.bank_card_id} onChange={(event) => setWithdrawal({ ...withdrawal, bank_card_id: event.target.value })} required><option value="">选择可用银行卡</option>{cards.map((card) => <option value={card.id} key={card.id}>{card.bank_name} ···· {card.card_last4 || card.card_number.slice(-4)} · {card.status}</option>)}</select></label><button className="commerce-primary" disabled={!wallet.withdraw_service_enabled || !withdrawalConfig?.enabled || !cards.length || busy === "withdraw"}>{busy === "withdraw" ? "提交中…" : cards.length ? withdrawalConfig?.enabled && wallet.withdraw_service_enabled ? "提交提现申请" : "提现服务未开放" : "请先绑定可用银行卡"}</button><p>当前最多可提现 {amount(wallet.withdrawable_balance)} 卡时。{withdrawalConfig?.notice || "提现由财务人工审核并转账。"}</p></form>}
    </div> : <div className="workspace-service-note">在线充值与提现暂未开放。已有余额、历史流水和订单状态仍可查询；如需算力服务，请前往需求页面提交信息并等待人工联系。</div>}
    <section className="mobile-record-panel wallet-ledger">
      <header><Receipt size={20}/><div><small>ACCOUNT RECORDS</small><h2>{tab === "ledger" ? "钱包流水" : tab === "recharges" ? "充值订单" : tab === "refundRequests" ? "退款申请" : "提现记录"}</h2></div><nav><button className={tab === "ledger" ? "active" : ""} onClick={() => setTab("ledger")}>钱包流水</button><button className={tab === "recharges" ? "active" : ""} onClick={() => setTab("recharges")}>充值订单</button><button className={tab === "refundRequests" ? "active" : ""} onClick={() => setTab("refundRequests")}>退款申请</button><button className={tab === "withdrawals" ? "active" : ""} onClick={() => setTab("withdrawals")}>提现记录</button></nav></header>
      {tab === "recharges" && <form className="refund-toolbar" onSubmit={applyRechargeSearch}>
        <input aria-label="搜索充值订单号" placeholder="输入完整充值订单号" value={rechargeSearchInput} onChange={(event) => setRechargeSearchInput(event.target.value)} />
        <select aria-label="充值状态" value={rechargeStatus} onChange={(event) => { setRechargePage(1); setRechargeStatus(event.target.value); }}>
          <option value="">全部状态</option><option value="pending">等待支付</option><option value="paid">支付确认中</option><option value="review">复核中</option><option value="late_paid_review">超时到账复核</option><option value="refund_pending">退款提交中</option><option value="refund_unknown">结果待核验</option><option value="refunded">已退款</option><option value="canceled">已取消</option><option value="expired">已过期</option><option value="failed">支付失败</option>
        </select>
        <button type="submit">查询订单</button>
        {(rechargeOrderNo || rechargeSearchInput) && <button type="button" onClick={() => { setRechargeSearchInput(""); setRechargeOrderNo(""); setRechargePage(1); }}>清除</button>}
      </form>}
      {tab === "withdrawals" && <div className="refund-toolbar">
        <select aria-label="提现状态" value={withdrawalStatus} onChange={(event) => { setWithdrawalPage(1); setWithdrawalStatus(event.target.value); }}>
          <option value="">全部状态</option><option value="reviewing">待审核</option><option value="manual_payment_pending">待打款</option><option value="paid">已打款</option><option value="rejected">已驳回</option><option value="failed">打款失败</option><option value="canceled">已取消</option>
        </select>
        <span>共 {withdrawalTotal} 条提现记录</span>
      </div>}
      {tab === "refundRequests" && <div className="refund-toolbar">
        <select aria-label="退款申请状态" value={refundRequestStatus} onChange={(event) => { setRefundRequestPage(1); setRefundRequestStatus(event.target.value); }}>
          <option value="">全部状态</option><option value="pending_review">待平台审核</option><option value="approved">审核已通过</option><option value="processing">退款处理中</option><option value="succeeded">退款已完成</option><option value="rejected">申请已驳回</option><option value="failed">退款失败</option><option value="canceled">申请已取消</option>
        </select>
        <span>共 {refundRequestTotal} 条退款申请</span>
      </div>}
      {refundFormOrder && <form className="wallet-refund-request-form" onSubmit={submitRefundRequest}>
        <header><div><small>REFUND REQUEST</small><strong>申请退回充值款</strong></div><button type="button" onClick={() => { setRefundFormOrder(null); setRefundReason(""); }}>关闭</button></header>
        <p>订单 {refundFormOrder.order_no} · ¥ {amount(refundFormOrder.amount_cny)} · {amount(refundFormOrder.card_hours)} 卡时</p>
        <label>退款原因<textarea aria-label="退款原因" minLength={5} maxLength={500} value={refundReason} onChange={(event) => setRefundReason(event.target.value)} placeholder="请说明退款原因（5–500 个字符）" required/></label>
        <footer><span>提交后由平台审核；审核通过后才会发起原路退款。</span><button type="button" onClick={() => { setRefundFormOrder(null); setRefundReason(""); }}>取消</button><button className="commerce-primary" disabled={busy === "refund-request"}>{busy === "refund-request" ? "提交中…" : "提交退款申请"}</button></footer>
      </form>}
      {tab === "ledger" ? ledger.length ? ledger.map((row) => <article key={row.id}><span><strong>{row.direction === "in" ? "+" : "-"}{amount(row.amount)} 卡时</strong><small>{row.remark || row.type} · 余额 {amount(row.balance_after)}</small></span><b>{row.type}</b><time>{row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "—"}</time></article>) : <div className="mobile-inline-empty">暂无钱包流水</div>
        : tab === "recharges" ? rechargeOrders.length ? rechargeOrders.map((row) => <article className="wallet-recharge-order" key={row.order_no}>
          <span><strong>¥ {amount(row.amount_cny)} · {amount(row.card_hours)} 卡时</strong><small>{row.order_no} · {row.provider === "qixiangpay" ? "七相支付" : row.provider || "历史支付"}</small>{row.failure_reason && <small>{row.failure_reason}</small>}</span>
          <b>{paymentLabel(row)}</b>
          <span><strong>{row.channel === "wxpay" ? "微信支付" : row.channel === "alipay" ? "支付宝" : row.channel || "—"}</strong><small>创建：{row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "—"}</small><small>{row.paid_at ? `支付：${new Date(row.paid_at).toLocaleString("zh-CN")}` : `到期：${row.expires_at ? new Date(row.expires_at).toLocaleString("zh-CN") : "—"}`}</small></span>
          <time className="wallet-order-actions">
            {rechargeCanQuery(row) && <button disabled={busy === `recharge-query-${row.order_no}`} onClick={() => void refreshRechargeOrder(row)}>{busy === `recharge-query-${row.order_no}` ? "查询中…" : "查询状态"}</button>}
            {rechargeCanCancel(row) && <button className="danger" disabled={busy === `recharge-cancel-${row.order_no}`} title="取消前会再次确认订单未支付" onClick={() => void cancelRechargeOrder(row)}>{busy === `recharge-cancel-${row.order_no}` ? "取消中…" : "取消订单"}</button>}
            {rechargeCanRequestRefund(row) && <button className="danger" onClick={() => openRefundRequest(row)}>申请退款</button>}
            {rechargeEntryEnabled && rechargeCanRestart(row) && <button onClick={() => restartRecharge(row)}>再来一单</button>}
          </time>
        </article>) : <div className="mobile-inline-empty">暂无充值订单</div>
          : tab === "refundRequests" ? refundRequests.length ? refundRequests.map((row) => <article className="wallet-refund-request" key={row.id}><span><strong>¥ {amount(row.amount_cny)} · {amount(row.card_hours)} 卡时</strong><small>{row.request_no}</small><small>充值订单：{row.order_no}</small></span><b>{rechargeRefundRequestLabel(row)}</b><span><strong>申请原因</strong><small>{row.reason}</small></span><time>提交：{row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "—"}{row.reviewed_at && <small>审核：{new Date(row.reviewed_at).toLocaleString("zh-CN")}</small>}</time></article>) : <div className="mobile-inline-empty">暂无退款申请</div>
            : withdrawals.length ? withdrawals.map((row) => <article key={row.id}><span><strong>{amount(row.amount_card_hours)} 卡时</strong><small>{row.order_no} · {row.bank_card.bank_name} ···· {row.bank_card.card_last4 || row.bank_card.card_number?.slice(-4)}</small></span><b>{row.status}</b><span><strong>¥ {amount(row.net_amount_cny)}</strong><small>手续费 ¥ {amount(row.fee_cny)}</small></span><time>{row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "—"}{row.status === "reviewing" && <button disabled={busy === `cancel-${row.id}`} onClick={() => void cancel(row.id)}>取消</button>}</time></article>) : <div className="mobile-inline-empty">暂无提现记录</div>}
      {tab === "recharges" && <nav className="community-page-nav"><button disabled={rechargePage <= 1} onClick={() => setRechargePage((page) => page - 1)}>上一页</button><span>第 {rechargePage} / {rechargePages} 页 · 共 {rechargeTotal} 条</span><button disabled={rechargePage >= rechargePages} onClick={() => setRechargePage((page) => page + 1)}>下一页</button></nav>}
      {tab === "withdrawals" && <nav className="community-page-nav"><button disabled={withdrawalPage <= 1} onClick={() => setWithdrawalPage((page) => page - 1)}>上一页</button><span>第 {withdrawalPage} / {withdrawalPages} 页</span><button disabled={withdrawalPage >= withdrawalPages} onClick={() => setWithdrawalPage((page) => page + 1)}>下一页</button></nav>}
      {tab === "refundRequests" && <nav className="community-page-nav"><button disabled={refundRequestPage <= 1} onClick={() => setRefundRequestPage((page) => page - 1)}>上一页</button><span>第 {refundRequestPage} / {refundRequestPages} 页 · 共 {refundRequestTotal} 条</span><button disabled={refundRequestPage >= refundRequestPages} onClick={() => setRefundRequestPage((page) => page + 1)}>下一页</button></nav>}
    </section>
  </section>;
}
