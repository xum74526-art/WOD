"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ChatCircleDots, PaperPlaneTilt, Ticket, UserCircle } from "@phosphor-icons/react";
import { ApiError } from "@/lib/api";
import { createSupportTicket, getSupportSession, sendSupportMessage, type SupportSession } from "@/lib/mobile-support-api";
import { formatDate } from "@/lib/commerce-ui";
import { useI18n } from "@/components/locale-root";

const ticketStatuses: Record<string, { key: string; zh: string }> = {
  pending_unassigned: { key: "support.status.pending", zh: "待分配" },
  assigned: { key: "support.status.assigned", zh: "处理中" },
  resolved: { key: "support.status.resolved", zh: "已解决" },
  closed: { key: "support.status.closed", zh: "已关闭" },
};
export function MobileSupportWorkspace() {
  const { locale, t, dateLocale } = useI18n();
  const [session, setSession] = useState<SupportSession | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loginRequired, setLoginRequired] = useState(false);
  const [ticketSource, setTicketSource] = useState<number | null>(null);
  const [ticket, setTicket] = useState({
    subject: "",
    description: "",
    category: "other",
  });
  const endRef = useRef<HTMLDivElement>(null);
  const load = useCallback(async () => {
    setError("");
    try {
      setSession(await getSupportSession(locale === "en" ? "en" : "zh"));
      setLoginRequired(false);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setLoginRequired(true);
      else setError(t("support.error", "客服请求未完成，请稍后重试。"));
    }
  }, [locale, t]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length]);
  async function send(event: FormEvent) {
    event.preventDefault();
    const value = message.trim();
    if (!value || busy) return;
    setBusy(true);
    setError("");
    try {
      await sendSupportMessage(value, session?.conversation_id, locale === "en" ? "en" : "zh");
      setMessage("");
      await load();
    } catch {
      setError(t("support.error", "客服请求未完成，请稍后重试。"));
    } finally {
      setBusy(false);
    }
  }
  async function submitTicket(event: FormEvent) {
    event.preventDefault();
    if (!session?.conversation_id) return;
    setBusy(true);
    setError("");
    try {
      await createSupportTicket({
        conversation_id: session.conversation_id,
        source_message_id: ticketSource || undefined,
        ...ticket,
      }, locale === "en" ? "en" : "zh");
      setTicketSource(null);
      setTicket({ subject: "", description: "", category: "other" });
      await load();
    } catch {
      setError(t("support.error", "客服请求未完成，请稍后重试。"));
    } finally {
      setBusy(false);
    }
  }
  if (loginRequired)
    return (
      <section className="support-login">
        <ChatCircleDots size={38} />
        <h1>{t("support.loginTitle", "登录后使用在线客服")}</h1>
        <p>{t("support.loginDescription", "客服会话和工单将保存到当前账户。")}</p>
        <Link href="/login?return_to=/support">{t("support.loginAction", "登录")}</Link>
      </section>
    );
  return (
    <section className="support-workspace">
      <header>
        <p className="hero-eyebrow">ACCOUNT SUPPORT</p>
        <h1>{t("support.title", "帮助与客服")}</h1>
        <span>{!session ? t("support.connecting", "正在连接在线客服…") : session.service_mode === "ai_assisted" ? t("support.aiOnline", "智能客服在线，可查询常见问题并创建客服工单。") : t("support.selfServiceOnline", "自助客服在线，可查询常见问题并创建客服工单。")}</span>
      </header>
      {error && <div className="commerce-error">{error}</div>}
      <div className="support-console">
        <main>
          <div className="support-messages">
            {session?.messages.length ? (
              session.messages.map((item) => (
                <article className={item.role === "user" ? "user" : "assistant"} key={item.id}>
                  <span>{item.role === "user" ? <UserCircle size={18} /> : <ChatCircleDots size={18} />}</span>
                  <div>
                    <small>
                      {item.role === "user" ? t("support.me", "我") : t("support.assistant", "北斗 kai 自助客服")} · {formatDate(item.created_at, dateLocale)}
                    </small>
                    <p>{item.content}</p>
                    {item.can_create_ticket && (
                      <button
                        onClick={() => {
                          setTicketSource(item.id);
                          setTicket((value) => ({
                            ...value,
                            description: item.content,
                          }));
                        }}
                      >
                        {t("support.createTicket", "转为客服工单")}
                      </button>
                    )}
                  </div>
                </article>
              ))
            ) : (
              <div className="support-welcome">
                <ChatCircleDots size={34} />
                <strong>{t("support.welcome", "你好，需要什么帮助？")}</strong>
                <span>{t("support.welcomeDescription", "可以询问充值、提现、订单、设备或账户问题。")}</span>
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form className="support-composer" onSubmit={send}>
            <textarea maxLength={1000} value={message} onChange={(event) => setMessage(event.target.value)} placeholder={t("support.inputPlaceholder", "输入你的问题…")} />
            <button disabled={busy || !message.trim()}>
              <PaperPlaneTilt size={18} />
              {busy ? t("support.sending", "发送中") : t("support.send", "发送")}
            </button>
          </form>
        </main>
        <aside>
          <header>
            <Ticket size={20} />
            <div>
              <small>SUPPORT TICKETS</small>
              <h2>{t("support.myTickets", "我的工单")}</h2>
            </div>
          </header>
          {ticketSource && (
            <form onSubmit={submitTicket}>
              <label>
                {t("support.subject", "主题")}
                <input required maxLength={120} value={ticket.subject} onChange={(event) => setTicket({ ...ticket, subject: event.target.value })} />
              </label>
              <label>
                {t("support.description", "问题描述")}
                <textarea required maxLength={2000} value={ticket.description} onChange={(event) => setTicket({ ...ticket, description: event.target.value })} />
              </label>
              <label>
                {t("support.category", "分类")}
                <select value={ticket.category} onChange={(event) => setTicket({ ...ticket, category: event.target.value })}>
                  <option value="order">{t("support.category.order", "订单")}</option>
                  <option value="payment">{t("support.category.payment", "支付")}</option>
                  <option value="device">{t("support.category.device", "设备")}</option>
                  <option value="account">{t("support.category.account", "账户")}</option>
                  <option value="other">{t("support.category.other", "其他")}</option>
                </select>
              </label>
              <div>
                <button type="button" onClick={() => setTicketSource(null)}>
                  {t("support.cancel", "取消")}
                </button>
                <button disabled={busy}>{t("support.submitTicket", "提交工单")}</button>
              </div>
            </form>
          )}
          {session?.tickets.length ? (
            session.tickets.map((item) => (
              <article key={item.id}>
                <span>
                  <strong>{item.subject}</strong>
                  <small>
                    {item.ticket_no} · {formatDate(item.created_at, dateLocale)}
                  </small>
                </span>
                <b>{ticketStatuses[item.status] ? t(ticketStatuses[item.status].key, ticketStatuses[item.status].zh) : item.status}</b>
              </article>
            ))
          ) : (
            <div className="mobile-inline-empty">{t("support.emptyTickets", "暂无客服工单")}</div>
          )}
        </aside>
      </div>
    </section>
  );
}
