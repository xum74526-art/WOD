"use client";

import { useCallback, useEffect, useState } from "react";
import { apiBaseUrl, readApiError } from "@/lib/api";

type Item = { id: number; content: string; status: string; violation_category?: string; created_at: string; report_count?: number; author: { display_name: string } };
function csrfToken() { return decodeURIComponent(document.cookie.split("; ").find((part) => part.startsWith("kai_csrf="))?.split("=").slice(1).join("=") || ""); }

export function CommentModeration() {
  const [items, setItems] = useState<Item[]>([]), [status, setStatus] = useState(""), [message, setMessage] = useState("正在读取留言……");
  const load = useCallback(async () => {
    const params = status ? `?status=${status}` : "";
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/admin/comments${params}`, {
        credentials: "include",
        headers: { "X-CSRF-Token": csrfToken() },
        cache: "no-store",
      });
      if (!response.ok) {
        setMessage(await readApiError(response));
        return;
      }
      const payload = await response.json();
      setItems(payload.data ?? []);
      setMessage("");
    } catch {
      setMessage("暂时无法连接服务，请稍后重试");
    }
  }, [status]);
  useEffect(() => { void load(); }, [load]);
  async function update(id: number, next: string) {
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/admin/comments/${id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
        body: JSON.stringify({ status: next, violation_category: next === "hidden" ? "其他不当内容" : null }),
      });
      if (response.ok) await load();
      else setMessage(await readApiError(response));
    } catch {
      setMessage("暂时无法连接服务，请稍后重试");
    }
  }
  return <section className="moderation-panel"><header><div><p className="hero-eyebrow">COMMUNITY CONTROL</p><h1>留言管理</h1><p>审核、隐藏、恢复或删除资讯留言。</p></div><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option><option value="checking">复审中</option><option value="visible">公开</option><option value="hidden">已隐藏</option><option value="pending_manual">人工复核</option><option value="deleted">已删除</option></select></header>{message && <div className="data-empty"><strong>{message}</strong></div>}<div className="moderation-list">{items.map((item) => <article key={item.id}><header><strong>{item.author.display_name}</strong><span>{item.status}</span><small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></header><p>{item.content}</p><footer><span>举报 {item.report_count ?? 0} 次{item.violation_category ? ` · ${item.violation_category}` : ""}</span><div><button onClick={() => void update(item.id, "visible")}>恢复公开</button><button onClick={() => void update(item.id, "pending_manual")}>人工复核</button><button onClick={() => void update(item.id, "hidden")}>隐藏</button><button className="danger" onClick={() => void update(item.id, "deleted")}>删除</button></div></footer></article>)}</div></section>;
}
