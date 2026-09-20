"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, BookOpenText, CalendarBlank, Clock, SealCheck } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";
import { ArticleComments } from "@/components/article-comments";
import { useI18n } from "@/components/locale-root";

type Article = { id: number; title: string; title_original?: string; summary: string; content?: string; content_format?: string; ingestion_method?: string; category: string; tags: string[]; image_url?: string; original_url: string; published_at?: string; collected_at: string; source: { name: string; site_url: string; is_official: boolean } };
type Translate = ReturnType<typeof useI18n>["t"];

function categoryName(category: string, t: Translate) {
  const names: Record<string, string> = {
    market: t("community.news.category.market", "市场行情"),
    hardware: t("community.news.category.hardware", "GPU 与硬件"),
    compute: t("community.news.category.compute", "算力技术"),
    policy: t("community.news.category.policy", "政策与产业"),
  };
  return names[category] || t("community.news.category.fallback", "算力资讯");
}

export function NewsDetail({ articleId }: { articleId: string }) {
  const { t, dateLocale } = useI18n();
  const [article, setArticle] = useState<Article | null>(null);
  const [related, setRelated] = useState<Article[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/api/v1/public/news/${encodeURIComponent(articleId)}`, { cache: "no-store", signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(await readApiError(response));
      return response.json();
    }).then(async (payload) => {
      const item = payload.data as Article;
      setArticle(item);
      const response = await fetch(`${apiBaseUrl}/api/v1/public/news?category=${encodeURIComponent(item.category)}&page_size=5`, { cache: "no-store", signal: controller.signal });
      if (response.ok) {
        const result = await response.json();
        setRelated((result.data ?? []).filter((entry: Article) => entry.id !== item.id).slice(0, 4));
      }
    }).catch((reason) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error ? reason.message : t("community.news.error.load", "资讯读取失败"));
    });
    return () => controller.abort();
  }, [articleId, t]);
  if (error) return <div className="data-empty data-empty--error"><strong data-i18n-skip>{error}</strong><Link className="outline-link" href="/community">{t("community.news.back", "返回资讯")}</Link></div>;
  if (!article) return <div className="news-detail-loading" role="status" aria-label={t("community.news.loading", "正在加载资讯")}><span /><span /><span /></div>;
  const published = new Date(article.published_at || article.collected_at);
  const readingMinutes = Math.max(2, Math.ceil(((article.content || article.summary)?.length || 180) / 500));
  const localizedCategory = categoryName(article.category, t);
  return <div className="intelligence-detail">
    <aside className="intelligence-index">
      <Link href="/community"><ArrowLeft size={15} />{t("community.news.backFeed", "返回资讯流")}</Link>
      <p className="hero-eyebrow">{t("community.news.index.eyebrow", "ARTICLE INDEX")}</p>
      <h2>{t("community.news.index.title", "本页目录")}</h2>
      <nav aria-label={t("community.news.index.aria", "文章目录")}><a href="#summary">{t("community.news.index.summary", "01 · 内容概览")}</a><a href="#article-body">{t("community.news.index.body", "02 · 文章正文")}</a><a href="#related">{t("community.news.index.related", "03 · 相关资讯")}</a><a href="#comments">{t("community.news.index.comments", "04 · 留言讨论")}</a></nav>
      <h2>{t("community.news.relatedTopics", "相关主题")}</h2>
      <div className="intelligence-tags">{article.tags.length ? article.tags.map((tag) => <span key={tag} data-i18n-skip>{tag}</span>) : <span>{localizedCategory}</span>}</div>
    </aside>
    <article className="intelligence-article">
      <p className="hero-eyebrow">{t("community.news.eyebrow", "COMPUTE INTELLIGENCE")}</p>
      <h1 data-i18n-skip>{article.title}</h1>
      <div className="intelligence-byline"><span>{article.source.is_official && <SealCheck size={17} />} <span data-i18n-skip>{article.source.name}</span></span><span><CalendarBlank size={16} />{published.toLocaleDateString(dateLocale)}</span></div>
      <div className="intelligence-facts">
        <div><BookOpenText size={18} /><small>{t("community.news.contentType", "内容类型")}</small><strong>{localizedCategory}</strong></div>
        <div><SealCheck size={18} /><small>{t("community.news.sourceType", "内容来源")}</small><strong>{article.ingestion_method === "rsshub" ? t("community.news.source.rsshub", "RSSHub 聚合") : t("community.news.source.official", "官方来源")}</strong></div>
        <div><Clock size={18} /><small>{t("community.news.readingTime", "预计阅读")}</small><strong>{t("community.news.minutes", "{minutes} 分钟", { minutes: new Intl.NumberFormat(dateLocale).format(readingMinutes) })}</strong></div>
      </div>
      {article.image_url && <img className="intelligence-cover" src={article.image_url} alt={t("community.news.coverAlt", "文章封面")} referrerPolicy="no-referrer" />}
      <section className="intelligence-copy" id="summary"><h2>{t("community.news.summary", "内容概览")}</h2><p data-i18n-skip>{article.summary || t("community.news.summaryFallback", "正文已收录，可在本页直接阅读。")}</p>{article.title_original && article.title_original !== article.title && <blockquote data-i18n-skip><span>{t("community.news.originalTitle", "原标题")}</span>{article.title_original}</blockquote>}</section>
      <section className="intelligence-copy intelligence-body" id="article-body"><h2>{t("community.news.body", "文章正文")}</h2>{article.content ? <div data-i18n-skip dangerouslySetInnerHTML={{ __html: article.content }} /> : <p data-i18n-skip>{article.summary || t("community.news.bodyFallback", "该来源暂未提供可展示的正文。")}</p>}</section>
      {related.length > 0 && <section className="intelligence-related" id="related"><h2>{t("community.news.related", "相关资讯")}</h2>{related.map((item) => <Link href={`/community/news/${item.id}`} key={item.id}><span>{categoryName(item.category, t)}</span><strong data-i18n-skip>{item.title}</strong><ArrowUpRight size={16} /></Link>)}</section>}
      <ArticleComments articleId={article.id} />
    </article>
  </div>;
}
