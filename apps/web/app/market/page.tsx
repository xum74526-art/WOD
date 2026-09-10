import type { Metadata } from "next";
import { MarketPageContent } from "@/components/market-page-content";
import { getInitialMarketRanking, getInitialPublicProducts } from "@/lib/server/public-page-data";

export const metadata: Metadata = { title: "算力市場", description: "分別瀏覽 KAI 自營與商家發佈的算力資源，提交需求後由人工聯絡確認方案。" };

export default async function MarketPage() {
  const [initialRanking, initialProducts] = await Promise.all([getInitialMarketRanking(), getInitialPublicProducts()]);
  return <MarketPageContent initialRanking={initialRanking} initialProducts={initialProducts}/>;
}
