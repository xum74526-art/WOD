import type { Metadata } from "next";
import { MarketPageContent } from "@/components/market-page-content";
import { getInitialMarketRanking, getInitialPublicProducts } from "@/lib/server/public-page-data";

export const metadata: Metadata = { title: "算力市场", description: "分别浏览 KAI 自营与商家发布的算力资源，提交需求后由人工联系确认方案。" };

export default async function MarketPage() {
  const [initialRanking, initialProducts] = await Promise.all([getInitialMarketRanking(), getInitialPublicProducts()]);
  return <MarketPageContent initialRanking={initialRanking} initialProducts={initialProducts}/>;
}
