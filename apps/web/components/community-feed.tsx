"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpRight, ChatCircle, Heart, ImageSquare, MagnifyingGlass, PaperPlaneTilt, Play, Plus, ShareNetwork, UserPlus, VideoCamera } from "@phosphor-icons/react";
import { ApiError } from "@/lib/api";
import {
  communityMediaUrl,
  createCommunityComment,
  createCommunityPost,
  getCommunityComments,
  getCommunityPosts,
  toggleCommunityFollow,
  toggleCommunityLike,
  uploadCommunityMedia,
  type CommunityComment,
  type CommunityPost,
} from "@/lib/mobile-community-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { acquireCommunityAction, releaseCommunityAction } from "@/lib/community-action-lock";
import {
  COMMUNITY_POST_MAX_LENGTH,
  COMMUNITY_MEDIA_LIMIT_TEXT,
  communityDisplayText,
  communityMediaUploadError,
  communityShareText,
  isCommunityVideoFile,
  uploadCommunityMediaBatch,
} from "@/lib/community-ui";

const tabs = [["recommend", "推荐"], ["latest", "最新"], ["follow", "关注"], ["video", "视频"]] as const;

type PublishProgress = {
  phase: "idle" | "preparing" | "uploading" | "processing" | "publishing";
  percent: number;
  current: number;
  total: number;
  fileName: string;
  video: boolean;
};

const idlePublishProgress: PublishProgress = { phase: "idle", percent: 0, current: 0, total: 0, fileName: "", video: false };

function formatUploadBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function publishProgressText(progress: PublishProgress) {
  if (progress.phase === "preparing") return "正在检查视频时长与格式…";
  if (progress.phase === "uploading") return `正在上传第 ${progress.current}/${progress.total} 个文件 · ${progress.percent}%`;
  if (progress.phase === "processing") return `第 ${progress.current}/${progress.total} 个文件已上传，服务器正在${progress.video ? "转换兼容视频" : "处理文件"}…`;
  if (progress.phase === "publishing") return "媒体处理完成，正在发布动态…";
  return "";
}

function publishButtonText(progress: PublishProgress) {
  if (progress.phase === "preparing") return "检查中…";
  if (progress.phase === "uploading") return `上传 ${progress.percent}%`;
  if (progress.phase === "processing") return "处理中…";
  if (progress.phase === "publishing") return "发布中…";
  return "发布";
}

function readVideoDuration(file: File) {
  return new Promise<number>((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      const duration = Math.max(1, Math.round(video.duration || 0));
      URL.revokeObjectURL(url);
      resolve(duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("无法读取视频时长，请更换视频文件"));
    };
    video.src = url;
  });
}

function postSourceHref(row: CommunityPost) {
  return row.canonical_url || row.source_url || row.video_url || "";
}

function ExternalVideoPreview({ row }: { row: CommunityPost }) {
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const href = postSourceHref(row);
  if (!href) return null;
  return (
    <a className="community-video-cover" href={href} target="_blank" rel="noreferrer" aria-label={`观看视频：${communityDisplayText(row.content, row.source_key)}`}>
      {!thumbnailFailed && row.thumbnail_url ? (
        <img src={row.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setThumbnailFailed(true)} />
      ) : (
        <span className="community-video-cover__fallback"><VideoCamera size={42} /><small>VIDEO SIGNAL</small></span>
      )}
      <span className="community-video-cover__shade" />
      <span className="community-video-cover__play"><Play size={22} weight="fill" /></span>
      <span className="community-video-cover__label">官方视频</span>
      <span className="community-video-cover__source">{communityDisplayText(row.source_name, row.source_key) || "在来源网站观看"}<ArrowUpRight size={15} /></span>
    </a>
  );
}

type CommunityCardProps = {
  row: CommunityPost;
  featured: boolean;
  busy: ReadonlySet<string>;
  openComments: number | null;
  comments: Record<number, CommunityComment[]>;
  comment: string;
  onCommentChange: (value: string) => void;
  onLike: (row: CommunityPost) => void;
  onFollow: (row: CommunityPost) => void;
  onShare: (row: CommunityPost) => void;
  onShowComments: (id: number) => void;
  onSubmitComment: (event: FormEvent, id: number) => void;
};

function CommunityCard({ row, featured, busy, openComments, comments, comment, onCommentChange, onLike, onFollow, onShare, onShowComments, onSubmitComment }: CommunityCardProps) {
  const externalVideo = !row.video && (row.content_type === "video" || Boolean(row.video_url));
  const sourceName = communityDisplayText(row.source_name || row.source_author, row.source_key);
  const authorName = communityDisplayText(row.author_name || row.source_author || row.source_name, row.source_key) || "社区用户";
  const content = communityDisplayText(row.content, row.source_key);
  const summary = communityDisplayText(row.summary, row.source_key);
  return (
    <article className={`community-post-card${featured ? " community-post-card--featured" : ""}${externalVideo ? " community-post-card--video" : ""}`}>
      <header className="community-post-card__author">
        <div className="community-user-avatar">
          {row.author_avatar ? <img src={row.author_avatar.startsWith("/user/avatars/") ? `/api/v1/canonical${row.author_avatar}` : row.author_avatar} alt="" /> : communityDisplayText(row.author_name || "匿", row.source_key).slice(0, 1)}
        </div>
        <span><strong>{authorName}</strong><small>{formatDate(row.source_published_at || row.created_at)}{row.topic ? ` · ${row.topic}` : ""}</small></span>
        {!row.is_own && <button className={row.is_following ? "following" : ""} disabled={busy.has(`follow-${row.id}`)} onClick={() => onFollow(row)}><UserPlus size={15} />{row.is_following ? "已关注" : "关注"}</button>}
      </header>

      <div className="community-post-card__copy">
        {row.origin === "aggregated" && <div className="community-source-line"><span>自动资讯</span><b>{sourceName || "公开来源"}</b></div>}
        <p>{content}</p>
        {summary && summary !== content && <small className="community-post-summary">{summary}</small>}
      </div>

      <div className="community-post-card__media">
        {row.images?.length ? <div className={`community-media-grid${row.images.length === 1 ? " is-single" : ""}`}>{row.images.map((image, index) => <img src={communityMediaUrl(image)} alt="动态图片" loading="lazy" key={`${image}-${index}`} />)}</div> : null}
        {row.video && <video className="community-video-player" controls preload="metadata" src={communityMediaUrl(row.video)} />}
        {externalVideo && <ExternalVideoPreview row={row} />}
      </div>

      <footer className="community-post-card__actions">
        <button className={row.is_liked ? "liked" : ""} disabled={busy.has(`like-${row.id}`)} onClick={() => onLike(row)}><Heart size={18} weight={row.is_liked ? "fill" : "regular"} />{row.likes}</button>
        <button onClick={() => onShowComments(row.id)}><ChatCircle size={18} />{row.comments}</button>
        <button disabled={busy.has(`share-${row.id}`)} onClick={() => onShare(row)}><ShareNetwork size={18} />{busy.has(`share-${row.id}`) ? "复制中…" : `分享${row.shares ? ` ${row.shares}` : ""}`}</button>
        {row.source_url && <a href={row.source_url} target="_blank" rel="noreferrer">查看来源<ArrowUpRight size={15} /></a>}
      </footer>

      {openComments === row.id && <section className="community-comments">
        {comments[row.id]?.length ? comments[row.id].map((item) => <article key={item.id}><strong>{item.author_name || "社区用户"}</strong><p>{item.content}</p><time>{formatDate(item.created_at)}</time></article>) : <p className="community-comments__empty">还没有评论，写下第一条。</p>}
        <form onSubmit={(event) => onSubmitComment(event, row.id)}><input maxLength={500} value={comment} onChange={(event) => onCommentChange(event.target.value)} placeholder="写下评论…" /><button disabled={busy.has(`comment-${row.id}`)}>发送</button></form>
      </section>}
    </article>
  );
}

export function CommunityFeed({ initialQuery = "", initialPage = 1 }: { initialCategory?: string; initialQuery?: string; initialPage?: number }) {
  const [rows, setRows] = useState<CommunityPost[]>([]);
  const [tab, setTab] = useState<(typeof tabs)[number][0]>("recommend");
  const [query, setQuery] = useState(initialQuery);
  const [page, setPage] = useState(initialPage);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loginRequired, setLoginRequired] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [composerOpen, setComposerOpen] = useState(false);
  const [draft, setDraft] = useState({ content: "", topic: "" });
  const [files, setFiles] = useState<File[]>([]);
  const [publishProgress, setPublishProgress] = useState<PublishProgress>(idlePublishProgress);
  const fileInput = useRef<HTMLInputElement>(null);
  const pendingActions = useRef(new Set<string>());
  const [busy, setBusy] = useState<ReadonlySet<string>>(() => new Set());
  const [openComments, setOpenComments] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, CommunityComment[]>>({});
  const [commentDrafts, setCommentDrafts] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getCommunityPosts(tab, page, query.trim());
      setRows(result.items);
      setTotal(result.total);
      setLoginRequired(false);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setLoginRequired(true);
      else setError(errorMessage(reason));
    } finally { setLoading(false); }
  }, [page, query, tab]);

  useEffect(() => { void load(); }, [load]);

  function beginAction(key: string): boolean {
    if (!acquireCommunityAction(pendingActions.current, key)) return false;
    setBusy(new Set(pendingActions.current));
    return true;
  }

  function finishAction(key: string) {
    releaseCommunityAction(pendingActions.current, key);
    setBusy(new Set(pendingActions.current));
    if (key === "publish") setPublishProgress(idlePublishProgress);
  }

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (!draft.content.trim()) return;
    const validationError = communityMediaUploadError(files);
    if (validationError) { setError(validationError); return; }
    const action = "publish";
    if (!beginAction(action)) return;
    setError("");
    try {
      const videoFile = files.find(isCommunityVideoFile);
      if (videoFile && files.length > 1) throw new Error("视频不能与其他图片或视频同时发布");
      if (videoFile) setPublishProgress({ phase: "preparing", percent: 0, current: 1, total: 1, fileName: videoFile.name, video: true });
      const inputDuration = videoFile ? await readVideoDuration(videoFile) : undefined;
      if (inputDuration && inputDuration > 300) throw new Error("社区视频不能超过 5 分钟");
      let completed = 0;
      const uploaded = await uploadCommunityMediaBatch(files, async (file) => {
        const current = completed + 1;
        const video = isCommunityVideoFile(file);
        setPublishProgress({ phase: "uploading", percent: 0, current, total: files.length, fileName: file.name, video });
        const result = await uploadCommunityMedia(file, (progress) => {
          setPublishProgress({ phase: progress.phase, percent: progress.percent, current, total: files.length, fileName: file.name, video });
        });
        completed += 1;
        return result;
      });
      const images = uploaded.filter((item) => item.kind === "image").map((item) => item.url);
      const video = uploaded.find((item) => item.kind === "video");
      if (video && (video.content_type !== "video/mp4" || !video.url.toLowerCase().endsWith(".mp4") || !video.standardized || !video.duration)) {
        throw new Error("视频兼容处理未完成，请重新上传");
      }
      setPublishProgress({ phase: "publishing", percent: 100, current: files.length, total: files.length, fileName: "", video: Boolean(video) });
      await createCommunityPost({ content: draft.content.trim(), topic: draft.topic.trim() || undefined, images: images.length ? images : undefined, video: video?.url, video_duration: video?.duration || undefined });
      setDraft({ content: "", topic: "" }); setFiles([]); if (fileInput.current) fileInput.current.value = ""; setComposerOpen(false); setPage(1); await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { finishAction(action); }
  }

  async function like(row: CommunityPost) {
    const action = `like-${row.id}`;
    if (!beginAction(action)) return;
    try { const result = await toggleCommunityLike(row.id); setRows((items) => items.map((item) => item.id === row.id ? { ...item, likes: result.likes, is_liked: result.liked } : item)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { finishAction(action); }
  }

  async function follow(row: CommunityPost) {
    const action = `follow-${row.id}`;
    if (!beginAction(action)) return;
    try { const result = await toggleCommunityFollow(row.user_id); setRows((items) => items.map((item) => item.user_id === row.user_id ? { ...item, is_following: result.following } : item)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { finishAction(action); }
  }

  async function share(row: CommunityPost) {
    const text = communityShareText(row);
    if (!text) return;
    const action = `share-${row.id}`;
    if (!beginAction(action)) return;
    setError(""); setMessage("");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const field = document.createElement("textarea");
        field.value = text;
        field.setAttribute("readonly", "");
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.appendChild(field);
        field.select();
        const copied = document.execCommand("copy");
        field.remove();
        if (!copied) throw new Error("浏览器未允许复制，请手动复制动态内容");
      }
      setMessage("动态内容已复制，可以粘贴分享");
    } catch (reason) { setError(errorMessage(reason)); }
    finally { finishAction(action); }
  }

  async function showComments(id: number) {
    if (openComments === id) { setOpenComments(null); return; }
    setOpenComments(id);
    try { const next = await getCommunityComments(id); setComments((value) => ({ ...value, [id]: next })); }
    catch (reason) { setError(errorMessage(reason)); }
  }

  async function submitComment(event: FormEvent, id: number) {
    event.preventDefault();
    const value = (commentDrafts[id] || "").trim();
    if (!value) return;
    const action = `comment-${id}`;
    if (!beginAction(action)) return;
    try {
      await createCommunityComment(id, value);
      setCommentDrafts((drafts) => {
        const next = { ...drafts };
        delete next[id];
        return next;
      });
      const next = await getCommunityComments(id);
      setComments((items) => ({ ...items, [id]: next }));
      setRows((items) => items.map((item) => item.id === id ? { ...item, comments: next.length } : item));
    } catch (reason) { setError(errorMessage(reason)); }
    finally { finishAction(action); }
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    if (page === 1) void load(); else setPage(1);
  }

  const publishing = busy.has("publish");
  const selectedBytes = files.reduce((totalBytes, file) => totalBytes + file.size, 0);

  if (loginRequired) return <div className="community-login"><ChatCircle size={38}/><h2>登录后进入算力社区</h2><p>登录后可发布动态、关注、点赞和评论。</p><Link href="/login?return_to=/community">登录</Link></div>;

  return <section className="mobile-community-feed">
    <div className="community-commandbar">
      <form className="community-search" onSubmit={submitSearch}><MagnifyingGlass size={21}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索动态、话题或作者" /></form>
      <button className="community-publish-button" type="button" onClick={() => setComposerOpen((value) => !value)}><Plus size={17}/>{composerOpen ? "收起发布" : "发布动态"}</button>
      <div className="community-commandbar__meta"><span>POSTS</span><strong>{total}</strong><small>条社区动态</small></div>
    </div>

    <div className="mobile-community-tabs" role="tablist" aria-label="社区内容筛选">{tabs.map(([value, label]) => <button type="button" role="tab" aria-selected={tab === value} className={tab === value ? "active" : ""} key={value} onClick={() => { setTab(value); setPage(1); }}>{label}</button>)}</div>

    {composerOpen && <form className="community-composer" onSubmit={publish}>
      <header><PaperPlaneTilt size={20}/><div><small>CREATE POST</small><h2>发布社区动态</h2></div></header>
      <input disabled={publishing} maxLength={40} value={draft.topic} onChange={(event) => setDraft({ ...draft, topic: event.target.value })} placeholder="话题（可选）" />
      <textarea disabled={publishing} required maxLength={COMMUNITY_POST_MAX_LENGTH} value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} placeholder="分享算力设备、行情或使用经验…" />
      {files.length > 0 && <div className="community-upload-selection"><div><strong>已选择 {files.length} 个文件 · {formatUploadBytes(selectedBytes)}</strong><small>{files.map((file) => file.name).join("、")}</small></div><button type="button" disabled={publishing} onClick={() => { setFiles([]); if (fileInput.current) fileInput.current.value = ""; }}>清除</button></div>}
      {publishProgress.phase !== "idle" && <div className="community-upload-progress" role="status" aria-live="polite"><div><strong>{publishProgressText(publishProgress)}</strong><small>{publishProgress.fileName || "正在写入动态"}</small></div><span><i style={{ width: `${publishProgress.percent}%` }}/></span></div>}
      <footer><label aria-disabled={publishing}><ImageSquare size={16}/>添加图片或视频（{COMMUNITY_MEDIA_LIMIT_TEXT}）<input ref={fileInput} disabled={publishing} hidden multiple type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm,.mov" onChange={(event) => {
        const selected = Array.from(event.currentTarget.files || []);
        const validationError = communityMediaUploadError(selected);
        if (validationError) { setError(validationError); event.currentTarget.value = ""; return; }
        setError(""); setFiles(selected);
      }}/></label><span>{files.length ? `${draft.content.length}/${COMMUNITY_POST_MAX_LENGTH} 字` : `${draft.content.length}/${COMMUNITY_POST_MAX_LENGTH}`}</span><button disabled={publishing}>{publishButtonText(publishProgress)}</button></footer>
    </form>}

    {error && <div className="commerce-error">{error}</div>}
    {message && <div className="commerce-success">{message}</div>}
    {loading ? <div className="news-skeleton"><span/><span/><span/></div> : <div className="mobile-community-list">{rows.length ? rows.map((row, index) => <CommunityCard key={row.id} row={row} featured={index === 0 && page === 1} busy={busy} openComments={openComments} comments={comments} comment={commentDrafts[row.id] || ""} onCommentChange={(value) => setCommentDrafts((drafts) => ({ ...drafts, [row.id]: value }))} onLike={(item) => void like(item)} onFollow={(item) => void follow(item)} onShare={(item) => void share(item)} onShowComments={(id) => void showComments(id)} onSubmitComment={(event, id) => void submitComment(event, id)} />) : <div className="data-empty"><ChatCircle size={30}/><strong>当前没有动态</strong><p>切换标签或发布第一条内容。</p></div>}</div>}

    {total > 10 && <nav className="community-page-nav"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</button><span>第 {page} 页</span><button disabled={page * 10 >= total} onClick={() => setPage((value) => value + 1)}>下一页</button></nav>}
  </section>;
}
