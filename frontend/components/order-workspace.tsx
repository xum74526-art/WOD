"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle,
  ClockCountdown,
  Package,
  Prohibit,
  Receipt,
  RocketLaunch,
  ShieldCheck,
} from "@phosphor-icons/react";
import {
  cancelOrder,
  completeOrder,
  confirmOrder,
  getOrder,
  listOrders,
  markOrderDelivered,
  startOrderDelivery,
  type Order,
  type OrderStatus,
} from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, orderStatusLabel } from "@/lib/commerce-ui";

const filters: Array<[OrderStatus | "", string]> = [
  ["", "全部"],
  ["pending_confirmation", "待确认"],
  ["confirmed", "已确认"],
  ["delivering", "交付中"],
  ["delivered", "待验收"],
  ["completed", "已完成"],
  ["cancelled", "已取消"],
];

const eventLabels: Record<string, string> = {
  created_from_accepted_quote: "买家接受报价并创建订单",
  direct_order_created: "买家从商家商品创建测试订单",
  ssh_access_authorized: "Agent 已下发买家 SSH 公钥",
  ssh_access_queued: "SSH 公钥授权命令已进入队列",
  lease_renewed: "买家已延长服务器租期",
  buyer_confirmed: "买家确认订单",
  supplier_confirmed: "商家确认接单",
  order_cancelled: "订单已取消",
  delivery_started: "商家开始交付",
  delivery_marked_delivered: "商家标记已交付",
  buyer_completed: "买家验收完成",
};

export function OrderWorkspace({ scope }: { scope: "account" | "supplier" }) {
  const supplierView = scope === "supplier";
  const [rows, setRows] = useState<Order[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Order | null>(null);
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadDetail = useCallback(async (id: number) => {
    const order = await getOrder(scope, id);
    setDetail(order);
    setSelectedId(id);
  }, [scope]);

  const load = useCallback(async (nextStatus: OrderStatus | "" = status) => {
    setLoading(true);
    setError("");
    try {
      const result = await listOrders(scope, nextStatus || undefined);
      setRows(result.data);
      const requestedId = typeof window !== "undefined" ? Number(new URLSearchParams(window.location.search).get("order")) : 0;
      const preferredId = requestedId && result.data.some((row) => row.id === requestedId) ? requestedId : selectedId;
      const nextId = result.data.some((row) => row.id === preferredId)
        ? preferredId
        : result.data[0]?.id ?? null;
      if (nextId) await loadDetail(nextId);
      else { setSelectedId(null); setDetail(null); }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [loadDetail, scope, selectedId, status]);

  useEffect(() => { void load(""); }, [scope]);

  async function act(key: string, action: () => Promise<unknown>, message: string) {
    setBusy(key); setError(""); setSuccess("");
    try {
      await action();
      setSuccess(message);
      await load(status);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy("");
    }
  }

  function cancel() {
    if (!detail) return;
    const reason = window.prompt("请输入取消原因（交付开始后不能直接取消）", "双方协商取消");
    if (reason?.trim()) void act("cancel", () => cancelOrder(scope, detail.id, detail.version, reason.trim()), "订单已取消");
  }

  function deliveryNote(promptText: string, action: (note: string) => Promise<unknown>, key: string, message: string) {
    const note = window.prompt(`${promptText}\n请勿填写密码、私钥或其他登录凭据。`, "");
    if (note !== null) void act(key, () => action(note.trim()), message);
  }

  function orderTitle(order: Order) { return order.snapshot.product?.name || order.snapshot.request?.title || "服务器租赁订单"; }
  function orderSpec(order: Order) { return order.snapshot.product?.gpu_model || order.snapshot.request?.gpu_model || "服务器"; }
  function orderReference(order: Order) { return order.snapshot.product?.resource_no || order.snapshot.request?.request_no || order.order_no; }
  function paymentCopy(order: Order) {
    const real = order.snapshot.payment_mode === "pingxx";
    if (order.payment_status !== "paid") return { title: real ? "等待 Ping++ 付款" : "等待本机测试付款", body: real ? "验签回调并主动查单成功后，系统才会授权 SSH。" : "本机开发支付不会产生真实资金变动。" };
    return real ? { title: "Ping++ 付款已验证", body: "支付回调已验签并经主动查单确认，SSH 授权流程已经开始。" } : { title: "本机测试付款已记账", body: "这笔记录只用于本机闭环测试，不代表真实扣款。" };
  }

  return <section className="workspace-page commerce-workspace order-workspace">
    <div className="workspace-page__head commerce-head"><div><p>{supplierView ? "SUPPLIER / RENTAL ORDERS" : "BUYER / ORDERS"}</p><h1>{supplierView ? "租赁订单" : "我的订单"}</h1><span>{supplierView ? "订单记录保留付款、SSH 公钥授权和租期事件。" : "连接命令与续费请前往“我的服务器”。"}</span></div><div className="order-policy"><ShieldCheck size={17} /><span>SSH 私钥不进入平台<br />支付暂为占位 Provider</span></div></div>
    <div className="commerce-tabs">{filters.map(([value, label]) => <button className={status === value ? "active" : ""} key={value || "all"} onClick={() => { setStatus(value); void load(value); }}>{label}</button>)}</div>
    {error && <div className="commerce-error">{error}</div>}{success && <div className="commerce-success">{success}</div>}
    <div className="order-console">
      <aside><header><span>订单队列</span><strong>{rows.length}</strong></header>{loading ? <div className="commerce-loading">正在读取订单…</div> : rows.length === 0 ? <div className="commerce-empty"><Receipt size={25} /><strong>暂无订单</strong><span>买家租用服务器后，订单会显示在这里。</span></div> : <div className="order-queue">{rows.map((order) => <button className={selectedId === order.id ? "active" : ""} key={order.id} onClick={() => void loadDetail(order.id)}><span><small>{order.order_no}</small><strong>{orderTitle(order)}</strong><em>{supplierView ? order.buyer.display_name : order.supplier.company_name || order.supplier.display_name}</em></span><b className={`status-chip status-chip--${order.status}`}>{orderStatusLabel[order.status]}</b></button>)}</div>}</aside>
      <div className="order-dossier">{detail ? <>
        <header><div><p>{detail.order_no} · V{detail.version}</p><h2>{orderTitle(detail)}</h2><span>{orderReference(detail)} · {orderSpec(detail)} × {detail.quantity}</span></div><b className={`status-chip status-chip--${detail.status}`}>{orderStatusLabel[detail.status]}</b></header>
        {detail.order_source === "direct" && <div className={`sandbox-order-banner sandbox-order-banner--${detail.payment_status}`}><ShieldCheck size={18}/><div><strong>服务器租赁订单 · {paymentCopy(detail).title}</strong><span>{paymentCopy(detail).body}</span></div></div>}
        <div className="order-facts"><div><small>{detail.order_source === "direct" ? "订单总额" : "单位报价"}</small><strong>{formatMoney(detail.amount, detail.currency, detail.price_unit)}</strong></div><div><small>{supplierView ? "买家" : "商家"}</small><strong>{supplierView ? detail.buyer.display_name : detail.supplier.company_name || detail.supplier.display_name}</strong></div><div><small>{detail.duration_hours ? "租用周期" : "创建时间"}</small><strong>{detail.duration_hours ? `${detail.duration_hours} 小时` : formatDate(detail.created_at)}</strong></div></div>
        <section className="confirmation-grid"><div className={detail.buyer_confirmed_at ? "done" : ""}><CheckCircle size={20} /><span><small>买家确认</small><strong>{detail.buyer_confirmed_at ? formatDate(detail.buyer_confirmed_at) : "等待确认"}</strong></span></div><div className={detail.supplier_confirmed_at ? "done" : ""}><CheckCircle size={20} /><span><small>商家确认</small><strong>{detail.supplier_confirmed_at ? formatDate(detail.supplier_confirmed_at) : "等待确认"}</strong></span></div></section>
        {detail.delivery_note && <div className="delivery-note"><Package size={18} /><div><strong>最近交付说明</strong><p>{detail.delivery_note}</p></div></div>}
        <section className="order-timeline"><header><ClockCountdown size={18} /><h3>订单时间线</h3></header>{detail.events?.map((event) => <article key={event.id}><i /><div><strong>{eventLabels[event.event_type] || event.event_type}</strong><span>{formatDate(event.created_at)} · {event.actor_role}</span>{event.payload.note && <p>{event.payload.note}</p>}</div></article>)}</section>
        <footer className="order-actions">
          {detail.available_actions.includes("confirm") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void act("confirm", () => confirmOrder(scope, detail.id, detail.version, "确认资源与交付计划"), "订单已确认") }><CheckCircle size={16} />{busy === "confirm" ? "确认中…" : "确认接单"}</button>}
          {detail.available_actions.includes("start_delivery") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => deliveryNote("填写交付进度说明（可选）", (note) => startOrderDelivery(detail.id, detail.version, note), "start", "订单已进入交付中") }><RocketLaunch size={16} />开始交付</button>}
          {detail.available_actions.includes("mark_delivered") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => deliveryNote("填写交付完成说明（可选）", (note) => markOrderDelivered(detail.id, detail.version, note), "deliver", "已通知买家验收") }><Package size={16} />标记已交付</button>}
          {detail.available_actions.includes("complete") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void act("complete", () => completeOrder(detail.id, detail.version, "买家确认验收通过"), "订单已完成") }><CheckCircle size={16} />确认验收完成</button>}
          {detail.available_actions.includes("cancel") && <button className="commerce-danger" disabled={Boolean(busy)} onClick={cancel}><Prohibit size={16} />取消订单</button>}
        </footer>
      </> : <div className="commerce-empty"><Receipt size={28} /><strong>选择一笔订单</strong><span>这里会展示确认、交付与事件记录。</span></div>}</div>
    </div>
  </section>;
}
