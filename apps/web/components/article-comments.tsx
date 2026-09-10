"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Flag, PaperPlaneTilt, Trash } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

type Viewer = { id: number; display_name: string };
type Comment = { id: number; content: string; status: "checking" | "visible" | "hidden" | "pending_manual"; violation_category?: string; created_at: string; is_own: boolean; author: { display_name: string; avatar_initial: string } };

function csrfToken() { return decodeURIComponent(document.cookie.split("; ").find((part) => part.startsWith("kai_csrf="))?.split("=").slice(1).join("=") || ""); }
function dateLabel(value: string, dateLocale: string) { return new Date(value).toLocaleString(dateLocale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }

export function ArticleComments({ articleId }: { articleId: number }) {
  const { t, dateLocale } = useI18n();
  const number = (value: number) => new Intl.NumberFormat(dateLocale).format(value);
  const [viewer, setViewer] = useState<Viewer | null>(null), [comments, setComments] = useState<Comment[]>([]), [count, setCount] = useState(0);
  const [sort, setSort] = useState<"latest" | "oldest">("latest"), [content, setContent] = useState(""), [editingId, setEditingId] = useState<number | null>(null), [message, setMessage] = useState(""), [loading, setLoading] = useState(true), [submitting, setSubmitting] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/public/news/${articleId}/comments?sort=${sort}`, { credentials: "include", cache: "no-store" });
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setComments(payload.data ?? []);
      setCount(payload.meta?.visible_count ?? 0);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("community.comments.error.load", "留言服务读取失败"));
    } finally {
      setLoading(false);
    }
  }, [articleId, sort, t]);
  useEffect(() => { fetch(`${apiBaseUrl}/api/v1/auth/me`, { credentials: "include", cache: "no-store" }).then((r) => r.ok ? r.json() : null).then((p) => setViewer(p?.data?.user ?? null)); }, []);
  useEffect(() => { void load(); }, [load]);

  async function submit() {
    if (!content.trim() || submitting) return;
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch(editingId ? `${apiBaseUrl}/api/v1/comments/${editingId}` : `${apiBaseUrl}/api/v1/news/${articleId}/comments`, { method: editingId ? "PUT" : "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: JSON.stringify({ content }) });
      if (!response.ok) throw new Error(await readApiError(response));
      setContent("");
      setEditingId(null);
      setMessage(t("community.comments.submitted", "留言已提交，正在复审。"));
      await load();
      window.setTimeout(() => void load(), 900);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t("community.comments.error.publish", "发布失败"));
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: number) {
    const response = await fetch(`${apiBaseUrl}/api/v1/comments/${id}`, { method: "DELETE", credentials: "include", headers: { "X-CSRF-Token": csrfToken() } });
    if (response.ok) await load();
    else setMessage(await readApiError(response));
  }

  async function report(id: number) {
    const response = await fetch(`${apiBaseUrl}/api/v1/comments/${id}/reports`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: JSON.stringify({ reason: "其他不当内容" }) });
    setMessage(response.ok ? t("community.comments.reported", "举报已提交，感谢你的反馈。") : await readApiError(response));
  }

  return <section className="article-comments" id="comments">
    <header>
      <div><p className="hero-eyebrow">{t("community.comments.eyebrow", "DISCUSSION")}</p><h2>{t("community.comments.title", "留言讨论")} <span>({number(count)})</span></h2></div>
      <div className="comment-sort" aria-label={t("community.comments.sortAria", "留言排序")}><button className={sort === "latest" ? "active" : ""} onClick={() => setSort("latest")}>{t("community.comments.sort.latest", "最新")}</button><button className={sort === "oldest" ? "active" : ""} onClick={() => setSort("oldest")}>{t("community.comments.sort.oldest", "最早")}</button></div>
    </header>
    {viewer ? <div className="comment-composer">
      <textarea maxLength={500} value={content} onChange={(event) => setContent(event.target.value)} placeholder={t("community.comments.placeholder", "分享你对算力、GPU 或行业趋势的看法……")} aria-label={t("community.comments.inputAria", "留言内容")} />
      <footer><span>{t("community.comments.characterCount", "{count}/{maximum} · 仅支持纯文字", { count: number(content.length), maximum: number(500) })}{editingId ? t("community.comments.editing", " · 正在修改隐藏留言") : ""}</span><button onClick={() => void submit()} disabled={!content.trim() || submitting}><PaperPlaneTilt size={16} />{submitting ? t("community.comments.publishing", "发布中") : editingId ? t("community.comments.editAndResubmit", "修改并重提") : t("community.comments.publish", "发布留言")}</button></footer>
    </div> : <div className="comment-login"><p>{t("community.comments.login.description", "登录后参与留言，与其他用户讨论算力市场。")}</p><Link href={`/login?return_to=/community/news/${articleId}`}>{t("community.comments.login.action", "登录后参与留言")}</Link></div>}
    {message && <p className="comment-message" data-i18n-skip>{message}</p>}
    <div className="comment-list">{loading ? <p className="comment-empty" role="status">{t("community.comments.loading", "留言正在加载……")}</p> : comments.length === 0 ? <p className="comment-empty">{t("community.comments.empty", "还没有留言，登录后参与讨论。")}</p> : comments.map((comment) => <article className={`comment-card ${comment.status === "hidden" || comment.status === "pending_manual" ? "private" : ""}`} key={comment.id}>
      <div className="comment-avatar" data-i18n-skip>{comment.author.avatar_initial}</div>
      <div><header><strong data-i18n-skip>{comment.author.display_name}</strong><time>{dateLabel(comment.created_at, dateLocale)}</time>{comment.is_own && comment.status !== "visible" && <span>{comment.status === "checking" ? t("community.comments.reviewing", "正在复审") : t("community.comments.private", "仅自己可见")}</span>}</header><p data-i18n-skip>{comment.content}</p>{comment.is_own && comment.status === "hidden" && <small>{t("community.comments.hidden", "该留言可能违反社区规则，暂不对其他用户展示。")}{comment.violation_category ? <> {t("community.comments.reason", "原因：")}<span data-i18n-skip>{comment.violation_category}</span></> : ""}</small>}<footer>{comment.is_own ? <>{comment.status === "hidden" && <button onClick={() => { setEditingId(comment.id); setContent(comment.content); document.getElementById("comments")?.scrollIntoView({ behavior: "smooth" }); }}>{t("community.comments.editAndResubmit", "修改并重提")}</button>}<button onClick={() => void remove(comment.id)}><Trash size={14} />{t("community.comments.delete", "删除")}</button></> : viewer ? <button onClick={() => void report(comment.id)}><Flag size={14} />{t("community.comments.report", "举报")}</button> : null}</footer></div>
    </article>)}</div>
  </section>;
}
