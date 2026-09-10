import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { RequestMarketplace } from "@/components/request-marketplace";

export const metadata: Metadata = { title: "求購" };

export default function RequestsPage() {
  return <div className="site-page public-v2"><SiteHeader /><main className="public-data-page request-market-page"><header><p className="hero-eyebrow">BUY REQUESTS / LIVE BOARD</p><h1>把算力需求写清楚，<br />让报价可比较</h1><p>公开采购任务只展示业务必要字段。联系人和买家身份不会出现在市场列表中。</p></header><RequestMarketplace /></main></div>;
}
