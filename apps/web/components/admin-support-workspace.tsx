"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ChatCircleText, CheckCircle, MagnifyingGlass, UserSwitch, XCircle } from "@phosphor-icons/react";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { useI18n } from "@/components/locale-root";
import {
  getAdminSupportTicket,
  listAdminSupportTickets,
  listAdminUsers,
  manageAdminSupportTicket,
  type AdminSupportTicket,
  type AdminSupportTicketDetail,
  type AdminSupportTicketStatus,
  type AdminUserItem,
} from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const PAGE_SIZE = 20;

function requestId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `support:${crypto.randomUUID()}`
    : `support:${Date.now()}:${Math.random().toString(36).slice(2)}`;
}

export function AdminSupportWorkspace() {
  const { locale } = useI18n();
  const en = locale === "en";
  const [rows, setRows] = useState<AdminSupportTicket[]>([]);
  const [detail, setDetail] = useState<AdminSupportTicketDetail | null>(null);
  const [operators, setOperators] = useState<AdminUserItem[]>([]);
  const [status, setStatus] = useState<AdminSupportTicketStatus | "">("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [reply, setReply] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selected = detail?.ticket ?? null;
  const statusLabels = useMemo<Record<AdminSupportTicketStatus, string>>(() => ({
    pending_unassigned: en ? "Unassigned" : "待分配",
    assigned: en ? "In progress" : "处理中",
    resolved: en ? "Resolved" : "已解决",
    closed: en ? "Closed" : "已关闭",
  }), [en]);

  const loadDetail = useCallback(async (id: number) => {
    const value = await getAdminSupportTicket(id);
    setDetail(value);
  }, []);

  const load = useCallback(async (nextPage = page, preferredId?: number) => {
    setLoading(true);
    setError("");
    try {
      const [result, users] = await Promise.all([
        listAdminSupportTickets({ status, keyword, page: nextPage, pageSize: PAGE_SIZE }),
        listAdminUsers({ status: "active", page: 1, pageSize: 100 }),
      ]);
      setRows(result.items);
      setTotal(result.total);
      setPage(result.page);
      setOperators(users.items.filter((item) => item.role === "admin"));
      const id = preferredId && result.items.some((item) => item.id === preferredId)
        ? preferredId
        : result.items[0]?.id;
      if (id) await loadDetail(id);
      else setDetail(null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [keyword, loadDetail, page, status]);

  useEffect(() => { void load(1); }, [status]);

  async function act(action: "claim" | "assign" | "reply" | "resolve" | "close" | "reopen") {
    if (!selected) return;
    if (action === "reply" && !reply.trim()) {
      setError(en ? "Enter a reply." : "请输入回复内容。");
      return;
    }
    if (action === "assign" && !assigneeId) {
      setError(en ? "Choose an administrator." : "请选择接收工单的管理员。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await manageAdminSupportTicket(selected.id, {
        action,
        expected_status: selected.status,
        assignee_user_id: action === "assign" ? Number(assigneeId) : undefined,
        reply: action === "reply" ? reply.trim() : undefined,
        request_id: requestId(),
      });
      setReply("");
      setDetail(updated);
      await load(page, selected.id);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(1);
  }

  return <section className="workspace-page commerce-workspace admin-support-workspace">
    <div className="workspace-page__head"><p>OPERATIONS / HUMAN SUPPORT</p><h1>{en ? "Support ticket queue" : "客服工单队列"}</h1><span>{en ? "Claim, assign, reply to, resolve, and close real customer tickets. Every mutation is audited." : "认领、分配、回复、解决和关闭用户工单；所有管理操作均写入审计记录。"}</span></div>
    {error && <div className="commerce-error" role="alert">{error}</div>}
    <div className="review-console admin-support-console">
      <aside>
        <form onSubmit={submit}><label><MagnifyingGlass size={15}/><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={en ? "Ticket, subject, or account" : "搜索工单号、主题或账号"}/></label><select value={status} onChange={(event) => setStatus(event.target.value as AdminSupportTicketStatus | "")}><option value="">{en ? "All statuses" : "全部状态"}</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></form>
        {loading && rows.length === 0 ? <div className="commerce-loading">{en ? "Loading tickets…" : "正在读取工单…"}</div> : rows.length === 0 ? <div className="commerce-empty"><ChatCircleText size={24}/><strong>{en ? "No matching tickets" : "没有符合条件的工单"}</strong></div> : <div className="review-queue">{rows.map((row) => <button className={selected?.id === row.id ? "active" : ""} type="button" key={row.id} onClick={() => void loadDetail(row.id)}><span><small>{row.ticket_no} · {formatDate(row.updated_at)}</small><strong data-i18n-skip>{row.subject}</strong><em data-i18n-skip>{row.user.username ?? `#${row.user.id}`}</em></span><b className={`status-chip status-chip--${row.status}`}>{statusLabels[row.status]}</b></button>)}</div>}
        <AdminQueuePagination page={page} total={total} loading={loading} onPageChange={(value) => void load(value)}/>
      </aside>
      <article className="review-dossier admin-support-detail">{selected && detail ? <>
        <header><div><p>{selected.ticket_no}</p><h2 data-i18n-skip>{selected.subject}</h2><small>{en ? "Account" : "账号"}: <span data-i18n-skip>{selected.user.username ?? `#${selected.user.id}`}</span></small></div><span className={`status-chip status-chip--${selected.status}`}>{statusLabels[selected.status]}</span></header>
        <section className="admin-support-summary"><h3>{en ? "Issue description" : "问题说明"}</h3><p data-i18n-skip>{selected.description}</p><small>{en ? "Category" : "分类"}: {selected.category} · {en ? "Assigned to" : "当前处理人"}: <span data-i18n-skip>{selected.assigned_to || (en ? "Nobody" : "未分配")}</span></small></section>
        <section className="admin-support-thread"><h3>{en ? "Conversation" : "会话记录"}</h3>{detail.messages.items.map((message) => <div className={`admin-support-message admin-support-message--${message.role}`} key={message.id}><strong>{message.role === "user" ? (en ? "Customer" : "用户") : message.response_mode === "human" ? (en ? "Operator" : "人工客服") : (en ? "Assistant" : "自助客服")}</strong><p data-i18n-skip>{message.content}</p><small>{formatDate(message.created_at)}</small></div>)}</section>
        <footer className="admin-support-actions">
          {selected.status === "pending_unassigned" && <button type="button" disabled={busy} onClick={() => void act("claim")}><CheckCircle size={16}/>{en ? "Claim" : "认领工单"}</button>}
          {(selected.status === "pending_unassigned" || selected.status === "assigned") && <label><span>{en ? "Assign to" : "分配给管理员"}</span><div><select value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)}><option value="">{en ? "Choose" : "请选择"}</option>{operators.map((item) => <option key={item.id} value={item.id}>{item.username}</option>)}</select><button type="button" disabled={busy || !assigneeId} onClick={() => void act("assign")}><UserSwitch size={16}/>{en ? "Assign" : "分配"}</button></div></label>}
          {(selected.status === "pending_unassigned" || selected.status === "assigned") && <label><span>{en ? "Reply" : "人工回复"}</span><textarea rows={4} maxLength={2000} value={reply} onChange={(event) => setReply(event.target.value)} placeholder={en ? "Reply appears in Support and Notifications" : "回复会同步到用户客服页和消息中心"}/><div><button type="button" disabled={busy || !reply.trim()} onClick={() => void act("reply")}>{en ? "Send reply" : "发送回复"}</button>{selected.status === "assigned" && <><button type="button" disabled={busy} onClick={() => void act("resolve")}><CheckCircle size={16}/>{en ? "Resolve" : "标记已解决"}</button><button className="commerce-danger" type="button" disabled={busy} onClick={() => void act("close")}><XCircle size={16}/>{en ? "Close" : "关闭工单"}</button></>}</div></label>}
          {selected.status === "resolved" && <button className="commerce-danger" type="button" disabled={busy} onClick={() => void act("close")}><XCircle size={16}/>{en ? "Close" : "关闭工单"}</button>}
          {(selected.status === "resolved" || selected.status === "closed") && <button type="button" disabled={busy} onClick={() => void act("reopen")}>{en ? "Reopen and assign to me" : "重新打开并由我处理"}</button>}
        </footer>
      </> : <div className="commerce-empty"><ChatCircleText size={25}/><strong>{en ? "Select a ticket" : "选择一条工单查看详情"}</strong></div>}</article>
    </div>
  </section>;
}
