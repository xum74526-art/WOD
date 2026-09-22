"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowClockwise, ClockCounterClockwise, EnvelopeSimple, LockKey, LockOpen, Receipt, Trash, Users, Wallet } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import {
  getAdminOverview,
  listAdminOrders,
  listAdminRechargeOrders,
  listAdminUserActions,
  listAdminUsers,
  manageAdminUser,
  type AdminOrderItem,
  type AdminOverview,
  type AdminRechargeItem,
  type AdminUserActionKind,
  type AdminUserAction,
  type AdminUserItem,
} from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import type { AuditPlatform } from "@/lib/mobile-finance-api";

type View = "users" | "orders" | "recharges";
type PendingUserAction = { user: AdminUserItem; action: AdminUserActionKind };

const countLabels = { users: "用户", orders: "订单", recharge_orders: "充值", verifications: "实名", bank_cards: "银行卡", withdrawals: "提现" } as const;
const statusLabels: Record<string, string> = { active: "正常", suspended: "已冻结", deleting: "注销处理中", deleted: "已注销" };
const actionLabels: Record<AdminUserActionKind, string> = {
  send_password_reset: "发送重置邮件",
  freeze: "冻结账号",
  unfreeze: "解除冻结",
  delete: "注销账号",
};

function actionDescription(action: AdminUserActionKind) {
  if (action === "send_password_reset") return "系统只会向用户已验证的找回邮箱发送一次性链接，管理员看不到原密码、完整邮箱或重置令牌。";
  if (action === "freeze") return "立即使全部登录会话和找回凭证失效，并阻止该账号继续登录；订单、资金和审计记录不会被修改。";
  if (action === "unfreeze") return "恢复账号登录能力。旧会话不会恢复，用户需要重新登录。";
  return "仅在没有未结订单、资金、退款、提现或争议时进入不可逆注销流程；依法应保留的账务及审计记录不会物理删除。";
}

export function AdminPlatformAuditWorkspace() {
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [view, setView] = useState<View>("users");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [userPage, setUserPage] = useState(1);
  const [userTotal, setUserTotal] = useState(0);
  const [orders, setOrders] = useState<AdminOrderItem[]>([]);
  const [recharges, setRecharges] = useState<AdminRechargeItem[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingUserAction | null>(null);
  const [actionReason, setActionReason] = useState("");
  const [confirmUsername, setConfirmUsername] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [historyUserId, setHistoryUserId] = useState<number | null>(null);
  const [historyRows, setHistoryRows] = useState<AdminUserAction[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const source = platform || undefined;
    try {
      const [summary, userPageResult, orderPage, rechargePage] = await Promise.all([
        getAdminOverview(source),
        listAdminUsers({ platform: source, keyword: view === "users" ? search : undefined, status: view === "users" ? status : undefined, page: userPage, pageSize: 20 }),
        listAdminOrders({ platform: source, status: view === "orders" ? status : undefined, orderNo: view === "orders" ? search : undefined }),
        listAdminRechargeOrders({ platform: source, status: view === "recharges" ? status : undefined, orderNo: view === "recharges" ? search : undefined }),
      ]);
      setOverview(summary); setUsers(userPageResult.items); setUserTotal(userPageResult.total); setOrders(orderPage.items); setRecharges(rechargePage.items);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, [platform, search, status, userPage, view]);

  useEffect(() => { void load(); }, [load]);
  function submit(event: FormEvent) { event.preventDefault(); void load(); }

  function beginUserAction(user: AdminUserItem, action: AdminUserActionKind) {
    setPendingAction({ user, action });
    setActionReason("");
    setConfirmUsername("");
    setError("");
    setNotice("");
  }

  async function submitUserAction(event: FormEvent) {
    event.preventDefault();
    if (!pendingAction) return;
    setActionBusy(true); setError(""); setNotice("");
    try {
      await manageAdminUser(pendingAction.user.id, {
        action: pendingAction.action,
        client_request_id: `admin-account-${crypto.randomUUID()}`,
        reason: actionReason,
        confirm_username: pendingAction.action === "delete" ? confirmUsername : undefined,
      });
      setNotice(`${pendingAction.user.username}：${actionLabels[pendingAction.action]}已提交。`);
      setPendingAction(null); setActionReason(""); setConfirmUsername("");
      await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setActionBusy(false); }
  }

  async function toggleUserHistory(user: AdminUserItem) {
    if (historyUserId === user.id) {
      setHistoryUserId(null); setHistoryRows([]);
      return;
    }
    setHistoryBusy(true); setError("");
    try {
      const result = await listAdminUserActions(user.id, { page: 1, pageSize: 20 });
      setHistoryUserId(user.id); setHistoryRows(result.items);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setHistoryBusy(false); }
  }

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / PLATFORM DATA</p><h1>端口数据</h1><span>三端共享业务数据，管理员按数据产生端口查看来源与后续修改来源。</span></div>
    {overview && <div className="commerce-stat-grid">{Object.entries(overview.counts).map(([key, value]) => <article key={key}><small>{countLabels[key as keyof typeof countLabels]}</small><strong>{value}</strong><span>{platform ? platformLabel(platform) : "全部端口"}</span></article>)}</div>}
    <div className="commerce-tabs"><button className={view === "users" ? "active" : ""} onClick={() => { setView("users"); setSearch(""); setStatus(""); setUserPage(1); }}><Users size={17}/>用户</button><button className={view === "orders" ? "active" : ""} onClick={() => { setView("orders"); setSearch(""); setStatus(""); }}><Receipt size={17}/>订单</button><button className={view === "recharges" ? "active" : ""} onClick={() => { setView("recharges"); setSearch(""); setStatus(""); }}><Wallet size={17}/>充值</button></div>
    <form className="refund-toolbar" onSubmit={submit}><AdminPlatformFilter value={platform} onChange={(value) => { setPlatform(value); setUserPage(1); }}/><input aria-label={view === "users" ? "搜索用户名或手机号" : "搜索订单号"} placeholder={view === "users" ? "用户名或手机号" : "订单号"} value={search} onChange={(event) => { setSearch(event.target.value); if (view === "users") setUserPage(1); }}/>{view === "users" ? <select aria-label="账号状态筛选" value={status} onChange={(event) => { setStatus(event.target.value); setUserPage(1); }}><option value="">全部账号状态</option><option value="active">正常</option><option value="suspended">已冻结</option><option value="deleting">注销处理中</option><option value="deleted">已注销</option></select> : <input aria-label="状态筛选" placeholder="状态" value={status} onChange={(event) => setStatus(event.target.value)}/>}<button disabled={loading}><ArrowClockwise size={15}/>{loading ? "加载中" : "查询"}</button></form>
    {error && <div className="commerce-error">{error}</div>}
    {notice && <div className="commerce-success">{notice}</div>}

    {pendingAction && <form className={`admin-account-action-panel${pendingAction.action === "delete" ? " admin-account-action-panel--danger" : ""}`} onSubmit={submitUserAction}>
      <div><small>账号管理 · 用户 #{pendingAction.user.id}</small><h2>{actionLabels[pendingAction.action]}：{pendingAction.user.username}</h2><p>{actionDescription(pendingAction.action)}</p></div>
      <label>操作原因<textarea required minLength={4} maxLength={500} value={actionReason} onChange={(event) => setActionReason(event.target.value)} placeholder="请填写可供审计复核的原因，不要填写密码、验证码、证件号或银行卡号"/></label>
      {pendingAction.action === "delete" && <label>输入完整用户名确认<input required value={confirmUsername} onChange={(event) => setConfirmUsername(event.target.value)} placeholder={pendingAction.user.username}/></label>}
      <footer><button type="button" className="outline-link" disabled={actionBusy} onClick={() => setPendingAction(null)}>取消</button><button className={pendingAction.action === "delete" ? "commerce-danger" : "commerce-primary"} disabled={actionBusy || actionReason.trim().length < 4 || (pendingAction.action === "delete" && confirmUsername.trim() !== pendingAction.user.username)}>{actionBusy ? "提交中" : `确认${actionLabels[pendingAction.action]}`}</button></footer>
    </form>}

    {view === "users" && <div className="admin-settlement-list">{users.length ? users.map((row) => <article key={row.id}>
      <header><div><small>用户 #{row.id} · {platformLabel(row.created_platform)}</small><h2>{row.username}</h2><span>{formatDate(row.created_at)}</span></div><b className={`status-chip ${row.account_status === "active" ? "status-chip--published" : "status-chip--pending_review"}`}>{statusLabels[row.account_status] || row.account_status}</b></header>
      <p>{row.phone_masked || "未绑定手机号"} · 找回邮箱{row.recovery_email_verified ? "已验证" : "未验证"} · KAI 身份{row.kai_identity_bound ? "已绑定" : "未绑定"} · {row.password_set ? "已设置密码" : "未设置本地密码"} · 商家状态 {row.supplier_status}</p>
      <footer className="admin-account-actions">
        {row.role !== "admin" && row.account_status !== "deleted" && row.account_status !== "deleting" && <>
          <button type="button" disabled={!row.recovery_email_verified || row.account_status !== "active"} title={row.recovery_email_verified ? "向已验证邮箱发送一次性链接" : "该账号没有已验证的找回邮箱"} onClick={() => beginUserAction(row, "send_password_reset")}><EnvelopeSimple size={15}/>重置密码</button>
          {row.account_status === "active" ? <button type="button" onClick={() => beginUserAction(row, "freeze")}><LockKey size={15}/>冻结</button> : row.account_status === "suspended" ? <button type="button" onClick={() => beginUserAction(row, "unfreeze")}><LockOpen size={15}/>解冻</button> : null}
          <button type="button" className="commerce-danger" onClick={() => beginUserAction(row, "delete")}><Trash size={15}/>注销</button>
        </>}
        <button type="button" disabled={historyBusy} onClick={() => void toggleUserHistory(row)}><ClockCounterClockwise size={15}/>{historyUserId === row.id ? "收起记录" : "操作记录"}</button>
      </footer>
      {historyUserId === row.id && <div className="admin-account-history">{historyRows.length ? historyRows.map((action) => <div key={action.id}><span>{actionLabels[action.action] || action.action} · 管理员 #{action.actor_user_id}</span><strong>{action.reason}</strong><time>{action.created_at ? formatDate(action.created_at) : "时间待同步"} · {statusLabels[action.previous_status] || action.previous_status} → {statusLabels[action.new_status] || action.new_status}</time></div>) : <p>暂无账号管理操作记录</p>}</div>}
    </article>) : <div className="commerce-empty"><Users size={25}/><strong>没有符合条件的用户</strong></div>}
      {userTotal > 20 && <nav className="admin-account-pagination" aria-label="用户列表分页"><button type="button" disabled={loading || userPage <= 1} onClick={() => setUserPage((page) => Math.max(1, page - 1))}>上一页</button><span>第 {userPage} / {Math.ceil(userTotal / 20)} 页 · 共 {userTotal} 个账号</span><button type="button" disabled={loading || userPage >= Math.ceil(userTotal / 20)} onClick={() => setUserPage((page) => page + 1)}>下一页</button></nav>}
    </div>}
    {view === "orders" && <div className="admin-settlement-list">{orders.length ? orders.map((row) => <article key={row.id}><header><div><small>{row.order_no} · 创建 {platformLabel(row.created_platform)} · 修改 {platformLabel(row.last_modified_platform)}</small><h2>{row.product.name || row.product.gpu_model || `商品 #${row.product.id}`}</h2><span>{row.user.username || `用户 #${row.user.id}`} · {formatDate(row.created_at)}</span></div><strong>{row.amount_card_hours} 卡时</strong><b className="status-chip status-chip--pending_review">{row.status}</b></header><p>{row.quantity} 台 · {row.purchase_hours ? `${row.purchase_hours} 小时` : row.cycle_days ? `${row.cycle_days} 天（历史）` : "时长未记录"}</p></article>) : <div className="commerce-empty"><Receipt size={25}/><strong>没有符合条件的订单</strong></div>}</div>}
    {view === "recharges" && <div className="admin-settlement-list">{recharges.length ? recharges.map((row) => <article key={row.id}><header><div><small>{row.order_no} · 创建 {platformLabel(row.created_platform)} · 修改 {platformLabel(row.last_modified_platform)}</small><h2>{row.provider} / {row.channel}</h2><span>{row.user.username || `用户 #${row.user.id}`} · {formatDate(row.created_at)}</span></div><strong>¥ {row.amount_cny.toFixed(2)}</strong><b className="status-chip status-chip--pending_review">{row.status}</b></header><p>{row.card_hours} 卡时 · 汇率 {row.card_hour_rate}</p></article>) : <div className="commerce-empty"><Wallet size={25}/><strong>没有符合条件的充值订单</strong></div>}</div>}
  </section>;
}
