"use client";

import { useEffect, useState } from "react";
import { HardDrives, Key } from "@phosphor-icons/react";
import { listSupplierLeases, type ServerLease } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

export function SupplierLeaseWorkspace() {
  const [rows, setRows] = useState<ServerLease[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { listSupplierLeases().then((payload) => setRows(payload.data)).catch((reason) => setError(errorMessage(reason))); }, []);
  return <section className="workspace-page supplier-lease-page"><header className="asset-control-head"><div><p>SUPPLIER / LEASES</p><h1>服务器租约</h1><span>查看租期和 Agent 授权状态。买家连接地址和完整公钥不在商家页面展示。</span></div></header>{error && <div className="commerce-error">{error}</div>}<div className="supplier-lease-list">{rows.length ? rows.map((row) => <article key={row.id}><HardDrives size={23}/><div><small>{row.lease_no} · {row.order_no}</small><strong>{row.server_name}</strong><span>{row.gpu_model} · {row.region}</span></div><div><small>租期</small><strong>{formatDate(row.expires_at)}</strong><span>宽限至 {formatDate(row.grace_expires_at)}</span></div><div><small>买家公钥</small><strong><Key size={14}/>{row.ssh_key.fingerprint.slice(0, 22)}…</strong><span>仅显示指纹</span></div><b className={`status-chip status-chip--${row.status === "active" ? "published" : "archived"}`}>{row.status}</b></article>) : <div className="asset-empty"><HardDrives size={30}/><strong>暂无服务器租约</strong><span>买家购买并完成公钥授权后会显示在这里。</span></div>}</div></section>;
}
