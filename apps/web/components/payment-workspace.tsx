"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowClockwise, Bank, CheckCircle, ClockCountdown, Coins, LockKey, Receipt, WarningCircle } from "@phosphor-icons/react";
import { errorMessage } from "@/lib/commerce-ui";
import {
  cancelWithdrawal, createRechargePayment, createWithdrawal, getMobileLedger, getMobileWallet,
  getRechargePayment, getRechargePaymentConfig, getWithdrawalBundle, queryRechargePayment,
  type BankCard, type MobileLedgerItem, type MobileWallet, type RechargePaymentConfig,
  type RechargePaymentOrder, type WithdrawalConfig, type WithdrawalOrder,
} from "@/lib/mobile-business-api";

const PENDING_PAYMENT_KEY = "wod-web-pending-recharge";
type PendingRechargeSession = { order_no?: string; checkout_url?: string | null; expires_at?: string | null };
const registeredCardStatuses = new Set(["registered", "pending_review", "active"]);
const amount = (value: unknown) => { const n = Number(value || 0); return Number.isFinite(n) ? n.toFixed(2) : "0.00"; };

function checkoutHref(checkoutUrl: string) {
  const parsed = new URL(checkoutUrl, window.location.origin);
  const match = parsed.pathname.match(/^\/api\/payments\/mapay\/checkout\/([A-Za-z0-9_-]+)$/);
  return match ? `/api/v1/canonical/payments/mapay/checkout/${match[1]}` : parsed.toString();
}

function paymentLabel(status?: string) {
  return ({ pending: "等待支付", review: "确认中", paid: "充值成功", expired: "支付已过期", failed: "支付失败", late_paid_review: "超时到账复核中" } as Record<string, string>)[status || ""] || status || "无待处理订单";
}

function paymentActive(status?: string) { return status === "pending" || status === "review"; }

export function PaymentWorkspace() {
  const [wallet, setWallet] = useState<MobileWallet | null>(null);
  const [ledger, setLedger] = useState<MobileLedgerItem[]>([]);
  const [paymentConfig, setPaymentConfig] = useState<RechargePaymentConfig | null>(null);
  const [withdrawalConfig, setWithdrawalConfig] = useState<WithdrawalConfig | null>(null);
  const [withdrawals, setWithdrawals] = useState<WithdrawalOrder[]>([]);
  const [cards, setCards] = useState<BankCard[]>([]);
  const [pendingPayment, setPendingPayment] = useState<RechargePaymentOrder | null>(null);
  const [recharge, setRecharge] = useState({ amount: "100", payment_type: "alipay" as "alipay" | "wxpay" });
  const [withdrawal, setWithdrawal] = useState({ amount: "", bank_card_id: "" });
  const [tab, setTab] = useState<"ledger" | "withdrawals">("ledger");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [now, setNow] = useState(Date.now());
  const checkingPayment = useRef(false);

  const load = useCallback(async () => {
    setError("");
    const [walletResult, ledgerResult, paymentResult, withdrawalResult] = await Promise.allSettled([
      getMobileWallet(), getMobileLedger(), getRechargePaymentConfig(), getWithdrawalBundle(),
    ]);
    if (walletResult.status === "fulfilled") setWallet(walletResult.value);
    if (ledgerResult.status === "fulfilled") setLedger(ledgerResult.value.items || []);
    if (paymentResult.status === "fulfilled") {
      setPaymentConfig(paymentResult.value);
      const first = paymentResult.value.payment_types?.[0];
      if (first) setRecharge((value) => ({ ...value, payment_type: first }));
    }
    if (withdrawalResult.status === "fulfilled") {
      const [config, page, bankCards] = withdrawalResult.value;
      const selectable = bankCards.filter((card) => registeredCardStatuses.has(card.status));
      setWithdrawalConfig(config); setWithdrawals(page.items || []); setCards(selectable);
      setWithdrawal((value) => ({
        ...value,
        bank_card_id: selectable.some((card) => String(card.id) === value.bank_card_id)
          ? value.bank_card_id
          : String(selectable.find((card) => card.is_default)?.id || selectable[0]?.id || ""),
      }));
    }
    const failed = [walletResult, ledgerResult, paymentResult, withdrawalResult].find((result) => result.status === "rejected");
    if (failed?.status === "rejected") setError(errorMessage(failed.reason));
  }, []);

  const refreshPayment = useCallback(async (showError = false) => {
    let stored: PendingRechargeSession | null = null;
    try { stored = JSON.parse(localStorage.getItem(PENDING_PAYMENT_KEY) || "null") as PendingRechargeSession | null; } catch { localStorage.removeItem(PENDING_PAYMENT_KEY); }
    const orderNo = stored?.order_no;
    if (!orderNo || checkingPayment.current) return;
    checkingPayment.current = true; setBusy("payment-check");
    try {
      let order = await getRechargePayment(orderNo);
      if (paymentActive(order.status) && order.can_query !== false) {
        try { order = await queryRechargePayment(orderNo); } catch { /* a still-pending provider response is normal */ }
      }
      setPendingPayment(order);
      localStorage.setItem(PENDING_PAYMENT_KEY, JSON.stringify({ ...stored, order_no: order.order_no, expires_at: order.expires_at }));
      if (order.status === "paid") await load();
    } catch (reason) { if (showError) setError(errorMessage(reason)); }
    finally { checkingPayment.current = false; setBusy(""); }
  }, [load]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void refreshPayment(false); }, [refreshPayment]);
  useEffect(() => {
    if (!paymentActive(pendingPayment?.status)) return;
    const timer = window.setInterval(() => { if (!document.hidden) void refreshPayment(false); }, 5000);
    return () => window.clearInterval(timer);
  }, [pendingPayment?.status, refreshPayment]);
  useEffect(() => {
    if (!pendingPayment?.expires_at || pendingPayment.status !== "pending") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pendingPayment?.expires_at, pendingPayment?.status]);

  const paymentTypes = paymentConfig?.payment_types || [];
  const rechargeEnabled = Boolean(paymentConfig?.enabled && paymentTypes.length);
  const remainingSeconds = useMemo(() => pendingPayment?.expires_at
    ? Math.max(0, Math.ceil((new Date(pendingPayment.expires_at).getTime() - now) / 1000))
    : Number(pendingPayment?.remaining_seconds || 0), [now, pendingPayment]);

  async function submitRecharge(event: FormEvent) {
    event.preventDefault();
    const value = Number(recharge.amount);
    if (!Number.isFinite(value) || value < Number(paymentConfig?.min_amount_cny || 0) || value > Number(paymentConfig?.max_amount_cny || Infinity)) {
      setError(`充值金额须在 ${amount(paymentConfig?.min_amount_cny)} 至 ${amount(paymentConfig?.max_amount_cny)} 元之间`); return;
    }
    if (!paymentTypes.includes(recharge.payment_type)) { setError("当前支付渠道未启用"); return; }
    setBusy("recharge"); setError("");
    try {
      const order = await createRechargePayment(value, recharge.payment_type);
      setPendingPayment(order);
      localStorage.setItem(PENDING_PAYMENT_KEY, JSON.stringify({ order_no: order.order_no, checkout_url: order.checkout_url, expires_at: order.expires_at }));
      if (order.checkout_url) window.location.assign(checkoutHref(order.checkout_url)); else await load();
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function submitWithdrawal(event: FormEvent) {
    event.preventDefault();
    const value = Number(withdrawal.amount);
    const card = cards.find((item) => item.id === Number(withdrawal.bank_card_id));
    if (!Number.isFinite(value) || value < Number(withdrawalConfig?.min_card_hours || 0) || value > Number(withdrawalConfig?.max_card_hours || Infinity)) {
      setError(`提现卡时须在 ${amount(withdrawalConfig?.min_card_hours)} 至 ${amount(withdrawalConfig?.max_card_hours)} 之间`); return;
    }
    if (value > Number(wallet?.withdrawable_balance || 0)) { setError("提现金额超过当前可提现余额"); return; }
    if (!card) { setError("请选择状态可用的银行卡"); return; }
    setBusy("withdraw"); setError("");
    try {
      await createWithdrawal({ amount_card_hours: value, bank_card_id: card.id, client_request_id: crypto.randomUUID() });
      setWithdrawal((current) => ({ ...current, amount: "" })); setTab("withdrawals"); await load();
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  async function cancel(id: number) {
    if (!window.confirm("确定取消这笔提现申请？")) return;
    setBusy(`cancel-${id}`); setError("");
    try { await cancelWithdrawal(id); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(""); }
  }

  function continueCheckout() {
    try {
      const stored = JSON.parse(localStorage.getItem(PENDING_PAYMENT_KEY) || "null") as { checkout_url?: string } | null;
      if (stored?.checkout_url) window.location.assign(checkoutHref(stored.checkout_url));
    } catch { localStorage.removeItem(PENDING_PAYMENT_KEY); }
  }

  function dismissPayment() { localStorage.removeItem(PENDING_PAYMENT_KEY); setPendingPayment(null); }

  if (!wallet) return <section className="workspace-page"><div className="workspace-skeleton" aria-label="正在读取钱包" />{error && <div className="commerce-error">{error}</div>}</section>;
  return <section className="workspace-page mobile-wallet-workspace">
    <div className="mobile-ops-head"><div><p>ACCOUNT / MOBILE WALLET</p><h1>钱包与结算</h1><span>余额、流水、充值和提现全部使用手机端业务后端。</span></div><button onClick={() => void load()}><ArrowClockwise size={16}/>刷新</button></div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="mobile-data-spine"><article><small>可用余额</small><strong>{amount(wallet.balance)}</strong><span>卡时</span></article><article><small>可提现余额</small><strong>{amount(wallet.withdrawable_balance)}</strong><span>已结算收益</span></article><article><small>提现冻结</small><strong>{amount(wallet.withdraw_frozen)}</strong><span>卡时</span></article><article><small>累计收益</small><strong>{amount(wallet.total_income)}</strong><span>卡时</span></article></div>
    {pendingPayment && <section className={`wallet-payment-state state-${pendingPayment.status}`}><div>{pendingPayment.status === "paid" ? <CheckCircle size={28}/> : ["failed", "expired"].includes(pendingPayment.status) ? <WarningCircle size={28}/> : <ClockCountdown size={28}/>}<span><small>RECHARGE ORDER · {pendingPayment.order_no}</small><strong>{paymentLabel(pendingPayment.status)}</strong><em>¥ {amount(pendingPayment.amount_cny)} · {amount(pendingPayment.card_hours)} 卡时</em></span></div>{pendingPayment.status === "pending" && <b>{Math.floor(remainingSeconds / 60).toString().padStart(2, "0")}:{(remainingSeconds % 60).toString().padStart(2, "0")}</b>}<nav>{pendingPayment.status === "pending" && pendingPayment.can_pay !== false && <button onClick={continueCheckout}>继续支付</button>}{pendingPayment.can_query !== false && paymentActive(pendingPayment.status) && <button onClick={() => void refreshPayment(true)} disabled={busy === "payment-check"}>查询状态</button>}{!paymentActive(pendingPayment.status) && <button onClick={dismissPayment}>完成</button>}</nav></section>}
    <div className="mobile-service-columns wallet-actions">
      <form className="mobile-business-form" onSubmit={submitRecharge}><header><Coins size={21}/><div><small>RECHARGE</small><h2>账户充值</h2></div></header><label>充值金额（人民币）<input type="number" min={paymentConfig?.min_amount_cny || 0.01} max={paymentConfig?.max_amount_cny || undefined} step="0.01" value={recharge.amount} onChange={(event) => setRecharge({ ...recharge, amount: event.target.value })} required/></label><label>支付方式<select value={recharge.payment_type} onChange={(event) => setRecharge({ ...recharge, payment_type: event.target.value as "alipay" | "wxpay" })} disabled={!paymentTypes.length}>{paymentTypes.length ? paymentTypes.map((type) => <option value={type} key={type}>{type === "alipay" ? "支付宝" : "微信支付"}</option>) : <option>暂无可用渠道</option>}</select></label><button className="commerce-primary" disabled={!rechargeEnabled || busy === "recharge" || paymentActive(pendingPayment?.status)}>{busy === "recharge" ? "正在创建…" : paymentActive(pendingPayment?.status) ? "请先完成待支付订单" : rechargeEnabled ? "前往支付" : "充值服务未开放"}</button><p><LockKey size={14}/>支付在后端托管页面完成，Web 不接触支付密钥。</p></form>
      <form className="mobile-business-form" onSubmit={submitWithdrawal}><header><Bank size={21}/><div><small>WITHDRAWAL</small><h2>申请提现</h2></div></header><label>提现卡时<input type="number" min={withdrawalConfig?.min_card_hours || 0.01} max={Math.min(Number(withdrawalConfig?.max_card_hours || Infinity), Number(wallet.withdrawable_balance || 0)) || undefined} step="0.01" value={withdrawal.amount} onChange={(event) => setWithdrawal({ ...withdrawal, amount: event.target.value })} required/></label><label>到账银行卡<select value={withdrawal.bank_card_id} onChange={(event) => setWithdrawal({ ...withdrawal, bank_card_id: event.target.value })} required><option value="">选择可用银行卡</option>{cards.map((card) => <option value={card.id} key={card.id}>{card.bank_name} ···· {card.card_last4 || card.card_number.slice(-4)} · {card.status}</option>)}</select></label><button className="commerce-primary" disabled={!wallet.withdraw_service_enabled || !withdrawalConfig?.enabled || !cards.length || busy === "withdraw"}>{busy === "withdraw" ? "提交中…" : cards.length ? withdrawalConfig?.enabled && wallet.withdraw_service_enabled ? "提交提现申请" : "提现服务未开放" : "请先绑定可用银行卡"}</button><p>当前最多可提现 {amount(wallet.withdrawable_balance)} 卡时。{withdrawalConfig?.notice || "提现由财务人工审核并转账。"}</p></form>
    </div>
    <section className="mobile-record-panel wallet-ledger"><header><Receipt size={20}/><div><small>ACCOUNT LEDGER</small><h2>{tab === "ledger" ? "钱包流水" : "提现记录"}</h2></div><nav><button className={tab === "ledger" ? "active" : ""} onClick={() => setTab("ledger")}>钱包流水</button><button className={tab === "withdrawals" ? "active" : ""} onClick={() => setTab("withdrawals")}>提现记录</button></nav></header>{tab === "ledger" ? ledger.length ? ledger.map((row) => <article key={row.id}><span><strong>{row.direction === "in" ? "+" : "-"}{amount(row.amount)} 卡时</strong><small>{row.remark || row.type} · 余额 {amount(row.balance_after)}</small></span><b>{row.type}</b><time>{row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "—"}</time></article>) : <div className="mobile-inline-empty">暂无钱包流水</div> : withdrawals.length ? withdrawals.map((row) => <article key={row.id}><span><strong>{amount(row.amount_card_hours)} 卡时</strong><small>{row.order_no} · {row.bank_card.bank_name} ···· {row.bank_card.card_last4 || row.bank_card.card_number?.slice(-4)}</small></span><b>{row.status}</b><span><strong>¥ {amount(row.net_amount_cny)}</strong><small>手续费 ¥ {amount(row.fee_cny)}</small></span><time>{row.created_at ? new Date(row.created_at).toLocaleString("zh-CN") : "—"}{["reviewing", "manual_payment_pending"].includes(row.status) && <button disabled={busy === `cancel-${row.id}`} onClick={() => void cancel(row.id)}>取消</button>}</time></article>) : <div className="mobile-inline-empty">暂无提现记录</div>}</section>
  </section>;
}
