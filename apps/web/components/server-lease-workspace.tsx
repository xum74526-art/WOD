"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CheckCircle, ClockCountdown, Copy, HardDrives, Key, WarningCircle } from "@phosphor-icons/react";
import { listServerLeases, renewServerLease, type ServerLease } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { reconcilePayment } from "@/lib/integration-api";

const labels: Record<ServerLease["status"], string> = {
  pending_authorization: "正在授权",
  active: "使用中",
  grace: "续费宽限期",
  expired: "已到期",
  revoked: "已撤销",
  failed: "开通失败",
};

export function ServerLeaseWorkspace() {
  const [rows, setRows] = useState<ServerLease[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [renewHours, setRenewHours] = useState(24);
  const [paymentChannel, setPaymentChannel] = useState("alipay_pc_direct");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      const payload = await listServerLeases();
      setRows(payload.data);
      setSelectedId((current) => payload.data.some((row) => row.id === current) ? current : payload.data[0]?.id || 0);
    } catch (reason) { setError(errorMessage(reason)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const paymentNo = query.get("payment");
    if (!paymentNo || query.get("result") !== "success") return;
    let cancelled = false;
    setBusy(true);
    void reconcilePayment(paymentNo)
      .then(async () => {
        if (cancelled) return;
        await load();
        window.history.replaceState({}, "", window.location.pathname);
      })
      .catch((reason) => { if (!cancelled) setError(errorMessage(reason)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [load]);
  const selected = useMemo(() => rows.find((row) => row.id === selectedId) || null, [rows, selectedId]);
  const activeCount = rows.filter((row) => row.status === "active").length;
  const graceCount = rows.filter((row) => row.status === "grace").length;

  async function copyCommand() {
    if (!selected?.connection) return;
    await navigator.clipboard.writeText(selected.connection.ssh_command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  async function renew() {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const renewed = await renewServerLease(selected.id, selected.version, renewHours, paymentChannel);
      if (renewed.payment?.checkout_url) {
        window.location.assign(renewed.payment.checkout_url);
        return;
      }
      await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return <section className="workspace-page asset-control-room">
    <header className="asset-control-head"><div><p>BUYER / SERVER LEASES</p><h1>我的服务器</h1><span>查看 SSH 连接信息、租期和续费状态。平台不会保存你的私钥。</span></div><Link href="/market"><HardDrives size={17}/>租用服务器</Link></header>
    <div className="asset-signal-strip"><div><small>有效租约</small><span>ACTIVE</span><strong>{activeCount}</strong></div><div><small>等待续费</small><span>GRACE</span><strong>{graceCount}</strong></div><div><small>全部租约</small><span>TOTAL</span><strong>{rows.length}</strong></div></div>
    {error && <div className="commerce-error">{error}</div>}
    {!rows.length ? <div className="asset-empty"><HardDrives size={31}/><strong>还没有服务器租约</strong><span>先添加 SSH 公钥，再从算力市场购买。</span><Link href="/market">浏览服务器</Link></div> : <div className="asset-console">
      <aside><header><span>LEASE DIRECTORY</span><b>{rows.length}</b></header>{rows.map((row) => <button type="button" className={selectedId === row.id ? "active" : ""} onClick={() => setSelectedId(row.id)} key={row.id}><i className={row.status === "active" ? "running" : ""}/><span><small>{row.lease_no}</small><strong>{row.server_name}</strong><em>{row.gpu_model} · {row.region}</em></span><b>{labels[row.status]}</b></button>)}</aside>
      {selected && <article className="asset-terminal"><header><div><HardDrives size={25}/><h2>{selected.server_name}</h2><p>{selected.lease_no} · {selected.order_no}</p></div><span className={`asset-live-mark ${selected.status !== "active" ? "stopped" : ""}`}>{labels[selected.status]}</span></header>
        <div className="asset-runtime-line"><span><i className={selected.status === "active" ? "running" : ""}/>{selected.status === "active" ? "SSH 访问已授权" : selected.status === "grace" ? "访问已停止，数据暂时保留" : "当前没有有效访问权限"}</span><small>SSH KEY · {selected.ssh_key.name}</small></div>
        <dl><div><dt>开始时间</dt><dd>{formatDate(selected.starts_at)}</dd></div><div><dt>到期时间</dt><dd>{formatDate(selected.expires_at)}</dd></div><div><dt>续费截止</dt><dd>{formatDate(selected.grace_expires_at)}</dd></div><div><dt>登录公钥</dt><dd>{selected.ssh_key.fingerprint.slice(0, 24)}…</dd></div><div><dt>已购时长</dt><dd>{selected.duration_hours} 小时</dd></div><div><dt>累计金额</dt><dd>{selected.amount} {selected.currency}</dd></div></dl>
        {selected.connection ? <div className="asset-command-deck"><div><Key size={22}/><span><strong>{selected.connection.ssh_command}</strong><small>在 Mac 终端中复制并执行此命令</small></span></div><button type="button" onClick={() => void copyCommand()}><Copy size={16}/>{copied ? "已复制" : "复制命令"}</button></div> : <div className="asset-ended">{selected.status === "grace" ? <WarningCircle size={21}/> : <CheckCircle size={21}/>}<span><strong>{selected.status === "grace" ? "SSH 权限已按时撤销" : "此租约当前不可连接"}</strong><small>{selected.status === "grace" ? "宽限期内续费会重新下发原公钥，服务器数据暂不清理。" : selected.failure_reason || "如有疑问，请从订单发起争议。"}</small></span></div>}
        {selected.renewable && <div className="lease-renew-panel"><div><ClockCountdown size={19}/><span><strong>延长租期</strong><small>宽限期内续费会恢复 SSH 权限</small></span></div><select value={renewHours} onChange={(event) => setRenewHours(Number(event.target.value))}><option value={1}>1 小时</option><option value={6}>6 小时</option><option value={24}>24 小时</option><option value={168}>7 天</option><option value={720}>30 天</option></select><select aria-label="续费支付方式" value={paymentChannel} onChange={(event) => setPaymentChannel(event.target.value)}><option value="alipay_pc_direct">支付宝</option><option value="wx_wap">微信 H5</option><option value="upacp_pc">银联</option></select><button type="button" disabled={busy} onClick={() => void renew()}>{busy ? "续费中…" : selected.payment_mode === "pingxx" ? "前往支付续费" : "测试续费"}</button></div>}
        <footer><Link href={`/account/orders?order=${selected.order_id}`}><ClockCountdown size={15}/>查看订单记录</Link><Link href="/account/ssh-keys"><Key size={15}/>管理 SSH 公钥</Link></footer>
      </article>}
    </div>}
  </section>;
}
