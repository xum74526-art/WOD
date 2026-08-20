import type { Metadata } from "next";
import { ChartLineUp, Cpu, Factory, NewspaperClipping } from "@phosphor-icons/react/dist/ssr";
import { CommunityFeed } from "@/components/community-feed";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "算力社区", description: "发现 GPU、AI、云计算与算力行业的最新内容。" };

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function CommunityPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const value = (key: string) => typeof params[key] === "string" ? params[key] : undefined;
  const requestedCategory = value("category") ?? "all";
  const category = ["all", "market", "hardware", "compute", "policy"].includes(requestedCategory) ? requestedCategory : "all";
  const page = Math.max(1, Number.parseInt(value("page") ?? "1", 10) || 1);
  return (
    <div className="site-page">
      <SiteHeader />
      <main className="public-data-page community-page">
        <header className="community-hero">
          <div className="community-hero__copy">
            <p className="hero-eyebrow">KAI COMPUTE COMMUNITY</p>
            <h1>看懂算力，<br /><em>再做选择</em></h1>
            <p>聚合 GPU 价格、硬件、基础设施与产业动态，为服务器采购和租用提供更清晰的判断依据。</p>
          </div>
          <aside className="community-coverage" aria-label="算力社区内容范围">
            <header>
              <div><span>情报范围</span><strong>覆盖 4 个主题</strong></div>
              <small>COMPUTE INTELLIGENCE</small>
            </header>
            <div className="community-coverage__grid">
              <article><span><ChartLineUp size={20} /></span><div><small>GPU MARKET</small><strong>价格与供需</strong></div></article>
              <article><span><Cpu size={20} /></span><div><small>HARDWARE</small><strong>GPU 与硬件</strong></div></article>
              <article><span><Factory size={20} /></span><div><small>INFRASTRUCTURE</small><strong>算力与数据中心</strong></div></article>
              <article><span><NewspaperClipping size={20} /></span><div><small>INDUSTRY</small><strong>政策与产业</strong></div></article>
            </div>
            <footer><span className="signal-dot" />每 30 分钟检查内容来源更新</footer>
          </aside>
        </header>
        <CommunityFeed initialCategory={category} initialQuery={value("q") ?? ""} initialPage={page} />
      </main>
    </div>
  );
}
