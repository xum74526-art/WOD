import type { Metadata } from "next";
import { ArrowUpRight, EnvelopeSimple } from "@phosphor-icons/react/dist/ssr";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "联系我们", description: "联系北斗 kai 未来算力中心，申请机构接入。" };

export default function ContactPage() {
  return <div className="site-page public-v2 kai-company-page"><SiteHeader/><main>
    <header className="kai-company-hero kai-contact-hero"><p className="hero-eyebrow">CONTACT / INSTITUTIONAL ACCESS</p><h1>规划下一段<br/>算力容量。</h1><p>如贵机构正为指定模型、区域或时段规划容量，请联系北斗 kai。我们将根据需求与可用容量安排后续接入。</p></header>
    <section className="kai-contact-channel"><EnvelopeSimple size={26}/><div><p className="hero-eyebrow">OFFICIAL CONTACT</p><h2>机构接入</h2><p>这是北斗 kai 对外公布的机构接入联系邮箱。</p></div><a href="mailto:access@kai.com">access@kai.com <ArrowUpRight size={18}/></a></section>
    <section className="kai-contact-notes"><header><p className="hero-eyebrow">BEFORE CONTACT</p><h2>建议一并说明</h2></header><ol><li><span>01</span><p><strong>模型与版本</strong>计划使用的模型和版本要求。</p></li><li><span>02</span><p><strong>区域与时段</strong>服务区域、时区和计划使用时段。</p></li><li><span>03</span><p><strong>容量需求</strong>预期容量单位及服务目标。</p></li></ol></section>
  </main><SiteFooter/></div>;
}
