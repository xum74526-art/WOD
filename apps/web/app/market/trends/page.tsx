import type { Metadata } from "next";
import { LiveMarketPanel } from "@/components/live-market-panel";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "算力行情" };

export default function TrendsPage() {
  return <div className="site-page"><SiteHeader /><main className="public-data-page trend-page"><header><p className="hero-eyebrow">GPU PRICE TRENDS</p><h1>GPU 算力行情</h1><p>查看不同 GPU 型号的卡时价格变化与当前市场区间。</p></header><LiveMarketPanel /></main></div>;
}
