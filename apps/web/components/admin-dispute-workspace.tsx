"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Gavel, X } from "@phosphor-icons/react";
import { listAdminOrders, resolveAdminOrderDispute, type AdminOrderItem } from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { useI18n } from "@/components/locale-root";

const DISPUTE_PAGE_SIZE = 30;

function sellerName(order: AdminOrderItem) {
  return order.seller_name || (order.seller_type === "kai_self_operated" ? "KAI星算自营" : "第三方商家");
}

function fulfillmentName(order: AdminOrderItem) {
  return order.fulfillment_mode === "platform_manual" ? "平台人工交付" : "商家人工交付";
}

function mergeOrders(current: AdminOrderItem[], incoming: AdminOrderItem[]) {
  const orders = new Map(current.map((row) => [row.id, row]));
  incoming.forEach((row) => orders.set(row.id, row));
  return Array.from(orders.values());
}

export function AdminDisputeWorkspace() {
  const { t, formatLedgerMoney } = useI18n();
  const [rows, setRows] = useState<AdminOrderItem[]>([]);
  const [selected, setSelected] = useState<AdminOrderItem | null>(null);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [resolution, setResolution] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingPage, setLoadingPage] = useState(false);

  const load = useCallback(async (nextPage = 1, append = false) => {
    setError("");
    setLoadingPage(true);
    try {
      const result = await listAdminOrders({ status: "disputed", page: nextPage, pageSize: DISPUTE_PAGE_SIZE });
      setRows((current) => append ? mergeOrders(current, result.items) : mergeOrders([], result.items));
      setSelected((current) => append
        ? current ?? result.items[0] ?? null
        : result.items.find((row) => row.id === current?.id) ?? result.items[0] ?? null);
      setPage(result.page);
      setTotal(result.total);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadingPage(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function decide(action: "refund" | "release") {
    if (!selected) return;
    const note = resolution.trim();
    if (!note) { setError("处理争议前请填写证据与处理结论"); return; }
    const actionLabel = action === "refund"
      ? t("admin.dispute.action.refund", "退回买家冻结金额")
      : t("admin.dispute.action.release", "放行订单资金并继续商家结算");
    if (!window.confirm(t("admin.dispute.confirm", "确认“{action}”？该动作会直接写入真实订单账本。", { action: actionLabel }))) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await resolveAdminOrderDispute(selected.id, { action, note });
      setResolution("");
      setSuccess(t("admin.dispute.success", "订单 {orderNo} 已处理：{action}", { orderNo: selected.order_no, action: actionLabel }));
      await load(1, false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const hasMore = page * DISPUTE_PAGE_SIZE < total;
  const snapshot = selected?.product_snapshot;
  const sshFingerprint = selected?.ssh_fingerprint || selected?.ssh_info_fingerprint;
  const snapshotName = snapshot?.name || snapshot?.product_name;
  const snapshotRegion = snapshot?.region_name || snapshot?.region || snapshot?.city || snapshot?.region_code;
  const snapshotUnitPrice = snapshot?.unit_price_card_hours ?? snapshot?.confirmed_unit_price_card_hours;
  const hasDeliveryEvidence = Boolean(selected && (
    selected.delivered_at
    || selected.confirmation_due_at
    || selected.ssh_info_present != null
    || sshFingerprint
  ));

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / DISPUTE RESOLUTION</p><h1>订单争议仲裁</h1><span>这里只显示真实的争议订单；退款会退回买家冻结金额，放行会完成订单资金结算。</span></div>
    <div className="review-console admin-dispute-console">
      <aside>
        <form><label className="admin-filter-label"><Gavel size={15}/><span>争议状态</span></label><select aria-label="争议状态" value="disputed" disabled><option value="disputed">待仲裁</option></select></form>
        {rows.length === 0
          ? <div className="commerce-empty"><Gavel size={24}/><strong>{loadingPage ? "正在读取待仲裁订单…" : "当前没有待仲裁订单"}</strong></div>
          : <div className="review-queue">{rows.map((row) => <button type="button" className={selected?.id === row.id ? "active" : ""} onClick={() => { setSelected(row); setResolution(""); setError(""); }} key={row.id}><span><small>{row.order_no} · {formatDate(row.disputed_at || row.updated_at || row.created_at)}</small><strong>{row.product.name || row.product.gpu_model || "算力订单"}</strong><em>{row.user.username || `用户 ${row.user.id}`} · {sellerName(row)}</em></span><b className="status-chip status-chip--disputed">待仲裁</b></button>)}</div>}
        {hasMore && <button className="admin-dispute-load-more" type="button" disabled={loadingPage} onClick={() => void load(page + 1, true)}>{loadingPage ? "正在加载…" : t("admin.common.loadMore", "加载更多（已显示 {shown} / {total}）", { shown: rows.length, total })}</button>}
      </aside>
      <article className="review-dossier">
        {selected ? <>
          <header><div><p>{selected.order_no} / ORDER #{selected.id}</p><h2>{selected.product.name || selected.product.gpu_model || "算力订单争议"}</h2></div><span className="status-chip status-chip--disputed">待仲裁</span></header>
          <section><h3>买家提交的问题</h3><p data-i18n-skip={Boolean(selected.dispute_reason) || undefined}>{selected.dispute_reason || "买家未补充文字说明，请结合订单交付记录核验。"}</p></section>
          <dl>
            <div><dt>买家</dt><dd>{selected.user.username || `用户 ${selected.user.id}`}</dd></div>
            <div><dt>卖方</dt><dd>{sellerName(selected)} · {fulfillmentName(selected)}</dd></div>
            <div><dt>订单金额</dt><dd>{formatLedgerMoney(selected.amount_card_hours)}</dd></div>
            <div><dt>发起时间</dt><dd>{formatDate(selected.disputed_at || selected.created_at)}</dd></div>
            {selected.dispute_due_at && <div><dt>处理截止</dt><dd>{formatDate(selected.dispute_due_at)}</dd></div>}
          </dl>
          {hasDeliveryEvidence && <section><h3>安全交付证据</h3><p>
            {selected.delivered_at && <>提交交付：{formatDate(selected.delivered_at)}<br/></>}
            {selected.confirmation_due_at && <>买家确认截止：{formatDate(selected.confirmation_due_at)}<br/></>}
            {selected.ssh_info_present != null && <>SSH 交付资料：{selected.ssh_info_present ? "已提交（敏感连接内容不在此页展示）" : "未提交"}<br/></>}
            {sshFingerprint && <>SSH 交付记录指纹：{sshFingerprint}</>}
          </p></section>}
          {snapshot && <section><h3>下单商品快照</h3><p>
            {snapshotName && <>商品：{snapshotName}<br/></>}
            {snapshot.gpu_model && <>GPU：{snapshot.gpu_model}{snapshot.memory ? ` / ${snapshot.memory}` : ""}<br/></>}
            {snapshotRegion && <>区域：{snapshotRegion}<br/></>}
            <>{t("admin.dispute.quantity", "数量：{quantity} 台", { quantity: snapshot.quantity ?? selected.quantity })}<br/></>
            {(snapshot.purchase_hours ?? selected.purchase_hours) != null && <>购买时长：{snapshot.purchase_hours ?? selected.purchase_hours} 小时<br/></>}
            {snapshotUnitPrice != null && <>下单单价：{formatLedgerMoney(snapshotUnitPrice)} / GPU·小时</>}
          </p></section>}
          {selected.dispute_resolution_note && <section><h3>已有处理记录</h3><p data-i18n-skip>{selected.dispute_resolution_note}</p></section>}
          <footer><label><span>证据与处理结论</span><textarea rows={5} maxLength={2000} value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="说明 SSH 交付证据、资源参数核验结果，以及退款或放行的理由" /></label><div><button disabled={busy} onClick={() => void decide("release")}><Check size={15}/>交付有效 · 放行结算</button><button disabled={busy} onClick={() => void decide("refund")} className="commerce-danger"><X size={15}/>买家申诉成立 · 退回冻结金额</button></div></footer>
        </> : <div className="commerce-empty"><Gavel size={25}/><strong>选择一笔争议订单查看详情</strong></div>}
      </article>
    </div>
    {error && <div className="commerce-error">{error}</div>}{success && <div className="commerce-success">{success}</div>}
  </section>;
}
