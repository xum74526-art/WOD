import type { Metadata } from "next";
import { NewsDetail } from "@/components/news-detail";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "資訊詳情", description: "算力星图算力與 AI 資訊詳情。" };

export default async function NewsDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div className="site-page public-v2"><SiteHeader /><main className="news-detail-page"><NewsDetail articleId={id} /></main></div>;
}
