"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";

type ReportStatus = "pending" | "resolved" | "dismissed" | "";
type Resolution = "dismissed" | "content_removed" | "user_restricted";
type ReportItem = {
  id: number;
  target_type: "post" | "comment" | "user";
  target_id: number;
  reason: string;
  details?: string | null;
  status: string;
  resolution?: string | null;
  resolution_note?: string | null;
  reporter?: { id: number; username: string } | null;
  target: {
    exists: boolean;
    author?: { id: number; username: string } | null;
    excerpt?: string | null;
    moderation_status?: string | null;
  };
  created_platform: string;
  created_at: string;
  reviewed_at?: string | null;
};

type ReportPage = { total: number; page: number; page_size: number; items: ReportItem[] };

const targetNames: Record<ReportItem["target_type"], string> = {
  post: "动态",
  comment: "评论",
  user: "用户",
};

export function CommentModeration() {
  const [items, setItems] = useState<ReportItem[]>([]);
  const [status, setStatus] = useState<ReportStatus>("pending");
  const [message, setMessage] = useState("正在读取举报队列……");
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    setMessage("正在读取举报队列……");
    try {
      const query = new URLSearchParams({ page: "1", page_size: "100", status });
      const result = await apiRequest<ReportPage>(path(`/admin/community/reports?${query}`));
      setItems(result.items);
      setMessage(result.items.length ? "" : "当前没有符合条件的举报");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "暂时无法连接服务，请稍后重试");
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  async function review(item: ReportItem, resolution: Resolution) {
    const labels: Record<Resolution, string> = {
      dismissed: "驳回举报并恢复显示",
      content_removed: "下架被举报内容",
      user_restricted: "限制账号并下架其内容",
    };
    if (!window.confirm(`确定要${labels[resolution]}吗？`)) return;
    const note = window.prompt("处置备注（可留空）", "");
    if (note === null) return;
    setBusy(item.id);
    setMessage("");
    try {
      await apiRequest(path(`/admin/community/reports/${item.id}`), {
        method: "PATCH",
        body: JSON.stringify({ resolution, note: note.trim() || null }),
      });
      await load();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "处置失败，请稍后重试");
    } finally {
      setBusy(null);
    }
  }

  return <section className="moderation-panel">
    <header>
      <div><p className="hero-eyebrow">COMMUNITY SAFETY</p><h1>社区举报与内容治理</h1><p>审核动态、评论和用户举报；每次处置都会记录审核人、时间与结果。</p></div>
      <select value={status} onChange={(event) => setStatus(event.target.value as ReportStatus)}>
        <option value="pending">待处理</option>
        <option value="resolved">已处理</option>
        <option value="dismissed">已驳回</option>
        <option value="">全部状态</option>
      </select>
    </header>
    {message && <div className="data-empty"><strong>{message}</strong></div>}
    <div className="moderation-list">{items.map((item) => <article key={item.id}>
      <header>
        <strong>{targetNames[item.target_type]} #{item.target_id}</strong>
        <span>{item.status}</span>
        <span>{item.reason}</span>
        <small>{new Date(item.created_at).toLocaleString("zh-CN")}</small>
      </header>
      <p>{item.target.excerpt || (item.target.author ? `账号：${item.target.author.username}` : "举报对象已不存在")}</p>
      {item.details && <p>举报补充：{item.details}</p>}
      <footer>
        <span>举报人：{item.reporter?.username || `#${item.reporter?.id || "未知"}`} · 作者：{item.target.author?.username || "未知"} · 来源：{item.created_platform}</span>
        {item.status === "pending" && <div>
          <button disabled={busy === item.id} onClick={() => void review(item, "dismissed")}>驳回</button>
          {item.target_type !== "user" && <button className="danger" disabled={busy === item.id} onClick={() => void review(item, "content_removed")}>下架内容</button>}
          <button className="danger" disabled={busy === item.id} onClick={() => void review(item, "user_restricted")}>限制账号</button>
        </div>}
      </footer>
    </article>)}</div>
  </section>;
}
