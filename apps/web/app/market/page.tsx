import type { Metadata } from "next";
import { MerchantResourceMarket } from "@/components/merchant-resource-market";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "算力市场", description: "浏览已审核商家的可租用算力资源。" };

export default function MarketPage() {
  return <div className="site-page"><SiteHeader /><main className="public-data-page market-page"><header><p className="hero-eyebrow">VERIFIED COMPUTE MARKET</p><h1>算力市场</h1><p>选择已审核且 Agent 在线的算力资源，使用自己的 SSH 公钥按小时租用。</p></header><MerchantResourceMarket /></main></div>;
}
