import type { Metadata } from "next";
import { MarketPageContent } from "@/components/market-page-content";
import { getInitialMarketRanking, getInitialPublicProducts } from "@/lib/server/public-page-data";

export const metadata: Metadata = { title: "算力市场", description: "分别浏览 KAI 自营与商家发布的可购买算力资源，并在下单前核对卖方与履约方式。" };

export default async function MarketPage() {
  const [initialRanking, initialProducts] = await Promise.all([getInitialMarketRanking(), getInitialPublicProducts()]);
  return <MarketPageContent initialRanking={initialRanking} initialProducts={initialProducts}/>;
}
