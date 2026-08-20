"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight } from "@phosphor-icons/react";
import { apiBaseUrl, readApiError } from "@/lib/api";

type Video = { title: string; summary: string; platform: string; published_at: string; embed_url: string; original_url: string };
export function CommunityVideo({ videoId }: { videoId: string }) {
  const [video, setVideo] = useState<Video | null>(null), [error, setError] = useState("");
  useEffect(() => { fetch(`${apiBaseUrl}/api/v1/public/videos/${encodeURIComponent(videoId)}`).then(async (response) => { if (!response.ok) throw new Error(await readApiError(response)); return response.json(); }).then((payload) => setVideo(payload.data)).catch((reason) => setError(reason instanceof Error ? reason.message : "视频读取失败")); }, [videoId]);
  if (error) return <div className="data-empty"><strong>{error}</strong><Link href="/community">返回社区</Link></div>;
  if (!video) return <div className="news-detail-loading"><span /><span /><span /></div>;
  return <article className="video-detail"><Link href="/community"><ArrowLeft size={15} />返回算力社区</Link><p className="hero-eyebrow">OFFICIAL VIDEO / {video.platform}</p><h1>{video.title}</h1><p>{video.summary}</p><div className="video-frame"><iframe src={video.embed_url} title={video.title} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /></div><footer><span>发布主体：{video.platform} · {new Date(video.published_at).toLocaleDateString("zh-CN")}</span><a href={video.original_url} target="_blank" rel="noreferrer">在 YouTube 查看原视频 <ArrowUpRight size={15} /></a></footer></article>;
}
