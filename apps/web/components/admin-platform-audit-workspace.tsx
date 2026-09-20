"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Receipt, Users, Wallet } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import { getAdminOverview, listAdminOrders, listAdminRechargeOrders, listAdminUsers, type AdminOrderItem, type AdminOverview, type AdminRechargeItem, type AdminUserItem } from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import type { AuditPlatform } from "@/lib/mobile-finance-api";

type View = "users" | "orders" | "recharges";
const countLabels = { users: "用户", orders: "订单", recharge_orders: "充值", verifications: "实名", bank_cards: "银行卡", withdrawals: "提现" } as const;

export function AdminPlatformAuditWorkspace() {
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [view, setView] = useState<View>("users");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [orders, setOrders] = useState<AdminOrderItem[]>([]);
  const [recharges, setRecharges] = useState<AdminRechargeItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const source = platform || undefined;
    try {
      const [summary, userPage, orderPage, rechargePage] = await Promise.all([
        getAdminOverview(source),
        listAdminUsers({ platform: source, keyword: view === "users" ? search : undefined }),
        listAdminOrders({ platform: source, status: view === "orders" ? status : undefined, orderNo: view === "orders" ? search : undefined }),
        listAdminRechargeOrders({ platform: source, status: view === "recharges" ? status : undefined, orderNo: view === "recharges" ? search : undefined }),
      ]);
      setOverview(summary); setUsers(userPage.items); setOrders(orderPage.items); setRecharges(rechargePage.items);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, [platform, search, status, view]);

  useEffect(() => { void load(); }, [load]);
  function submit(event: FormEvent) { event.preventDefault(); void load(); }

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / PLATFORM DATA</p><h1>端口数据</h1><span>三端共享业务数据，管理员按数据产生端口查看来源与后续修改来源。</span></div>
    {overview && <div className="commerce-stat-grid">{Object.entries(overview.counts).map(([key, value]) => <article key={key}><small>{countLabels[key as keyof typeof countLabels]}</small><strong>{value}</strong><span>{platform ? platformLabel(platform) : "全部端口"}</span></article>)}</div>}
    <div className="commerce-tabs"><button className={view === "users" ? "active" : ""} onClick={() => { setView("users"); setSearch(""); setStatus(""); }}><Users size={17}/>用户</button><button className={view === "orders" ? "active" : ""} onClick={() => { setView("orders"); setSearch(""); setStatus(""); }}><Receipt size={17}/>订单</button><button className={view === "recharges" ? "active" : ""} onClick={() => { setView("recharges"); setSearch(""); setStatus(""); }}><Wallet size={17}/>充值</button></div>
    <form className="refund-toolbar" onSubmit={submit}><AdminPlatformFilter value={platform} onChange={setPlatform}/><input aria-label={view === "users" ? "搜索用户名或手机号" : "搜索订单号"} placeholder={view === "users" ? "用户名或手机号" : "订单号"} value={search} onChange={(event) => setSearch(event.target.value)}/>{view !== "users" && <input aria-label="状态筛选" placeholder="状态" value={status} onChange={(event) => setStatus(event.target.value)}/>}<button disabled={loading}><ArrowClockwise size={15}/>{loading ? "加载中" : "查询"}</button></form>
    {error && <div className="commerce-error">{error}</div>}
    {view === "users" && <div className="admin-settlement-list">{users.length ? users.map((row) => <article key={row.id}><header><div><small>用户 #{row.id} · {platformLabel(row.created_platform)}</small><h2>{row.username}</h2><span>{formatDate(row.created_at)}</span></div><b className="status-chip status-chip--published">{row.role}</b></header><p>{row.phone_masked || "未绑定手机号"} · KAI 身份{row.kai_identity_bound ? "已绑定" : "未绑定"} · 商家状态 {row.supplier_status}</p></article>) : <div className="commerce-empty"><Users size={25}/><strong>没有符合条件的用户</strong></div>}</div>}
    {view === "orders" && <div className="admin-settlement-list">{orders.length ? orders.map((row) => <article key={row.id}><header><div><small>{row.order_no} · 创建 {platformLabel(row.created_platform)} · 修改 {platformLabel(row.last_modified_platform)}</small><h2>{row.product.name || row.product.gpu_model || `商品 #${row.product.id}`}</h2><span>{row.user.username || `用户 #${row.user.id}`} · {formatDate(row.created_at)}</span></div><strong>{row.amount_card_hours} 卡时</strong><b className="status-chip status-chip--pending_review">{row.status}</b></header><p>{row.quantity} 台 · {row.purchase_hours ? `${row.purchase_hours} 小时` : row.cycle_days ? `${row.cycle_days} 天（历史）` : "时长未记录"}</p></article>) : <div className="commerce-empty"><Receipt size={25}/><strong>没有符合条件的订单</strong></div>}</div>}
    {view === "recharges" && <div className="admin-settlement-list">{recharges.length ? recharges.map((row) => <article key={row.id}><header><div><small>{row.order_no} · 创建 {platformLabel(row.created_platform)} · 修改 {platformLabel(row.last_modified_platform)}</small><h2>{row.provider} / {row.channel}</h2><span>{row.user.username || `用户 #${row.user.id}`} · {formatDate(row.created_at)}</span></div><strong>¥ {row.amount_cny.toFixed(2)}</strong><b className="status-chip status-chip--pending_review">{row.status}</b></header><p>{row.card_hours} 卡时 · 汇率 {row.card_hour_rate}</p></article>) : <div className="commerce-empty"><Wallet size={25}/><strong>没有符合条件的充值订单</strong></div>}</div>}
  </section>;
}
