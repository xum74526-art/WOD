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
  setCommunityFollow,
  setCommunityLike,
  uploadCommunityMedia,
  type CommunityComment,
  type CommunityPost,
} from "@/lib/mobile-community-api";
import { formatDate } from "@/lib/commerce-ui";
import { acquireCommunityAction, releaseCommunityAction } from "@/lib/community-action-lock";
import {
  communityCommentIntentSignature,
  ensureCommunityCommentIntent,
  type CommunityCommentIntent,
} from "@/lib/web-business-contract";
import { useI18n } from "@/components/locale-root";
import { localizePersonName } from "@/lib/person-name";
import {
  COMMUNITY_POST_MAX_LENGTH,
  COMMUNITY_MEDIA_LIMIT_TEXT,
  communityDisplayText,
  communityMediaUploadError,
  communityShareText,
  isCommunityVideoFile,
  uploadCommunityMediaBatch,
} from "@/lib/community-ui";

const tabs = [
  { value: "recommend", key: "community.feed.tab.recommend", fallback: "推荐" },
  { value: "latest", key: "community.feed.tab.latest", fallback: "最新" },
  { value: "follow", key: "community.feed.tab.follow", fallback: "关注" },
  { value: "video", key: "community.feed.tab.video", fallback: "视频" },
] as const;

type Translate = ReturnType<typeof useI18n>["t"];

type PublishProgress = {
  phase: "idle" | "preparing" | "uploading" | "processing" | "publishing";
  percent: number;
  current: number;
  total: number;
  fileName: string;
  video: boolean;
};

const idlePublishProgress: PublishProgress = { phase: "idle", percent: 0, current: 0, total: 0, fileName: "", video: false };

function formatNumber(value: number, dateLocale: string, options?: Intl.NumberFormatOptions) {
  return new Intl.NumberFormat(dateLocale, options).format(value);
}

function formatUploadBytes(bytes: number, dateLocale: string) {
  if (bytes < 1024 * 1024) return `${formatNumber(Math.max(1, Math.round(bytes / 1024)), dateLocale)} KB`;
  return `${formatNumber(bytes / 1024 / 1024, dateLocale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`;
}

function publishProgressText(progress: PublishProgress, t: Translate, dateLocale: string) {
  const current = formatNumber(progress.current, dateLocale);
  const total = formatNumber(progress.total, dateLocale);
  const percent = formatNumber(progress.percent, dateLocale);
  if (progress.phase === "preparing") return t("community.feed.upload.preparing", "正在检查视频时长与格式…");
  if (progress.phase === "uploading") return t("community.feed.upload.uploading", `正在上传第 ${progress.current}/${progress.total} 个文件 · ${progress.percent}%`, { current, total, percent });
  if (progress.phase === "processing") return t("community.feed.upload.processing", `第 ${progress.current}/${progress.total} 个文件已上传，服务器正在${progress.video ? "转换兼容视频" : "处理文件"}…`, { current, total, task: progress.video ? t("community.feed.upload.transcoding", "转换兼容视频") : t("community.feed.upload.processingFile", "处理文件") });
  if (progress.phase === "publishing") return t("community.feed.upload.publishing", "媒体处理完成，正在发布动态…");
  return "";
}

function publishButtonText(progress: PublishProgress, t: Translate, dateLocale: string) {
  if (progress.phase === "preparing") return t("community.feed.upload.checking", "检查中…");
  if (progress.phase === "uploading") return t("community.feed.upload.button", "上传 {percent}%", { percent: formatNumber(progress.percent, dateLocale) });
  if (progress.phase === "processing") return t("community.feed.upload.processingShort", "处理中…");
  if (progress.phase === "publishing") return t("community.feed.publishing", "发布中…");
  return t("community.feed.publish", "发布");
}

function localizedMediaError(message: string, t: Translate) {
  if (/一次最多选择 \d+ 个文件/.test(message)) return t("community.feed.error.tooManyFiles", "一次最多选择 9 个文件，请重新选择");
  if (message === "社区图片不能超过 5MB，请重新选择") return t("community.feed.error.imageTooLarge", message);
  if (message === "社区视频不能超过 20MB，请重新选择") return t("community.feed.error.videoTooLarge", message);
  return message;
}

function localizedCommunityError(reason: unknown, t: Translate) {
  if (!(reason instanceof Error)) return t("community.feed.error.generic", "操作失败，请稍后重试");
  const localized = localizedMediaError(reason.message, t);
  if (localized !== reason.message) return localized;
  const known: Record<string, [string, string]> = {
    "无法读取视频时长，请更换视频文件": ["community.feed.error.videoDuration", "无法读取视频时长，请更换视频文件"],
    "视频不能与其他图片或视频同时发布": ["community.feed.error.videoExclusive", "视频不能与其他图片或视频同时发布"],
    "社区视频不能超过 5 分钟": ["community.feed.error.videoTooLong", "社区视频不能超过 5 分钟"],
    "视频兼容处理未完成，请重新上传": ["community.feed.error.videoProcessing", "视频兼容处理未完成，请重新上传"],
    "浏览器未允许复制，请手动复制动态内容": ["community.feed.error.copyDenied", "浏览器未允许复制，请手动复制动态内容"],
  };
  const entry = known[reason.message];
  return entry ? t(entry[0], entry[1]) : reason.message;
}

function readVideoDuration(file: File, failureMessage: string) {
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
      reject(new Error(failureMessage));
    };
    video.src = url;
  });
}

function postSourceHref(row: CommunityPost) {
  return row.canonical_url || row.source_url || row.video_url || "";
}

function ExternalVideoPreview({ row }: { row: CommunityPost }) {
  const { t } = useI18n();
  const [thumbnailFailed, setThumbnailFailed] = useState(false);
  const href = postSourceHref(row);
  if (!href) return null;
  return (
    <a className="community-video-cover" href={href} target="_blank" rel="noreferrer" data-i18n-skip aria-label={t("community.feed.video.watchAria", "观看视频：{title}", { title: communityDisplayText(row.content, row.source_key) })}>
      {!thumbnailFailed && row.thumbnail_url ? (
        <img src={row.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setThumbnailFailed(true)} />
      ) : (
        <span className="community-video-cover__fallback"><VideoCamera size={42} /><small>{t("community.feed.video.signal", "VIDEO SIGNAL")}</small></span>
      )}
      <span className="community-video-cover__shade" />
      <span className="community-video-cover__play"><Play size={22} weight="fill" /></span>
      <span className="community-video-cover__label">{t("community.feed.video.official", "官方视频")}</span>
      <span className="community-video-cover__source">{communityDisplayText(row.source_name, row.source_key) ? <span data-i18n-skip>{communityDisplayText(row.source_name, row.source_key)}</span> : t("community.feed.video.watchSource", "在来源网站观看")}<ArrowUpRight size={15} /></span>
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
  const { t, dateLocale, locale } = useI18n();
  const externalVideo = !row.video && (row.content_type === "video" || Boolean(row.video_url));
  const sourceName = communityDisplayText(row.source_name || row.source_author, row.source_key);
  const authorName = localizePersonName(
    communityDisplayText(row.author_name || row.source_author || row.source_name, row.source_key),
    locale,
  ) || t("community.feed.userFallback", "社区用户");
  const content = communityDisplayText(row.content, row.source_key);
  const summary = communityDisplayText(row.summary, row.source_key);
  return (
    <article className={`community-post-card${featured ? " community-post-card--featured" : ""}${externalVideo ? " community-post-card--video" : ""}`}>
      <header className="community-post-card__author">
        <div className="community-user-avatar" data-i18n-skip>
          {row.author_avatar ? <img src={row.author_avatar.startsWith("/user/avatars/") ? `/api/v1/canonical${row.author_avatar}` : row.author_avatar} alt="" /> : authorName.slice(0, 1)}
        </div>
        <span><strong data-i18n-skip>{authorName}</strong><small>{formatDate(row.source_published_at || row.created_at, dateLocale)}{row.topic ? <> · <span data-i18n-skip>{row.topic}</span></> : ""}</small></span>
        {!row.is_own && <button className={row.is_following ? "following" : ""} disabled={busy.has(`follow-${row.user_id}`)} onClick={() => onFollow(row)}><UserPlus size={15} />{row.is_following ? t("community.feed.following", "已关注") : t("community.feed.follow", "关注")}</button>}
      </header>

      <div className="community-post-card__copy">
        {row.origin === "aggregated" && <div className="community-source-line"><span>{t("community.feed.aggregated", "自动资讯")}</span><b data-i18n-skip>{sourceName || t("community.feed.publicSource", "公开来源")}</b></div>}
        <p data-i18n-skip>{content}</p>
        {summary && summary !== content && <small className="community-post-summary" data-i18n-skip>{summary}</small>}
      </div>

      <div className="community-post-card__media">
        {row.images?.length ? <div className={`community-media-grid${row.images.length === 1 ? " is-single" : ""}`}>{row.images.map((image, index) => <img src={communityMediaUrl(image)} alt={t("community.feed.postImage", "动态图片")} loading="lazy" key={`${image}-${index}`} />)}</div> : null}
        {row.video && <video className="community-video-player" controls preload="metadata" src={communityMediaUrl(row.video)} aria-label={t("community.feed.postVideo", "动态视频")} />}
        {externalVideo && <ExternalVideoPreview row={row} />}
      </div>

      <footer className="community-post-card__actions">
        <button aria-label={t("community.feed.likeAria", "点赞，共 {count}", { count: formatNumber(row.likes, dateLocale) })} className={row.is_liked ? "liked" : ""} disabled={busy.has(`like-${row.id}`)} onClick={() => onLike(row)}><Heart size={18} weight={row.is_liked ? "fill" : "regular"} />{formatNumber(row.likes, dateLocale)}</button>
        <button aria-label={t("community.feed.commentsAria", "评论，共 {count}", { count: formatNumber(row.comments, dateLocale) })} onClick={() => onShowComments(row.id)}><ChatCircle size={18} />{formatNumber(row.comments, dateLocale)}</button>
        <button disabled={busy.has(`share-${row.id}`)} onClick={() => onShare(row)}><ShareNetwork size={18} />{busy.has(`share-${row.id}`) ? t("community.feed.copying", "复制中…") : t("community.feed.share", "分享{count}", { count: row.shares ? ` ${formatNumber(row.shares, dateLocale)}` : "" })}</button>
        {row.source_url && <a href={row.source_url} target="_blank" rel="noreferrer">{t("community.feed.viewSource", "查看来源")}<ArrowUpRight size={15} /></a>}
      </footer>

      {openComments === row.id && <section className="community-comments">
        {comments[row.id]?.length ? comments[row.id].map((item) => <article key={item.id}><strong data-i18n-skip>{localizePersonName(item.author_name, locale) || t("community.feed.userFallback", "社区用户")}</strong><p data-i18n-skip>{item.content}</p><time>{formatDate(item.created_at, dateLocale)}</time></article>) : <p className="community-comments__empty">{t("community.feed.comments.empty", "还没有评论，写下第一条。")}</p>}
        <form onSubmit={(event) => onSubmitComment(event, row.id)}><input maxLength={500} value={comment} onChange={(event) => onCommentChange(event.target.value)} placeholder={t("community.feed.comments.placeholder", "写下评论…")} /><button disabled={busy.has(`comment-${row.id}`)}>{t("community.feed.comments.send", "发送")}</button></form>
      </section>}
    </article>
  );
}

export function CommunityFeed({ initialQuery = "", initialPage = 1 }: { initialCategory?: string; initialQuery?: string; initialPage?: number }) {
  const { t, dateLocale } = useI18n();
  const [rows, setRows] = useState<CommunityPost[]>([]);
  const [tab, setTab] = useState<(typeof tabs)[number]["value"]>("recommend");
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
  const commentsRef = useRef<Record<number, CommunityComment[]>>({});
  const [commentDrafts, setCommentDrafts] = useState<Record<number, string>>({});
  const commentDraftsRef = useRef<Record<number, string>>({});
  const pendingCommentIntents = useRef(new Map<number, CommunityCommentIntent>());

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
      else setError(localizedCommunityError(reason, t));
    } finally { setLoading(false); }
  }, [page, query, tab, t]);

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

  function storeComments(id: number, next: CommunityComment[]) {
    const value = { ...commentsRef.current, [id]: next };
    commentsRef.current = value;
    setComments(value);
  }

  function updateCommentDraft(id: number, value: string) {
    const next = { ...commentDraftsRef.current, [id]: value };
    commentDraftsRef.current = next;
    setCommentDrafts(next);
  }

  async function publish(event: FormEvent) {
    event.preventDefault();
    if (!draft.content.trim()) return;
    const validationError = communityMediaUploadError(files);
    if (validationError) { setError(localizedMediaError(validationError, t)); return; }
    const action = "publish";
    if (!beginAction(action)) return;
    setError("");
    try {
      const videoFile = files.find(isCommunityVideoFile);
      if (videoFile && files.length > 1) throw new Error(t("community.feed.error.videoExclusive", "视频不能与其他图片或视频同时发布"));
      if (videoFile) setPublishProgress({ phase: "preparing", percent: 0, current: 1, total: 1, fileName: videoFile.name, video: true });
      const inputDuration = videoFile ? await readVideoDuration(videoFile, t("community.feed.error.videoDuration", "无法读取视频时长，请更换视频文件")) : undefined;
      if (inputDuration && inputDuration > 300) throw new Error(t("community.feed.error.videoTooLong", "社区视频不能超过 5 分钟"));
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
        throw new Error(t("community.feed.error.videoProcessing", "视频兼容处理未完成，请重新上传"));
      }
      setPublishProgress({ phase: "publishing", percent: 100, current: files.length, total: files.length, fileName: "", video: Boolean(video) });
      await createCommunityPost({ content: draft.content.trim(), topic: draft.topic.trim() || undefined, images: images.length ? images : undefined, video: video?.url, video_duration: video?.duration || undefined });
      setDraft({ content: "", topic: "" }); setFiles([]); if (fileInput.current) fileInput.current.value = ""; setComposerOpen(false); setPage(1); await load();
    } catch (reason) { setError(localizedCommunityError(reason, t)); }
    finally { finishAction(action); }
  }

  async function like(row: CommunityPost) {
    const action = `like-${row.id}`;
    if (!beginAction(action)) return;
    const targetLiked = !row.is_liked;
    try { const result = await setCommunityLike(row.id, targetLiked); setRows((items) => items.map((item) => item.id === row.id ? { ...item, likes: result.likes, is_liked: result.liked } : item)); }
    catch (reason) { setError(localizedCommunityError(reason, t)); }
    finally { finishAction(action); }
  }

  async function follow(row: CommunityPost) {
    const action = `follow-${row.user_id}`;
    if (!beginAction(action)) return;
    const targetFollowing = !row.is_following;
    try { const result = await setCommunityFollow(row.user_id, targetFollowing); setRows((items) => items.map((item) => item.user_id === row.user_id ? { ...item, is_following: result.following } : item)); }
    catch (reason) { setError(localizedCommunityError(reason, t)); }
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
        if (!copied) throw new Error(t("community.feed.error.copyDenied", "浏览器未允许复制，请手动复制动态内容"));
      }
      setMessage(t("community.feed.copySuccess", "动态内容已复制，可以粘贴分享"));
    } catch (reason) { setError(localizedCommunityError(reason, t)); }
    finally { finishAction(action); }
  }

  async function showComments(id: number) {
    if (openComments === id) { setOpenComments(null); return; }
    setOpenComments(id);
    try { const next = await getCommunityComments(id); storeComments(id, next); }
    catch (reason) { setError(localizedCommunityError(reason, t)); }
  }

  async function submitComment(event: FormEvent, id: number) {
    event.preventDefault();
    const value = (commentDrafts[id] || "").trim();
    if (!value) return;
    const action = `comment-${id}`;
    if (!beginAction(action)) return;
    try {
      const intent = ensureCommunityCommentIntent(
        pendingCommentIntents.current.get(id) || null,
        communityCommentIntentSignature(id, value),
        () => crypto.randomUUID(),
      );
      pendingCommentIntents.current.set(id, intent);
      const result = await createCommunityComment(id, value, intent.requestId);
      const draftStillMatches = communityCommentIntentSignature(
        id,
        (commentDraftsRef.current[id] || "").trim(),
      ) === intent.signature;
      if (pendingCommentIntents.current.get(id) === intent) {
        pendingCommentIntents.current.delete(id);
      }
      if (draftStillMatches) {
        const next = { ...commentDraftsRef.current };
        delete next[id];
        commentDraftsRef.current = next;
        setCommentDrafts(next);
      }
      const currentComments = commentsRef.current[id] || [];
      const knownComment = currentComments.some((item) => item.id === result.id);
      storeComments(id, [result, ...currentComments.filter((item) => item.id !== result.id)]);
      const postComments = typeof result.post_comments === "number"
        && Number.isInteger(result.post_comments)
        && result.post_comments >= 0
        ? result.post_comments
        : null;
      setRows((items) => items.map((item) => item.id === id
        ? { ...item, comments: postComments ?? item.comments + (knownComment ? 0 : 1) }
        : item));
    } catch (reason) { setError(localizedCommunityError(reason, t)); }
    finally { finishAction(action); }
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    if (page === 1) void load(); else setPage(1);
  }

  const publishing = busy.has("publish");
  const selectedBytes = files.reduce((totalBytes, file) => totalBytes + file.size, 0);

  if (loginRequired) return <div className="community-login"><ChatCircle size={38}/><h2>{t("community.feed.login.title", "登录后进入算力社区")}</h2><p>{t("community.feed.login.description", "登录后可发布动态、关注、点赞和评论。")}</p><Link href="/login?return_to=/community">{t("community.feed.login.action", "登录")}</Link></div>;

  return <section className="mobile-community-feed">
    <div className="community-commandbar">
      <form className="community-search" onSubmit={submitSearch}><MagnifyingGlass size={21}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("community.feed.search", "搜索动态、话题或作者")} aria-label={t("community.feed.searchAria", "搜索社区动态")} /></form>
      <button className="community-publish-button" type="button" onClick={() => setComposerOpen((value) => !value)}><Plus size={17}/>{composerOpen ? t("community.feed.composer.collapse", "收起发布") : t("community.feed.composer.open", "发布动态")}</button>
      <div className="community-commandbar__meta"><span>{t("community.feed.postsEyebrow", "POSTS")}</span><strong>{formatNumber(total, dateLocale)}</strong><small>{t("community.feed.postCount", "条社区动态")}</small></div>
    </div>

    <div className="mobile-community-tabs" role="tablist" aria-label={t("community.feed.tabsAria", "社区内容筛选")}>{tabs.map(({ value, key, fallback }) => <button type="button" role="tab" aria-selected={tab === value} className={tab === value ? "active" : ""} key={value} onClick={() => { setTab(value); setPage(1); }}>{t(key, fallback)}</button>)}</div>

    {composerOpen && <form className="community-composer" onSubmit={publish}>
      <header><PaperPlaneTilt size={20}/><div><small>{t("community.feed.composer.eyebrow", "CREATE POST")}</small><h2>{t("community.feed.composer.title", "发布社区动态")}</h2></div></header>
      <input disabled={publishing} maxLength={40} value={draft.topic} onChange={(event) => setDraft({ ...draft, topic: event.target.value })} placeholder={t("community.feed.composer.topic", "话题（可选）")} />
      <textarea disabled={publishing} required maxLength={COMMUNITY_POST_MAX_LENGTH} value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} placeholder={t("community.feed.composer.content", "分享算力设备、行情或使用经验…")} />
      {files.length > 0 && <div className="community-upload-selection"><div><strong>{t("community.feed.composer.selectedFiles", "已选择 {count} 个文件 · {size}", { count: formatNumber(files.length, dateLocale), size: formatUploadBytes(selectedBytes, dateLocale) })}</strong><small data-i18n-skip>{files.map((file) => file.name).join(t("community.feed.composer.fileSeparator", "、"))}</small></div><button type="button" disabled={publishing} onClick={() => { setFiles([]); if (fileInput.current) fileInput.current.value = ""; }}>{t("community.feed.composer.clear", "清除")}</button></div>}
      {publishProgress.phase !== "idle" && <div className="community-upload-progress" role="status" aria-live="polite"><div><strong>{publishProgressText(publishProgress, t, dateLocale)}</strong><small data-i18n-skip={Boolean(publishProgress.fileName)}>{publishProgress.fileName || t("community.feed.upload.writing", "正在写入动态")}</small></div><span><i style={{ width: `${publishProgress.percent}%` }}/></span></div>}
      <footer><label aria-disabled={publishing}><ImageSquare size={16}/>{t("community.feed.composer.addMedia", "添加图片或视频（{limits}）", { limits: t("community.feed.composer.mediaLimits", COMMUNITY_MEDIA_LIMIT_TEXT) })}<input ref={fileInput} disabled={publishing} hidden multiple type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm,.mov" onChange={(event) => {
        const selected = Array.from(event.currentTarget.files || []);
        const validationError = communityMediaUploadError(selected);
        if (validationError) { setError(localizedMediaError(validationError, t)); event.currentTarget.value = ""; return; }
        setError(""); setFiles(selected);
      }}/></label><span>{files.length ? t("community.feed.composer.characterCount", "{current}/{maximum} 字", { current: formatNumber(draft.content.length, dateLocale), maximum: formatNumber(COMMUNITY_POST_MAX_LENGTH, dateLocale) }) : `${formatNumber(draft.content.length, dateLocale)}/${formatNumber(COMMUNITY_POST_MAX_LENGTH, dateLocale)}`}</span><button disabled={publishing}>{publishButtonText(publishProgress, t, dateLocale)}</button></footer>
    </form>}

    {error && <div className="commerce-error" data-i18n-skip>{error}</div>}
    {message && <div className="commerce-success">{message}</div>}
    {loading ? <div className="news-skeleton" role="status" aria-label={t("community.feed.loading", "正在加载社区动态")}><span/><span/><span/></div> : <div className="mobile-community-list">{rows.length ? rows.map((row, index) => <CommunityCard key={row.id} row={row} featured={index === 0 && page === 1} busy={busy} openComments={openComments} comments={comments} comment={commentDrafts[row.id] || ""} onCommentChange={(value) => updateCommentDraft(row.id, value)} onLike={(item) => void like(item)} onFollow={(item) => void follow(item)} onShare={(item) => void share(item)} onShowComments={(id) => void showComments(id)} onSubmitComment={(event, id) => void submitComment(event, id)} />) : <div className="data-empty"><ChatCircle size={30}/><strong>{t("community.feed.empty.title", "当前没有动态")}</strong><p>{t("community.feed.empty.description", "切换标签或发布第一条内容。")}</p></div>}</div>}

    {total > 10 && <nav className="community-page-nav" aria-label={t("community.feed.paginationAria", "社区动态分页")}><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>{t("community.feed.previous", "上一页")}</button><span>{t("community.feed.page", "第 {page} 页", { page: formatNumber(page, dateLocale) })}</span><button disabled={page * 10 >= total} onClick={() => setPage((value) => value + 1)}>{t("community.feed.next", "下一页")}</button></nav>}
  </section>;
}
