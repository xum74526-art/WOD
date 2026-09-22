"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Bell, ClockCounterClockwise, Megaphone, PaperPlaneTilt, Prohibit, ShieldCheck } from "@phosphor-icons/react";
import {
  createAdminNotificationBroadcast,
  listAdminNotificationBroadcasts,
  revokeAdminNotificationBroadcast,
  type AdminNotificationBroadcast,
  type AdminNotificationBroadcastInput,
} from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { useI18n } from "@/components/locale-root";
import { localDateTimeInputToUtcIso } from "@/lib/date-time";

const TYPE_LABELS: Record<AdminNotificationBroadcast["notification_type"], string> = {
  major_announcement: "重大公告（首页展示）",
  system: "系统公告",
  order: "订单提醒",
  device: "设备提醒",
  revenue: "收益提醒",
  wallet: "钱包提醒",
};

function requestId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `broadcast-${crypto.randomUUID()}`;
  }
  return `broadcast-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

type BroadcastDraft = Omit<AdminNotificationBroadcastInput, "client_request_id">;

function draftSignature(draft: BroadcastDraft) {
  return JSON.stringify([
    draft.title,
    draft.content,
    draft.title_en ?? null,
    draft.content_en ?? null,
    draft.notification_type,
    draft.action_url ?? null,
    draft.expires_at ?? null,
  ]);
}

export function AdminNotificationWorkspace() {
  const { locale } = useI18n();
  const [rows, setRows] = useState<AdminNotificationBroadcast[]>([]);
  const [form, setForm] = useState({
    title: "",
    content: "",
    title_en: "",
    content_en: "",
    notification_type: "system" as AdminNotificationBroadcast["notification_type"],
    action_url: "",
    expires_at: "",
  });
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revokingId, setRevokingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const pendingRequest = useRef<{ signature: string; id: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listAdminNotificationBroadcasts({ page: 1, pageSize: 20 });
      setRows(result.items);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const title = form.title.trim();
    const content = form.content.trim();
    if (!title || !content) {
      setError("请填写消息标题和正文");
      return;
    }
    const isMajorAnnouncement = form.notification_type === "major_announcement";
    const confirmation = isMajorAnnouncement
      ? "确认发布这条重大公告吗？内容会在 Web 公开首页和 App 首页展示，并进入所有有效账号的消息中心。请确认正文不含内部或个人信息。"
      : "确认向所有有效账号发布这条站内消息吗？发布后会立即进入收件箱。";
    if (!window.confirm(confirmation)) return;
    let expiresAt: string | null = null;
    try {
      expiresAt = form.expires_at ? localDateTimeInputToUtcIso(form.expires_at) : null;
    } catch (reason) {
      setError(errorMessage(reason));
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    const draft: BroadcastDraft = {
      title,
      content,
      title_en: form.title_en.trim() || null,
      content_en: form.content_en.trim() || null,
      notification_type: form.notification_type,
      action_url: form.action_url.trim() || null,
      expires_at: expiresAt,
    };
    const signature = draftSignature(draft);
    const pending = pendingRequest.current?.signature === signature ? pendingRequest.current : null;
    const input: AdminNotificationBroadcastInput = {
      ...draft,
      client_request_id: pending?.id ?? requestId(),
    };
    pendingRequest.current = { signature, id: input.client_request_id };
    try {
      const result = await createAdminNotificationBroadcast(input);
      pendingRequest.current = null;
      setMessage(isMajorAnnouncement
        ? `重大公告已发布，三端首页将显示，${result.recipient_count} 个有效账号也会收到站内消息。`
        : `已发布，${result.recipient_count} 个有效账号将收到消息。`);
      setForm((current) => ({ ...current, content: "", content_en: "", expires_at: "" }));
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(row: AdminNotificationBroadcast) {
    if (revokingId !== null) return;
    const reason = window.prompt(
      locale === "en"
        ? "Enter a revocation reason (at least 2 characters). This notice will immediately disappear from every client."
        : "请输入撤销原因（至少 2 个字）。撤销后公告会立即从所有端下架。",
    )?.trim();
    if (!reason) return;
    if (reason.length < 2) {
      setError(locale === "en" ? "Enter at least 2 characters." : "撤销原因至少需要 2 个字");
      return;
    }
    if (!window.confirm(locale === "en" ? "Revoke this notice now?" : "确认立即撤销这条公告吗？")) return;
    setRevokingId(row.id);
    setError("");
    setMessage("");
    try {
      await revokeAdminNotificationBroadcast(row.id, reason);
      setMessage(locale === "en" ? "The notice was revoked and removed from all inboxes." : "公告已撤销，并已从所有用户通知中心下架。审计记录仍然保留。");
      await load();
    } catch (reasonValue) {
      setError(errorMessage(reasonValue));
    } finally {
      setRevokingId(null);
    }
  }

  const statusLabel = (status: string) => ({
    completed: "已发布",
    processing: "处理中",
    expired: "已过期",
    revoked: "已撤销",
  } as Record<string, string>)[status] || status;

  return <section className="workspace-page commerce-workspace admin-notification-workspace">
    <div className="workspace-page__head">
      <p>ADMIN / MESSAGE CENTER</p>
      <h1>消息发布</h1>
      <span>管理员可以向所有有效账号发送一条站内通知；普通账号没有发布权限。</span>
    </div>

    <div className="notification-broadcast-safety"><ShieldCheck size={19} /><div><strong>发布边界</strong><span>普通消息只进入通知中心；重大公告会额外公开显示在 Web 首页及 Android、iOS 首页，请勿填写内部或个人信息。两类消息都不会发送短信或外部邮件，并保留管理员、幂等编号和收件人数审计记录。</span></div></div>

    <form className="internal-form notification-broadcast-form" onSubmit={(event) => void submit(event)}>
      <header><Megaphone size={21} /><div><small>BROADCAST COMPOSER</small><h2>发布新消息</h2></div></header>
      <label><span>标题</span><input required maxLength={128} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="例如：平台服务维护通知" /></label>
      <label><span>正文</span><textarea required maxLength={5000} rows={6} value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} placeholder="填写用户需要看到的完整说明" /></label>
      <div className="form-pair">
        <label><span>消息类型</span><select value={form.notification_type} onChange={(event) => setForm({ ...form, notification_type: event.target.value as AdminNotificationBroadcast["notification_type"] })}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label><span>点击跳转（可选）</span><input maxLength={512} value={form.action_url} onChange={(event) => setForm({ ...form, action_url: event.target.value })} placeholder="/pages/notifications/index" /></label>
      </div>
      <label><span>过期时间（可选）</span><input type="datetime-local" value={form.expires_at} onChange={(event) => setForm({ ...form, expires_at: event.target.value })} /><small>到期后自动从首页、未读数和三端通知中心下架；留空表示长期有效。</small></label>
      <details className="notification-broadcast-advanced"><summary>可选：英文内容</summary><div className="form-pair"><label><span>英文标题</span><input maxLength={128} value={form.title_en} onChange={(event) => setForm({ ...form, title_en: event.target.value })} /></label><label><span>英文正文</span><textarea maxLength={5000} rows={3} value={form.content_en} onChange={(event) => setForm({ ...form, content_en: event.target.value })} /></label></div></details>
      <button className="commerce-primary" disabled={busy}>{busy ? "发布中…" : <><PaperPlaneTilt size={16} />发布给所有有效账号</>}</button>
    </form>

    {error && <div className="commerce-error">{error}</div>}
    {message && <div className="commerce-success">{message}</div>}

    <section className="notification-broadcast-history">
      <header><div><p>DELIVERY AUDIT</p><h2>最近发布记录</h2></div><button type="button" onClick={() => void load()} disabled={loading}><ClockCounterClockwise size={16} />{loading ? "读取中" : "刷新"}</button></header>
      {rows.length ? <div>{rows.map((row) => <article key={row.id}><span className="notification-broadcast-history__dot"><Bell size={17} /></span><div><header><strong>{row.title}</strong><small>{TYPE_LABELS[row.notification_type] || row.notification_type} · {formatDate(row.created_at)}</small></header><p>{row.content}</p><footer><span>已送达 {row.recipient_count} 个有效账号</span>{row.expires_at && <span>有效期至 {formatDate(row.expires_at)}</span>}{row.revoked_at && <span>撤销于 {formatDate(row.revoked_at)} · {row.revoke_reason}</span>}<code>{row.client_request_id}</code></footer></div><div className="notification-broadcast-history__actions"><b className={`status-chip status-chip--${row.status === "completed" ? "published" : row.status}`}>{statusLabel(row.status)}</b>{row.status === "completed" && <button type="button" className="commerce-danger" disabled={revokingId !== null} onClick={() => void revoke(row)}><Prohibit size={14} />{revokingId === row.id ? "撤销中…" : "撤销"}</button>}</div></article>)}</div> : <div className="commerce-empty"><Bell size={26} /><strong>{loading ? "正在读取发布记录…" : "还没有发布记录"}</strong></div>}
    </section>
  </section>;
}
