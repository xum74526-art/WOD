import type { Metadata } from "next";
import { LiveMarketPanel } from "@/components/live-market-panel";
import { SiteHeader } from "@/components/site-header";
import { I18nText } from "@/components/locale-root";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";
import { getInitialMarketDashboard } from "@/lib/server/public-page-data";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "算力行情 | KAI星算",
      description: "查看不同 GPU 型號的港幣價格變化與目前市場區間。",
    },
    "zh-Hans": {
      title: "算力行情 | KAI星算",
      description: "查看不同 GPU 型号的人民币价格变化与当前市场区间。",
    },
    en: {
      title: "GPU Compute Market Trends | KAI Star",
      description: "Compare USD price movements and current market ranges across GPU models.",
    },
  });
}

export default async function TrendsPage() {
  const initialData = await getInitialMarketDashboard();
  return <div className="site-page public-v2 trend-public-page"><SiteHeader/><main className="public-data-page trend-page"><header><p className="hero-eyebrow">GPU PRICE TRENDS</p><h1><I18nText id="trends.title" zh="GPU 算力行情"/></h1><p><I18nText id="trends.description" zh="查看不同 GPU 型号按当前语言货币显示的价格变化与市场区间。"/></p></header><LiveMarketPanel initialData={initialData}/></main></div>;
}
