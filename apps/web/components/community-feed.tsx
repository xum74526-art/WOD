"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, ArrowUpRight, Broadcast, MagnifyingGlass, Play } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";

type Article = { id: number; title: string; summary: string; category: string; image_url?: string; published_at?: string; collected_at: string; source: { name: string } };
type Video = { id: string; title: string; summary: string; category: string; thumbnail_url: string; platform: string; published_at: string; duration?: string };
type NewsResponse = { data: Article[]; meta: { total: number; total_pages: number } };
const categories = [["all", "全部"], ["market", "市场行情"], ["hardware", "GPU 与硬件"], ["compute", "算力技术"], ["policy", "政策与产业"]];
const categoryNames = Object.fromEntries(categories);
const fallbackImages: Record<string, string> = { market: "/images/rtx5090.jpg", hardware: "/images/h100.jpg", compute: "/images/rtx4090.jpg", policy: "/images/a800.jpg", industry: "/images/h100.jpg" };
function relativeTime(value?: string) { if (!value) return "时间未标注"; const hours = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 3_600_000)); return hours < 1 ? "刚刚" : hours < 24 ? `${hours} 小时前` : `${Math.floor(hours / 24)} 天前`; }

export function CommunityFeed({ initialCategory = "all", initialQuery = "", initialPage = 1 }: { initialCategory?: string; initialQuery?: string; initialPage?: number }) {
  const [articles, setArticles] = useState<Article[]>([]), [videos, setVideos] = useState<Video[]>([]);
  const [category, setCategory] = useState(initialCategory), [contentType, setContentType] = useState<"all" | "article" | "video">("all");
  const [queryInput, setQueryInput] = useState(initialQuery), [query, setQuery] = useState(initialQuery), [page, setPage] = useState(initialPage), [totalPages, setTotalPages] = useState(0), [total, setTotal] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading"), [message, setMessage] = useState("");
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => { const next = queryInput.trim(); if (next === query) return; const timer = window.setTimeout(() => { setQuery(next); setPage(1); }, 300); return () => window.clearTimeout(timer); }, [query, queryInput]);
  const load = useCallback(async () => {
    requestRef.current?.abort(); const controller = new AbortController(); requestRef.current = controller; setState("loading");
    const params = new URLSearchParams({ page: String(page), page_size: "12", sort: "latest" });
    if (category !== "all") params.set("category", category); if (query) params.set("q", query);
    try {
      const [newsResponse, videoResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/v1/public/news?${params}`, { cache: "no-store", signal: controller.signal }),
        fetch(`${apiBaseUrl}/api/v1/public/videos`, { cache: "no-store", signal: controller.signal }),
      ]);
      if (!newsResponse.ok) throw new Error(await readApiError(newsResponse));
      const payload = await newsResponse.json() as NewsResponse; const videoPayload = videoResponse.ok ? await videoResponse.json() : { data: [] };
      setArticles(payload.data ?? []); setVideos(videoPayload.data ?? []); setTotal(payload.meta.total); setTotalPages(payload.meta.total_pages); setState("ready");
    } catch (error) { if (error instanceof DOMException && error.name === "AbortError") return; setMessage(error instanceof Error ? error.message : "资讯服务暂时不可用"); setState("error"); }
  }, [category, page, query]);
  useEffect(() => { void load(); return () => requestRef.current?.abort(); }, [load]);
  useEffect(() => { const params = new URLSearchParams(); if (category !== "all") params.set("category", category); if (query) params.set("q", query); if (page > 1) params.set("page", String(page)); window.history.replaceState(null, "", params.size ? `/community?${params}` : "/community"); }, [category, page, query]);

  const matchedVideos = useMemo(() => videos.filter((video) => (category === "all" || video.category === category) && (!query || `${video.title} ${video.summary} ${video.platform}`.toLowerCase().includes(query.toLowerCase()))), [category, query, videos]);
  const featured = page === 1 && !query && contentType !== "video" ? articles.slice(0, 3) : [];
  const stream = featured.length ? articles.slice(3) : articles;
  const showArticles = contentType !== "video";
  const showVideos = contentType !== "article";

  return <section className="news-browser">
    <div className="community-commandbar">
      <label className="community-search"><MagnifyingGlass size={21} /><input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="搜索 GPU 型号、价格、公司或技术" /></label>
      <div className="community-commandbar__meta"><span>INDEX</span><strong>{total + videos.length}</strong><small>条算力信号</small></div>
    </div>
    <div className="community-filter-row"><div className="news-categories">{categories.map(([slug, label]) => <button className={category === slug ? "active" : ""} type="button" key={slug} onClick={() => { setCategory(slug); setPage(1); }}>{label}</button>)}</div><div className="content-type-tabs"><span>FORMAT</span>{[["all", "全部"], ["article", "文章"], ["video", "视频"]].map(([slug, label]) => <button className={contentType === slug ? "active" : ""} key={slug} onClick={() => setContentType(slug as typeof contentType)}>{label}</button>)}</div></div>

    {featured.length > 0 && <section className="featured-news"><div className="section-heading"><div><p className="hero-eyebrow">PRIMARY SIGNAL</p><h2>本期重点</h2></div><span>按发布时间自动更新</span></div><div className="featured-news-grid"><Link className="featured-main" href={`/community/news/${featured[0].id}`}><img src={featured[0].image_url || fallbackImages[featured[0].category]} alt="" referrerPolicy="no-referrer" /><div><span>{categoryNames[featured[0].category]} · {relativeTime(featured[0].published_at)}</span><h3>{featured[0].title}</h3><p>{featured[0].summary}</p><strong>打开情报 <ArrowUpRight size={16} /></strong></div></Link><div className="featured-secondary">{featured.slice(1).map((item) => <Link href={`/community/news/${item.id}`} key={item.id}><img src={item.image_url || fallbackImages[item.category]} alt="" referrerPolicy="no-referrer" /><span>{categoryNames[item.category]}</span><h3>{item.title}</h3></Link>)}</div></div></section>}

    {state === "loading" && <div className="news-skeleton">{[1, 2, 3].map((item) => <span key={item} />)}</div>}
    {state === "error" && <div className="data-empty data-empty--error"><strong>{message}</strong><button className="outline-link" onClick={() => void load()}>重新加载</button></div>}
    {state === "ready" && <div className={`community-content-grid ${contentType !== "all" ? "single" : ""}`}>
      {showArticles && <section className="latest-news"><header><div><p className="hero-eyebrow">ARTICLE FEED</p><h2>最新文章</h2></div><span>{total} 篇</span></header>{stream.length === 0 ? <div className="data-empty"><Broadcast size={28} /><strong>没有找到匹配的文章</strong><p>换一个关键词或分类试试。</p></div> : stream.map((article) => <article className="news-card" key={article.id}><Link className="news-card__image" href={`/community/news/${article.id}`}><img src={article.image_url || fallbackImages[article.category] || fallbackImages.industry} alt="" referrerPolicy="no-referrer" onError={(event) => { event.currentTarget.src = fallbackImages[article.category] || fallbackImages.industry; }} /></Link><div><span className="news-card__meta">{categoryNames[article.category] || "算力资讯"} · {relativeTime(article.published_at || article.collected_at)} · 文章</span><h2><Link href={`/community/news/${article.id}`}>{article.title}</Link></h2><p>{article.summary}</p><footer><span>{article.source.name}</span><Link href={`/community/news/${article.id}`}>查看详情 <ArrowUpRight size={15} /></Link></footer></div></article>)}{totalPages > 1 && <nav className="news-pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ArrowLeft size={15} />上一页</button><span>第 {page} / {totalPages} 页</span><button disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>下一页<ArrowRight size={15} /></button></nav>}</section>}
      {showVideos && <aside className="video-dispatch"><header><div><p className="hero-eyebrow">VIDEO DISPATCH</p><h2>官方视频</h2></div><span>{matchedVideos.length} 条</span></header>{matchedVideos.length === 0 ? <div className="data-empty"><strong>当前分类暂无视频</strong><p>切换到“全部”查看官方算力视频。</p></div> : <div className="video-card-list">{matchedVideos.map((video, index) => <Link href={`/community/videos/${video.id}`} key={video.id} className={index === 0 ? "lead" : ""}><div><img src={video.thumbnail_url} alt="" referrerPolicy="no-referrer" /><span className="video-play"><Play size={18} weight="fill" /></span>{video.duration && <small>{video.duration}</small>}</div><p>{video.platform} · {new Date(video.published_at).getFullYear()}</p><h3>{video.title}</h3></Link>)}</div>}</aside>}
    </div>}
  </section>;
}
