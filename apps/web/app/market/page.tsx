import type { Metadata } from "next";
import { MarketPageContent } from "@/components/market-page-content";

export const metadata: Metadata = { title: "算力市场", description: "浏览已审核商家的可租用算力资源。" };

export default function MarketPage() {
  return <MarketPageContent/>;
}
