"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowClockwise, ClockCounterClockwise, EnvelopeSimple, LockKey, LockOpen, Receipt, Trash, Users, Wallet } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import {
  deliverAdminOrder,
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
import { useI18n } from "@/components/locale-root";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";

type View = "users" | "orders" | "recharges";
type PendingUserAction = { user: AdminUserItem; action: AdminUserActionKind };
type IssuedPasswordReset = { username: string; token: string; expiresAt: string };

const countLabels = { users: "用户", orders: "订单", recharge_orders: "充值", verifications: "实名", bank_cards: "银行卡", withdrawals: "提现" } as const;
const statusLabels: Record<string, string> = { active: "正常", suspended: "已冻结", deleting: "注销处理中", deleted: "已注销" };
const actionLabels: Record<AdminUserActionKind, string> = {
  send_password_reset: "发送重置邮件",
  issue_password_reset_code: "生成一次性重置码",
  freeze: "冻结账号",
  unfreeze: "解除冻结",
  delete: "注销账号",
};

function actionDescription(action: AdminUserActionKind) {
  if (action === "send_password_reset") return "系统只会向用户已验证的找回邮箱发送一次性链接，管理员看不到原密码、完整邮箱或重置令牌。";
  if (action === "issue_password_reset_code") return "完成用户身份核验后生成短时、单次使用的重置码。管理员不能指定或查看用户的新密码；重置码只在本次成功响应中显示。";
  if (action === "freeze") return "立即使全部登录会话和找回凭证失效，并阻止该账号继续登录；若账号属于商家，还会同步停用商家权限并下架商品。订单、资金和审计记录不会被修改。";
  if (action === "unfreeze") return "恢复账号登录能力。旧会话不会恢复，用户需要重新登录。";
  return "仅在没有未结订单、资金、退款、提现或争议时进入不可逆注销流程；依法应保留的账务及审计记录不会物理删除。";
}

export function AdminPlatformAuditWorkspace() {
  const { t, formatCnyMoney, formatLedgerMoney } = useI18n();
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [view, setView] = useState<View>("users");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [userPage, setUserPage] = useState(1);
  const [userTotal, setUserTotal] = useState(0);
  const [orders, setOrders] = useState<AdminOrderItem[]>([]);
  const [orderPage, setOrderPage] = useState(1);
  const [orderTotal, setOrderTotal] = useState(0);
  const [recharges, setRecharges] = useState<AdminRechargeItem[]>([]);
  const [rechargePage, setRechargePage] = useState(1);
  const [rechargeTotal, setRechargeTotal] = useState(0);
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
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [issuedReset, setIssuedReset] = useState<IssuedPasswordReset | null>(null);
  const [pendingDelivery, setPendingDelivery] = useState<AdminOrderItem | null>(null);
  const [sshInfo, setSshInfo] = useState("");
  const [deliveryBusy, setDeliveryBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    const source = platform || undefined;
    try {
      const [summary, userPageResult, orderPageResult, rechargePageResult] = await Promise.all([
        getAdminOverview(source),
        listAdminUsers({ platform: source, keyword: view === "users" ? search : undefined, status: view === "users" ? status : undefined, page: userPage, pageSize: 20 }),
        listAdminOrders({ platform: source, status: view === "orders" ? status : undefined, orderNo: view === "orders" ? search : undefined, page: orderPage, pageSize: 20 }),
        listAdminRechargeOrders({ platform: source, status: view === "recharges" ? status : undefined, orderNo: view === "recharges" ? search : undefined, page: rechargePage, pageSize: 20 }),
      ]);
      setOverview(summary); setUsers(userPageResult.items); setUserTotal(userPageResult.total); setOrders(orderPageResult.items); setOrderTotal(orderPageResult.total); setRecharges(rechargePageResult.items); setRechargeTotal(rechargePageResult.total);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, [orderPage, platform, rechargePage, search, status, userPage, view]);

  useEffect(() => { void load(); }, [load]);
  function submit(event: FormEvent) { event.preventDefault(); void load(); }

  function beginUserAction(user: AdminUserItem, action: AdminUserActionKind) {
    setPendingAction({ user, action });
    setIssuedReset(null);
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
      const result = await manageAdminUser(pendingAction.user.id, {
        action: pendingAction.action,
        client_request_id: `admin-account-${crypto.randomUUID()}`,
        reason: actionReason,
        confirm_username: pendingAction.action === "delete" || pendingAction.action === "issue_password_reset_code" ? confirmUsername : undefined,
      });
      if (result.reset_token && result.reset_expires_at) {
        setIssuedReset({
          username: pendingAction.user.username,
          token: result.reset_token,
          expiresAt: result.reset_expires_at,
        });
        setNotice("一次性重置码已生成。请在核验用户身份后安全地交给本人，关闭后无法再次查看。");
      } else {
        setNotice(t("admin.platform.actionSubmitted", "{username}：{action}已提交。", {
          username: pendingAction.user.username,
          action: t(`admin.platform.action.${pendingAction.action}`, actionLabels[pendingAction.action]),
        }));
      }
      setPendingAction(null); setActionReason(""); setConfirmUsername("");
      await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setActionBusy(false); }
  }

  async function copyResetValue(kind: "code" | "link") {
    if (!issuedReset) return;
    const value = kind === "code"
      ? issuedReset.token
      : `${window.location.origin}/reset-password#token=${encodeURIComponent(issuedReset.token)}`;
    try {
      await navigator.clipboard.writeText(value);
      setNotice(kind === "code" ? "一次性重置码已复制。" : "密码重置链接已复制。");
    } catch {
      setError("浏览器未允许复制，请手动选择并复制重置码。");
    }
  }

  function beginDelivery(order: AdminOrderItem) {
    setPendingDelivery(order);
    setSshInfo("");
    setError("");
    setNotice("");
  }

  async function submitDelivery(event: FormEvent) {
    event.preventDefault();
    if (!pendingDelivery) return;
    setDeliveryBusy(true); setError(""); setNotice("");
    try {
      await deliverAdminOrder(pendingDelivery.id, sshInfo.trim());
      setNotice(`订单 ${pendingDelivery.order_no} 已提交资源交付，等待用户确认。`);
      setPendingDelivery(null); setSshInfo("");
      await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setDeliveryBusy(false); }
  }

  function canDeliver(order: AdminOrderItem) {
    return order.status === "paid"
      && order.purchase_type === "usage"
      && order.seller_type === "kai_self_operated"
      && order.fulfillment_mode === "platform_manual";
  }

  async function loadUserHistory(userId: number, nextPage: number) {
    setHistoryBusy(true); setError("");
    try {
      const result = await listAdminUserActions(userId, { page: nextPage, pageSize: 20 });
      setHistoryUserId(userId); setHistoryRows(result.items); setHistoryPage(result.page); setHistoryTotal(result.total);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setHistoryBusy(false); }
  }

  async function toggleUserHistory(user: AdminUserItem) {
    if (historyUserId === user.id) {
      setHistoryUserId(null); setHistoryRows([]); setHistoryPage(1); setHistoryTotal(0);
      return;
    }
    await loadUserHistory(user.id, 1);
  }

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / PLATFORM DATA</p><h1>端口数据</h1><span>三端共享业务数据，管理员按数据产生端口查看来源与后续修改来源。</span></div>
    {overview && <div className="commerce-stat-grid">{Object.entries(overview.counts).map(([key, value]) => <article key={key}><small>{countLabels[key as keyof typeof countLabels]}</small><strong>{value}</strong><span>{platform ? platformLabel(platform) : "全部端口"}</span></article>)}</div>}
    <div className="commerce-tabs"><button className={view === "users" ? "active" : ""} onClick={() => { setView("users"); setSearch(""); setStatus(""); setUserPage(1); }}><Users size={17}/>用户</button><button className={view === "orders" ? "active" : ""} onClick={() => { setView("orders"); setSearch(""); setStatus(""); setOrderPage(1); }}><Receipt size={17}/>订单</button><button className={view === "recharges" ? "active" : ""} onClick={() => { setView("recharges"); setSearch(""); setStatus(""); setRechargePage(1); }}><Wallet size={17}/>充值</button></div>
    <form className="refund-toolbar" onSubmit={submit}><AdminPlatformFilter value={platform} onChange={(value) => { setPlatform(value); setUserPage(1); setOrderPage(1); setRechargePage(1); }}/><input aria-label={view === "users" ? "搜索用户名或手机号" : "搜索订单号"} placeholder={view === "users" ? "用户名或手机号" : "订单号"} value={search} onChange={(event) => { setSearch(event.target.value); setUserPage(1); setOrderPage(1); setRechargePage(1); }}/>{view === "users" ? <select aria-label="账号状态筛选" value={status} onChange={(event) => { setStatus(event.target.value); setUserPage(1); }}><option value="">全部账号状态</option><option value="active">正常</option><option value="suspended">已冻结</option><option value="deleting">注销处理中</option><option value="deleted">已注销</option></select> : <input aria-label="状态筛选" placeholder="状态" value={status} onChange={(event) => { setStatus(event.target.value); setOrderPage(1); setRechargePage(1); }}/>}<button disabled={loading}><ArrowClockwise size={15}/>{loading ? "加载中" : "查询"}</button></form>
    {error && <div className="commerce-error">{error}</div>}
    {notice && <div className="commerce-success">{notice}</div>}

    {issuedReset && <aside className="admin-reset-proof" role="status">
      <div><small>一次性账号恢复凭证</small><h2><span data-i18n-skip>{issuedReset.username}</span> 的重置码</h2><p>仅向已核验身份的账号本人提供。使用一次后立即失效，管理员不能查看或设置用户的新密码。</p></div>
      <code data-i18n-skip>{issuedReset.token}</code>
      <span>有效期至 {formatDate(issuedReset.expiresAt)}；关闭本提示后不能再次显示。</span>
      <footer><button type="button" onClick={() => void copyResetValue("code")}>复制重置码</button><button type="button" onClick={() => void copyResetValue("link")}>复制网页重置链接</button><button type="button" className="outline-link" onClick={() => setIssuedReset(null)}>已安全交给用户并关闭</button></footer>
    </aside>}

    {pendingAction && <form className={`admin-account-action-panel${pendingAction.action === "delete" ? " admin-account-action-panel--danger" : ""}`} onSubmit={submitUserAction}>
      <div><small>账号管理 · 用户 #{pendingAction.user.id}</small><h2>{t(`admin.platform.action.${pendingAction.action}`, actionLabels[pendingAction.action])}：<span data-i18n-skip>{pendingAction.user.username}</span></h2><p>{actionDescription(pendingAction.action)}</p></div>
      <label>操作原因<textarea required minLength={4} maxLength={500} value={actionReason} onChange={(event) => setActionReason(event.target.value)} placeholder="请填写可供审计复核的原因，不要填写密码、验证码、证件号或银行卡号"/></label>
      {(pendingAction.action === "delete" || pendingAction.action === "issue_password_reset_code") && <label>输入完整用户名确认<input required autoComplete="off" value={confirmUsername} onChange={(event) => setConfirmUsername(event.target.value)} placeholder={pendingAction.user.username}/></label>}
      <footer><button type="button" className="outline-link" disabled={actionBusy} onClick={() => setPendingAction(null)}>取消</button><button className={pendingAction.action === "delete" ? "commerce-danger" : "commerce-primary"} disabled={actionBusy || actionReason.trim().length < 4 || ((pendingAction.action === "delete" || pendingAction.action === "issue_password_reset_code") && confirmUsername.trim() !== pendingAction.user.username)}>{actionBusy ? "提交中" : t("admin.platform.confirmAction", "确认{action}", { action: t(`admin.platform.action.${pendingAction.action}`, actionLabels[pendingAction.action]) })}</button></footer>
    </form>}

    {pendingDelivery && <form className="admin-account-action-panel" onSubmit={submitDelivery}>
      <div><small>平台自营资源交付 · 订单 <span data-i18n-skip>{pendingDelivery.order_no}</span></small><h2>提交 SSH 连接信息</h2><p>只填写主机、端口与用户名等连接信息，不要填写密码、私钥、验证码或其他敏感凭证。提交后订单进入“等待用户确认”。</p></div>
      <label>SSH 连接信息<textarea required minLength={5} maxLength={2000} value={sshInfo} onChange={(event) => setSshInfo(event.target.value)} placeholder="例如：ssh ubuntu@203.0.113.10 -p 22"/></label>
      <footer><button type="button" className="outline-link" disabled={deliveryBusy} onClick={() => { setPendingDelivery(null); setSshInfo(""); }}>取消</button><button className="commerce-primary" disabled={deliveryBusy || sshInfo.trim().length < 5}>{deliveryBusy ? "交付中" : "确认提交交付"}</button></footer>
    </form>}

    {view === "users" && <div className="admin-settlement-list">{users.length ? users.map((row) => <article key={row.id}>
      <header><div><small>用户 #{row.id} · {platformLabel(row.created_platform)}</small><h2 data-i18n-skip>{row.username}</h2><span>{formatDate(row.created_at)}</span></div><b className={`status-chip ${row.account_status === "active" ? "status-chip--published" : "status-chip--pending_review"}`}>{statusLabels[row.account_status] || row.account_status}</b></header>
      <p>{row.phone_masked || "未绑定手机号"} · 找回邮箱{row.recovery_email_verified ? "已验证" : "未验证"} · KAI 身份{row.kai_identity_bound ? "已绑定" : "未绑定"} · {row.password_set ? "已设置密码" : "未设置本地密码"} · 商家状态 {row.supplier_status}</p>
      <footer className="admin-account-actions">
        {row.role !== "admin" && row.account_status !== "deleted" && row.account_status !== "deleting" && <>
          <button type="button" disabled={!row.recovery_email_verified || row.account_status !== "active"} title={row.recovery_email_verified ? "向已验证邮箱发送一次性链接" : "该账号没有已验证的找回邮箱"} onClick={() => beginUserAction(row, "send_password_reset")}><EnvelopeSimple size={15}/>发送重置邮件</button>
          <button type="button" disabled={row.account_status !== "active"} title="身份核验后生成只显示一次的短时重置码" onClick={() => beginUserAction(row, "issue_password_reset_code")}><LockOpen size={15}/>生成重置码</button>
          {row.account_status === "active" ? <button type="button" onClick={() => beginUserAction(row, "freeze")}><LockKey size={15}/>冻结</button> : row.account_status === "suspended" ? <button type="button" onClick={() => beginUserAction(row, "unfreeze")}><LockOpen size={15}/>解冻</button> : null}
          <button type="button" className="commerce-danger" onClick={() => beginUserAction(row, "delete")}><Trash size={15}/>注销</button>
        </>}
        <button type="button" disabled={historyBusy} onClick={() => void toggleUserHistory(row)}><ClockCounterClockwise size={15}/>{historyUserId === row.id ? "收起记录" : "操作记录"}</button>
      </footer>
      {historyUserId === row.id && <div className="admin-account-history">{historyRows.length ? historyRows.map((action) => <div key={action.id}><span>{actionLabels[action.action] || action.action} · 管理员 #{action.actor_user_id}</span><strong data-i18n-skip>{action.reason}</strong><time>{action.created_at ? formatDate(action.created_at) : "时间待同步"} · {statusLabels[action.previous_status] || action.previous_status} → {statusLabels[action.new_status] || action.new_status}</time></div>) : <p>暂无账号管理操作记录</p>}<AdminQueuePagination page={historyPage} total={historyTotal} loading={historyBusy} onPageChange={(value) => void loadUserHistory(row.id, value)}/></div>}
    </article>) : <div className="commerce-empty"><Users size={25}/><strong>没有符合条件的用户</strong></div>}
      {userTotal > 20 && <nav className="admin-account-pagination" aria-label="用户列表分页"><button type="button" disabled={loading || userPage <= 1} onClick={() => setUserPage((page) => Math.max(1, page - 1))}>上一页</button><span>{t("admin.platform.userPageSummary", "第 {page} / {pages} 页 · 共 {total} 个账号", { page: userPage, pages: Math.ceil(userTotal / 20), total: userTotal })}</span><button type="button" disabled={loading || userPage >= Math.ceil(userTotal / 20)} onClick={() => setUserPage((page) => page + 1)}>下一页</button></nav>}
    </div>}
    {view === "orders" && <div className="admin-settlement-list">{orders.length ? orders.map((row) => <article key={row.id}>
      <header><div><small>{row.order_no} · 创建 {platformLabel(row.created_platform)} · 修改 {platformLabel(row.last_modified_platform)}</small><h2 data-i18n-skip={Boolean(row.product.name || row.product.gpu_model) || undefined}>{row.product.name || row.product.gpu_model || t("admin.platform.productFallback", "商品 #{id}", { id: row.product.id })}</h2><span data-i18n-skip>{row.user.username || `USER #${row.user.id}`} · {formatDate(row.created_at)}</span></div><strong>{formatLedgerMoney(row.amount_card_hours)}</strong><b className="status-chip status-chip--pending_review">{row.status}</b></header>
      <p>{row.quantity} 台 · {row.purchase_hours ? `${row.purchase_hours} 小时` : row.cycle_days ? t("admin.platform.historicDays", "{days} 天（历史）", { days: row.cycle_days }) : "时长未记录"} · {row.seller_type === "kai_self_operated" ? "平台自营" : "第三方商家"} · {row.ssh_info_present ? "已提交连接信息" : "尚未提交连接信息"}</p>
      {canDeliver(row) && <footer className="admin-account-actions"><button type="button" onClick={() => beginDelivery(row)}><LockKey size={15}/>交付 SSH / 算力资源</button></footer>}
    </article>) : <div className="commerce-empty"><Receipt size={25}/><strong>没有符合条件的订单</strong></div>}<AdminQueuePagination page={orderPage} total={orderTotal} loading={loading} onPageChange={setOrderPage}/></div>}
    {view === "recharges" && <div className="admin-settlement-list">{recharges.length ? recharges.map((row) => <article key={row.id}><header><div><small>{row.order_no} · 创建 {platformLabel(row.created_platform)} · 修改 {platformLabel(row.last_modified_platform)}</small><h2>{row.provider} / {row.channel}</h2><span>{row.user.username || `用户 #${row.user.id}`} · {formatDate(row.created_at)}</span></div><strong>{formatCnyMoney(row.amount_cny)}</strong><b className="status-chip status-chip--pending_review">{row.status}</b></header><p>支付成功后等额计入账户余额</p></article>) : <div className="commerce-empty"><Wallet size={25}/><strong>没有符合条件的充值订单</strong></div>}<AdminQueuePagination page={rechargePage} total={rechargeTotal} loading={loading} onPageChange={setRechargePage}/></div>}
  </section>;
}
