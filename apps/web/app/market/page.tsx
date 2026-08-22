import type { Metadata } from "next";
import { MarketPageContent } from "@/components/market-page-content";
import { getInitialMarketRanking, getInitialPublicProducts } from "@/lib/server/public-page-data";

export const metadata: Metadata = { title: "算力市场", description: "浏览已审核商家的可租用算力资源。" };

export default async function MarketPage() {
  const [initialRanking, initialProducts] = await Promise.all([getInitialMarketRanking(), getInitialPublicProducts()]);
  return <MarketPageContent initialRanking={initialRanking} initialProducts={initialProducts}/>;
}
