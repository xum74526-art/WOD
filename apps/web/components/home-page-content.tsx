"use client";

import Link from "next/link";
import { ArrowRight, Buildings, ClipboardText, UsersThree } from "@phosphor-icons/react";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { GpuDailyTrendChart } from "@/components/gpu-candlestick-chart";
import { MerchantResourceMarket } from "@/components/merchant-resource-market";
import { MarketPulseRail } from "@/components/market-pulse-rail";
import { useI18n } from "@/components/locale-root";
import type { PublicProduct } from "@/lib/commerce-api";
import type { InitialGpuTrend, PublicMarketRanking } from "@/lib/public-data";

type Props = {
  initialRanking: PublicMarketRanking | null;
  initialProducts: PublicProduct[] | null;
  initialTrend: InitialGpuTrend | null;
};

export function HomePageContent({ initialRanking, initialProducts, initialTrend }: Props) {
  const { locale, t } = useI18n();
  return (
    <div className="site-page home-v2">
      <SiteHeader />
      <main>
        <section className="home-v2-hero">
          <div className="home-v2-hero__copy">
            <span className="home-v2-kicker">GPU SERVER MARKETPLACE</span>
            <h1>{locale === "en" ? <>GPU servers,<br/><em>ready on demand</em></> : <>GPU 服务器，<br/><em>按需即用</em></>}</h1>
            <p>{t("home.description", "透明比较 GPU 型号、配置与小时价格。完成支付后，平台自动授权你的 SSH 公钥，复制命令即可连接。")}</p>
            <div className="home-v2-actions">
              <Link className="primary-link primary-link--large" href="/market">{t("home.browse", "浏览 GPU 服务器")} <ArrowRight size={17}/></Link>
              <Link className="outline-link outline-link--large" href="/supplier/apply">{t("home.publish", "商家发布服务器")}</Link>
            </div>
            <ul className="home-v2-assurances" aria-label="平台租用特性"><li>{t("home.assurance1", "按小时透明计费")}</li><li>{t("home.assurance2", "SSH 公钥自动授权")}</li><li>{t("home.assurance3", "到期自动撤销")}</li></ul>
          </div>
          <div className="home-v2-hero__instrument"><GpuDailyTrendChart initialData={initialTrend} /></div>
        </section>

        <section className="home-v2-pulse-shell" aria-label={locale === "en" ? "Live GPU rental prices" : "实时 GPU 租赁价格"}><MarketPulseRail initialData={initialRanking} /></section>

        <section className="home-v2-flow-shell" aria-labelledby="home-rental-flow-title">
          <header><span>HOW IT WORKS</span><h2 id="home-rental-flow-title">{locale === "en" ? "From selection to SSH in three clear steps" : "从选型到 SSH，只需三步"}</h2><p>{locale === "en" ? "Choose a verified server, add your public key, and connect without sharing a private key." : "选择已核验的服务器、提交公钥、复制连接命令。私钥始终留在你手中。"}</p></header>
          <ol className="home-v2-rental-flow" aria-label={locale === "en" ? "GPU server rental flow" : "GPU 服务器租用流程"}>
            <li><span>01</span><div><strong>{t("home.step1.title", "选定服务器")}</strong><small>{t("home.step1.desc", "比较 GPU、显存、区域与小时价格")}</small></div></li>
            <li><span>02</span><div><strong>{t("home.step2.title", "提交 SSH 公钥")}</strong><small>{t("home.step2.desc", "付款后只下发公钥，平台不接收私钥")}</small></div></li>
            <li><span>03</span><div><strong>{t("home.step3.title", "复制连接命令")}</strong><small>{t("home.step3.desc", "Agent 自动授权，到期自动撤销")}</small></div></li>
          </ol>
        </section>

        <section className="home-v2-section"><MerchantResourceMarket limit={4} initialRows={initialProducts} /></section>
        <section className="home-v2-section home-supply-paths" aria-label="算力生态入口">
          <article><span className="home-supply-paths__icon"><UsersThree size={22} /></span><div><small>COMPUTE COMMUNITY</small><h2>{t("home.community.title", "算力社区")}</h2><p>{t("home.community.desc", "查看 GPU、AI 基础设施和算力市场动态，保留原有行业内容入口。")}</p></div><Link href="/community">{t("home.community.action", "进入算力社区")} <ArrowRight size={14}/></Link></article>
          <article><span className="home-supply-paths__icon"><ClipboardText size={22} /></span><div><small>BUY REQUESTS</small><h2>{t("home.requests.title", "公开求购")}</h2><p>{t("home.requests.desc", "买家发布 GPU 与服务器需求，商家查看需求并提供匹配的资源方案。")}</p></div><Link href="/account/requests">{t("home.requests.action", "查看求购市场")} <ArrowRight size={14}/></Link></article>
        </section>
        <section className="home-v2-section home-request-cta" aria-labelledby="merchant-cta-title"><div><span>{t("home.cta.kicker", "你有空闲服务器？")}</span><h2 id="merchant-cta-title">{t("home.cta.title", "登记服务器并接入 KAI Agent")}</h2><p>{t("home.cta.desc", "管理员审核服务器与 Agent 状态后发布；买家购买时由 Agent 自动下发公钥，商家无需手工发送密码。")}</p></div><div><Link className="primary-link" href="/supplier/apply"><Buildings size={15}/>{t("home.cta.action", "申请成为商家")}</Link></div></section>
      </main>
      <SiteFooter />
    </div>
  );
}
