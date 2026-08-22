import type { Metadata } from "next";
import { NewsDetail } from "@/components/news-detail";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "资讯详情", description: "北斗 kai 算力与 AI 资讯详情。" };

export default async function NewsDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div className="site-page"><SiteHeader /><main className="news-detail-page"><NewsDetail articleId={id} /></main></div>;
}
