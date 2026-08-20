import Link from "next/link";
import { ArrowRight, Buildings, ClipboardText, UsersThree } from "@phosphor-icons/react/dist/ssr";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { GpuDailyTrendChart } from "@/components/gpu-candlestick-chart";
import { LiveMarketPanel } from "@/components/live-market-panel";
import { MerchantResourceMarket } from "@/components/merchant-resource-market";

export default function HomePage() {
  return (
    <div className="site-page home-v2">
      <SiteHeader />
      <main>
        <section className="home-v2-hero">
          <div className="home-v2-hero__copy">
            <span className="home-v2-kicker">GPU SERVER MARKETPLACE</span>
            <h1>GPU 服务器，<br /><em>按需即用</em></h1>
            <p>透明比较 GPU 型号、配置与小时价格。完成支付后，平台自动授权你的 SSH 公钥，复制命令即可连接。</p>
            <ol className="home-v2-rental-flow" aria-label="GPU 服务器租用流程">
              <li>
                <span>01</span>
                <div><strong>选定服务器</strong><small>比较 GPU、显存、区域与小时价格</small></div>
              </li>
              <li>
                <span>02</span>
                <div><strong>提交 SSH 公钥</strong><small>付款后只下发公钥，平台不接收私钥</small></div>
              </li>
              <li>
                <span>03</span>
                <div><strong>复制连接命令</strong><small>Agent 自动授权，到期自动撤销</small></div>
              </li>
            </ol>
            <div className="home-v2-actions">
              <Link className="primary-link primary-link--large" href="/market">浏览 GPU 服务器 <ArrowRight size={17}/></Link>
              <Link className="outline-link outline-link--large" href="/supplier/apply">商家发布服务器</Link>
            </div>
            <ul className="home-v2-assurances" aria-label="平台租用特性">
              <li>按小时透明计费</li>
              <li>SSH 公钥自动授权</li>
              <li>到期自动撤销</li>
            </ul>
          </div>
          <GpuDailyTrendChart />
        </section>

        <section className="home-v2-section"><MerchantResourceMarket limit={4} /></section>

        <section className="home-v2-section" aria-label="GPU 算力行情预览">
          <LiveMarketPanel featured />
        </section>

        <section className="home-v2-section home-supply-paths" aria-label="算力生态入口">
          <article>
            <span className="home-supply-paths__icon"><UsersThree size={22} /></span>
            <div>
              <small>COMPUTE COMMUNITY</small>
              <h2>算力社区</h2>
              <p>查看 GPU、AI 基础设施和算力市场动态，保留原有行业内容入口。</p>
            </div>
            <Link href="/community">进入算力社区 <ArrowRight size={14} /></Link>
          </article>
          <article>
            <span className="home-supply-paths__icon"><ClipboardText size={22} /></span>
            <div>
              <small>BUY REQUESTS</small>
              <h2>公开求购</h2>
              <p>买家发布 GPU 与服务器需求，商家查看需求并提供匹配的资源方案。</p>
            </div>
            <Link href="/requests">查看求购市场 <ArrowRight size={14} /></Link>
          </article>
        </section>

        <section className="home-v2-section home-request-cta" aria-labelledby="merchant-cta-title">
          <div>
            <span>你有空闲服务器？</span>
            <h2 id="merchant-cta-title">登记服务器并接入 KAI Agent</h2>
            <p>管理员审核服务器与 Agent 状态后发布；买家购买时由 Agent 自动下发公钥，商家无需手工发送密码。</p>
          </div>
          <div><Link className="primary-link" href="/supplier/apply"><Buildings size={15}/>申请成为商家</Link></div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
