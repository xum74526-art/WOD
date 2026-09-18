import type { Metadata } from "next";
import { ChartLineUp, Cpu, Factory, Wrench } from "@phosphor-icons/react/dist/ssr";
import { CommunityFeed } from "@/components/community-feed";
import { SiteHeader } from "@/components/site-header";
import { I18nText } from "@/components/locale-root";

export const metadata: Metadata = { title: "社群", description: "交流 GPU、AI 與算力技術，查看平台算力行情。" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function CommunityPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const value = (key: string) => typeof params[key] === "string" ? params[key] : undefined;
  const page = Math.max(1, Number.parseInt(value("page") ?? "1", 10) || 1);
  return (
    <div className="site-page public-v2 community-public-page">
      <SiteHeader />
      <main className="public-data-page community-page">
        <header className="community-hero">
          <div className="community-hero__copy">
            <p className="hero-eyebrow">算力星图 COMPUTE COMMUNITY</p>
            <h1><I18nText id="community.title" zh="看懂算力，再做选择"/></h1>
            <p><I18nText id="community.description" zh="交流 GPU 使用、硬件配置和基础设施经验，并查看算力星图自有平台行情。"/></p>
          </div>
          <aside className="community-coverage" aria-label="社区内容范围">
            <header>
              <div><span><I18nText id="community.scope" zh="社区范围"/></span><strong><I18nText id="community.fourTopics" zh="覆盖 4 个主题"/></strong></div>
              <small>COMPUTE COMMUNITY</small>
            </header>
            <div className="community-coverage__grid">
              <article><span><ChartLineUp size={20}/></span><div><small>GPU MARKET</small><strong><I18nText id="community.topic.market" zh="价格与供需"/></strong></div></article>
              <article><span><Cpu size={20}/></span><div><small>HARDWARE</small><strong><I18nText id="community.topic.hardware" zh="GPU 与硬件"/></strong></div></article>
              <article><span><Factory size={20}/></span><div><small>INFRASTRUCTURE</small><strong><I18nText id="community.topic.infrastructure" zh="算力与数据中心"/></strong></div></article>
              <article><span><Wrench size={20}/></span><div><small>PRACTICE</small><strong><I18nText id="community.topic.industry" zh="技术实践"/></strong></div></article>
            </div>
            <footer><span className="signal-dot"/><I18nText id="community.refresh" zh="平台行情与社区内容持续更新"/></footer>
          </aside>
        </header>
        <CommunityFeed initialQuery={value("q") ?? ""} initialPage={page} />
      </main>
    </div>
  );
}
