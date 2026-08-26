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
  ShieldWarning,
} from "@phosphor-icons/react";
import {
  cancelOrder,
  completeOrder,
  confirmOrder,
  disputeOrder,
  getOrder,
  listOrders,
  markOrderDelivered,
  getPublicProduct,
  renewOrder,
  startOrderDelivery,
  type Order,
  type OrderStatus,
} from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, orderStatusLabel } from "@/lib/commerce-ui";

const filters: Array<[OrderStatus | "", string]> = [
  ["", "全部"],
  ["paid", "待交付"],
  ["delivering", "待验收"],
  ["disputed", "争议处理中"],
  ["completed", "已完成"],
  ["canceled", "已取消"],
];

const eventLabels: Record<string, string> = {
  created_from_accepted_quote: "买家接受报价并创建订单",
  direct_order_created: "买家从商家商品创建订单",
  ssh_access_authorized: "系统已下发买家 SSH 公钥",
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
  const [renewalHours, setRenewalHours] = useState<number[]>([24]);
  const [renewalHour, setRenewalHour] = useState(24);

  const loadDetail = useCallback(async (id: number) => {
    const order = await getOrder(scope, id);
    setDetail(order);
    setSelectedId(id);
    if (scope === "account" && order.product_id && order.available_actions.includes("renew")) {
      try {
        const product = (await getPublicProduct(order.product_id)).data;
        const hours = product.purchase_hour_options?.length ? product.purchase_hour_options : [24];
        setRenewalHours(hours);
        setRenewalHour(hours.includes(24) ? 24 : hours[0]);
      } catch { setRenewalHours([24]); setRenewalHour(24); }
    }
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

  function dispute() {
    if (!detail) return;
    const reason = window.prompt("请说明 SSH 无法连接、配置不符或其他交付问题（至少 5 个字）", "");
    if (reason === null) return;
    if (reason.trim().length < 5) { setError("争议说明至少需要 5 个字"); return; }
    void act("dispute", () => disputeOrder(detail.id, reason.trim()), "争议已提交，订单卡时将继续冻结等待平台处理");
  }

  function deliveryNote(promptText: string, action: (note: string) => Promise<unknown>, key: string, message: string, sshDelivery = false) {
    const note = window.prompt(sshDelivery ? `${promptText}\n示例：ssh gpu-user@203.0.113.10 -p 2222\n请勿填写密码或私钥。` : `${promptText}\n请勿填写密码或私钥。`, "");
    if (note !== null) void act(key, () => action(note.trim()), message);
  }

  function orderTitle(order: Order) { return order.snapshot.product?.name || order.snapshot.request?.title || "服务器租赁订单"; }
  function orderSpec(order: Order) { return order.snapshot.product?.gpu_model || order.snapshot.request?.gpu_model || "服务器"; }
  function orderReference(order: Order) { return order.snapshot.product?.resource_no || order.snapshot.request?.request_no || order.order_no; }
  function paymentCopy(order: Order) {
    if (order.payment_status !== "paid") return { title: "等待统一钱包处理", body: "余额与冻结金额以统一账本为准。" };
    return { title: "统一钱包已冻结订单金额", body: "商家交付并经买家确认后，订单状态会写回同一数据库。" };
  }
  function sellerCopy(order: Order) {
    return order.seller_name || order.supplier.company_name || order.supplier.display_name;
  }
  function fulfillmentCopy(order: Order) {
    return order.fulfillment_mode === "platform_manual" ? "平台人工交付 SSH" : "商家人工交付 SSH";
  }
  function fulfillmentStatusCopy(order: Order) {
    return ({
      pending_ssh: "等待卖方提交 SSH",
      awaiting_confirmation: "SSH 已提交，等待买家验收",
      active: "买家已验收，服务生效",
      under_review: "争议处理中",
      canceled: "订单已取消",
    } as Record<string, string>)[order.fulfillment_status || ""] || "以订单状态为准";
  }
  function durationCopy(order: Order) {
    if (order.purchase_hours) return `${order.purchase_hours} 小时`;
    if (order.cycle_days) return `${order.cycle_days} 天（历史订单）`;
    return order.duration_hours ? `${order.duration_hours} 小时` : "";
  }
  function deadlineCopy(order: Order) {
    if (order.dispute_due_at) return { title: "争议处理截止", value: order.dispute_due_at };
    if (order.confirmation_due_at) return { title: "买家验收截止", value: order.confirmation_due_at };
    if (order.delivery_due_at) return { title: "商家交付截止", value: order.delivery_due_at };
    return null;
  }

  return <section className="workspace-page commerce-workspace order-workspace">
    <div className="workspace-page__head commerce-head"><div><p>{supplierView ? "SUPPLIER / ORDERS" : "BUYER / ORDERS"}</p><h1>{supplierView ? "接单与交付" : "我的订单"}</h1><span>{supplierView ? "已付款订单在这里提交有效 SSH，买家验收后完成结算。" : "查看卖方、履约方式、SSH 交付、验收与争议状态。"}</span></div><div className="order-policy"><ShieldCheck size={17} /><span>统一订单账本<br />SSH 私钥不进入平台</span></div></div>
    <div className="commerce-tabs">{filters.map(([value, label]) => <button className={status === value ? "active" : ""} key={value || "all"} onClick={() => { setStatus(value); void load(value); }}>{label}</button>)}</div>
    {error && <div className="commerce-error">{error}</div>}{success && <div className="commerce-success">{success}</div>}
    <div className="order-console">
      <aside><header><span>订单队列</span><strong>{rows.length}</strong></header>{loading ? <div className="commerce-loading">正在读取订单…</div> : rows.length === 0 ? <div className="commerce-empty"><Receipt size={25} /><strong>暂无订单</strong><span>买家租用服务器后，订单会显示在这里。</span></div> : <div className="order-queue">{rows.map((order) => <button className={selectedId === order.id ? "active" : ""} key={order.id} onClick={() => void loadDetail(order.id)}><span><small>{order.order_no}</small><strong>{orderTitle(order)}</strong><em>{supplierView ? order.buyer.display_name : order.supplier.company_name || order.supplier.display_name}</em></span><b className={`status-chip status-chip--${order.status}`}>{orderStatusLabel[order.status]}</b></button>)}</div>}</aside>
      <div className="order-dossier">{detail ? <>
        <header><div><p>{detail.order_no} · V{detail.version}</p><h2>{orderTitle(detail)}</h2><span>{orderReference(detail)} · {orderSpec(detail)} × {detail.quantity}</span></div><b className={`status-chip status-chip--${detail.status}`}>{orderStatusLabel[detail.status]}</b></header>
          {detail.order_source === "direct" && <div className={`sandbox-order-banner sandbox-order-banner--${detail.payment_status}`}><ShieldCheck size={18}/><div><strong>{detail.seller_type === "kai_self_operated" ? "KAI 自营订单" : "商家订单"} · {paymentCopy(detail).title}</strong><span>卖方：{sellerCopy(detail)} · {fulfillmentCopy(detail)}。{paymentCopy(detail).body}</span></div></div>}
        <div className="order-facts"><div><small>{detail.order_source === "direct" ? "订单总额" : "单位报价"}</small><strong>{formatMoney(detail.amount, detail.currency, detail.price_unit)}</strong></div><div><small>{supplierView ? "买家" : "卖方"}</small><strong>{supplierView ? detail.buyer.display_name : detail.supplier.company_name || detail.supplier.display_name}</strong></div><div><small>{durationCopy(detail) ? "租用周期" : "创建时间"}</small><strong>{durationCopy(detail) || formatDate(detail.created_at)}</strong></div></div>
        <section className="confirmation-grid"><div className={detail.delivered_at ? "done" : ""}><Package size={20} /><span><small>卖方提交交付</small><strong>{detail.delivered_at ? formatDate(detail.delivered_at) : "等待有效 SSH"}</strong></span></div><div className={detail.confirmed_at ? "done" : ""}><CheckCircle size={20} /><span><small>买家验收</small><strong>{detail.confirmed_at ? formatDate(detail.confirmed_at) : "等待验收"}</strong></span></div></section>
        <div className="order-fulfillment-status"><Package size={18}/><span><small>当前履约状态</small><strong>{fulfillmentStatusCopy(detail)}</strong></span><em>{fulfillmentCopy(detail)}</em></div>
        {detail.delivery_note && <div className="delivery-note"><Package size={18} /><div><strong>最近交付说明</strong><p>{detail.delivery_note}</p></div></div>}
        {deadlineCopy(detail) && <div className="delivery-note"><ClockCountdown size={18} /><div><strong>{deadlineCopy(detail)?.title}</strong><p>{formatDate(deadlineCopy(detail)?.value)}</p></div></div>}
        {detail.status === "disputed" && detail.dispute_reason && <div className="delivery-note"><ShieldWarning size={18} /><div><strong>争议说明</strong><p>{detail.dispute_reason}</p></div></div>}
        {detail.available_actions.includes("renew") && <section className="order-renewal"><header><ClockCountdown size={18}/><div><small>RENEWAL</small><h3>订单续费</h3></div><span>{detail.remaining_hours ?? 0} 小时后到期</span></header><div>{renewalHours.map((hours) => <button type="button" className={renewalHour === hours ? "active" : ""} key={hours} onClick={() => setRenewalHour(hours)}>{hours} 小时</button>)}</div><button className="commerce-primary" disabled={Boolean(busy)} onClick={() => { if (window.confirm(`确认使用统一钱包续费 ${renewalHour} 小时？`)) void act("renew", () => renewOrder(detail.id, renewalHour), `已续费 ${renewalHour} 小时`); }}>{busy === "renew" ? "续费中…" : "确认续费"}</button></section>}
        {detail.events && detail.events.length > 0 && <section className="order-timeline"><header><ClockCountdown size={18} /><h3>订单时间线</h3></header>{detail.events.map((event) => <article key={event.id}><i /><div><strong>{eventLabels[event.event_type] || event.event_type}</strong><span>{formatDate(event.created_at)} · {event.actor_role}</span>{event.payload.note && <p>{event.payload.note}</p>}</div></article>)}</section>}
        <footer className="order-actions">
          {detail.available_actions.includes("confirm") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void act("confirm", () => confirmOrder(scope, detail.id, detail.version, "确认资源与交付计划"), "订单已确认") }><CheckCircle size={16} />{busy === "confirm" ? "确认中…" : "确认接单"}</button>}
          {detail.available_actions.includes("start_delivery") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => deliveryNote("填写交付进度说明（可选）", (note) => startOrderDelivery(detail.id, detail.version, note), "start", "订单已进入交付中") }><RocketLaunch size={16} />开始交付</button>}
          {detail.available_actions.includes("mark_delivered") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => deliveryNote("填写有效 SSH 连接信息", (note) => markOrderDelivered(detail.id, detail.version, note), "deliver", "已提交 SSH 交付，等待买家确认", true) }><Package size={16} />提交 SSH 交付</button>}
          {detail.available_actions.includes("complete") && <button className="commerce-primary" disabled={Boolean(busy)} onClick={() => void act("complete", () => completeOrder(detail.id, detail.version, "买家确认验收通过"), "订单已完成") }><CheckCircle size={16} />确认验收完成</button>}
          {detail.available_actions.includes("dispute") && <button className="commerce-danger" disabled={Boolean(busy)} onClick={dispute}><ShieldWarning size={16} />{busy === "dispute" ? "提交中…" : "发起争议"}</button>}
          {detail.available_actions.includes("cancel") && <button className="commerce-danger" disabled={Boolean(busy)} onClick={cancel}><Prohibit size={16} />取消订单</button>}
        </footer>
      </> : <div className="commerce-empty"><Receipt size={28} /><strong>选择一笔订单</strong><span>这里会展示确认、交付与事件记录。</span></div>}</div>
    </div>
  </section>;
}
