import type { Metadata } from "next";
import { MerchantResourceMarket } from "@/components/merchant-resource-market";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "服务器市场", description: "浏览已审核商家的可租用服务器。" };

export default function MarketPage() {
  return <div className="site-page"><SiteHeader /><main className="public-data-page market-page"><header><p className="hero-eyebrow">VERIFIED SERVER MARKET</p><h1>服务器市场</h1><p>选择已审核且 Agent 在线的服务器，使用自己的 SSH 公钥按小时租用。</p></header><MerchantResourceMarket /></main></div>;
}
