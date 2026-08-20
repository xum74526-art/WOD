import type { Metadata } from "next";
import { EnvelopeSimple } from "@phosphor-icons/react/dist/ssr";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "帮助与客服" };

export default function SupportPage() {
  return <div className="site-page"><SiteHeader /><main className="public-data-page"><header><p className="hero-eyebrow">SUPPORT</p><h1>帮助与联系</h1><p>账户和订单问题可先查看帮助中心；机构接入与算力容量需求请通过 KAI 官方邮箱联系。</p></header><a className="support-contact-card" href="mailto:access@kai.com"><EnvelopeSimple size={24}/><span><small>机构接入</small><strong>access@kai.com</strong><em>发送邮件联系 KAI</em></span></a></main><SiteFooter /></div>;
}
