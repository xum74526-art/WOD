import type { Metadata } from "next";
import { LiveMarketPanel } from "@/components/live-market-panel";
import { SiteHeader } from "@/components/site-header";
import { I18nText } from "@/components/locale-root";

export const metadata: Metadata = { title: "算力行情" };

export default function TrendsPage() {
  return <div className="site-page public-v2 trend-public-page"><SiteHeader/><main className="public-data-page trend-page"><header><p className="hero-eyebrow">GPU PRICE TRENDS</p><h1><I18nText id="trends.title" zh="GPU 算力行情"/></h1><p><I18nText id="trends.description" zh="查看不同 GPU 型号的卡时价格变化与当前市场区间。"/></p></header><LiveMarketPanel/></main></div>;
}
