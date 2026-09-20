"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bell, CheckCircle, EnvelopeOpen, SlidersHorizontal } from "@phosphor-icons/react";
import { getNotificationPreferences, listNotifications, readAllNotifications, readNotification, updateNotificationPreferences, type Notice, type NotificationPreferences } from "@/lib/internal-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

export function NotificationWorkspace() {
  const [rows, setRows] = useState<Notice[]>([]); const [unreadOnly, setUnreadOnly] = useState(false); const [error, setError] = useState("");
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null); const [savingPreference, setSavingPreference] = useState("");
  const load = useCallback(async () => { try { const [notices, settings] = await Promise.all([listNotifications(unreadOnly), getNotificationPreferences()]); setRows(notices.data); setPreferences(settings.preferences); } catch (reason) { setError(errorMessage(reason)); } }, [unreadOnly]);
  useEffect(() => { void load(); }, [load]);
  async function act(action: () => Promise<unknown>) { setError(""); try { await action(); await load(); } catch (reason) { setError(errorMessage(reason)); } }
  async function togglePreference(key: keyof NotificationPreferences) { if (!preferences || typeof preferences[key] !== "boolean") return; setSavingPreference(key); setError(""); try { const result = await updateNotificationPreferences({ [key]: !preferences[key] }); setPreferences(result.preferences); } catch (reason) { setError(errorMessage(reason)); } finally { setSavingPreference(""); } }
  const unread = rows.filter((row) => !row.is_read).length;
  return <section className="workspace-page internal-workspace"><div className="workspace-page__head"><p>ACCOUNT / INBOX</p><h1>通知中心</h1><span>订单、团队、争议和审核消息统一保存在站内。</span></div>
    <div className="internal-toolbar"><div><button className={!unreadOnly ? "active" : ""} onClick={() => setUnreadOnly(false)}>全部</button><button className={unreadOnly ? "active" : ""} onClick={() => setUnreadOnly(true)}>未读</button></div><button disabled={!unread} onClick={() => void act(readAllNotifications)}><CheckCircle size={16}/>全部标为已读</button></div>
    {error && <div className="commerce-error">{error}</div>}{preferences && <section className="notification-preferences"><header><SlidersHorizontal size={20}/><div><small>DELIVERY PREFERENCES</small><h2>通知偏好</h2></div></header><div>{([['order_enabled','订单'],['device_enabled','设备'],['revenue_enabled','收益'],['wallet_enabled','钱包'],['system_enabled','系统']] as Array<[keyof NotificationPreferences,string]>).map(([key, label]) => <button type="button" className={preferences[key] ? "active" : ""} disabled={Boolean(savingPreference)} key={key} onClick={() => void togglePreference(key)}><span>{label}通知</span><i><b/></i><small>{savingPreference === key ? "保存中" : preferences[key] ? "已开启" : "已关闭"}</small></button>)}</div></section>}<div className="notice-stack">{rows.length === 0 ? <div className="internal-empty"><Bell size={30}/><strong>{unreadOnly ? "没有未读消息" : "还没有站内通知"}</strong><span>新的业务状态变化会显示在这里。</span></div> : rows.map((row) => <article className={row.is_read ? "read" : ""} key={row.id}><i/><div><header><span>{row.category}</span><time>{formatDate(row.created_at)}</time></header><h2>{row.title}</h2><p>{row.body}</p><footer>{row.action_path && <Link href={row.action_path}>查看相关内容</Link>}{!row.is_read && <button onClick={() => void act(() => readNotification(row.id))}><EnvelopeOpen size={15}/>标为已读</button>}</footer></div></article>)}</div>
  </section>;
}
