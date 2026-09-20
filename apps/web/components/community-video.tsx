"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

type Video = { title: string; summary: string; platform: string; published_at: string; embed_url: string; original_url: string };
export function CommunityVideo({ videoId }: { videoId: string }) {
  const { t, dateLocale } = useI18n();
  const [video, setVideo] = useState<Video | null>(null), [error, setError] = useState("");
  useEffect(() => { fetch(`${apiBaseUrl}/api/v1/public/videos/${encodeURIComponent(videoId)}`).then(async (response) => { if (!response.ok) throw new Error(await readApiError(response)); return response.json(); }).then((payload) => setVideo(payload.data)).catch((reason) => setError(reason instanceof Error ? reason.message : t("community.video.error.load", "视频读取失败"))); }, [t, videoId]);
  if (error) return <div className="data-empty"><strong data-i18n-skip>{error}</strong><Link href="/community">{t("community.video.back", "返回社区")}</Link></div>;
  if (!video) return <div className="news-detail-loading" role="status" aria-label={t("community.video.loading", "正在加载视频")}><span /><span /><span /></div>;
  return <article className="video-detail"><Link href="/community"><ArrowLeft size={15} />{t("community.video.backFull", "返回算力社区")}</Link><p className="hero-eyebrow">{t("community.video.eyebrow", "OFFICIAL VIDEO")} / <span data-i18n-skip>{video.platform}</span></p><h1 data-i18n-skip>{video.title}</h1><p data-i18n-skip>{video.summary}</p><div className="video-frame"><iframe data-i18n-skip src={video.embed_url} title={video.title} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /></div><footer><span>{t("community.video.publisher", "发布主体：")}<span data-i18n-skip>{video.platform}</span> · {new Date(video.published_at).toLocaleDateString(dateLocale)}</span><a href={video.original_url} target="_blank" rel="noreferrer">{t("community.video.watchOriginal", "在 YouTube 查看原视频")} <ArrowUpRight size={15} /></a></footer></article>;
}
