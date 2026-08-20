import Link from "next/link";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

type SimplePageProps = {
  title: string;
  description: string;
};

export function SimplePage({ title, description }: SimplePageProps) {
  return (
    <div className="site-page">
      <SiteHeader />
      <main className="public-data-page kai-simple-page">
        <header><p className="hero-eyebrow">KAI / INFORMATION</p><h1>{title}</h1><p>{description}</p></header>
        <section><p>此页面将在对应业务服务接入时补充正式内容，目前不会显示虚构条款或状态。</p><Link className="outline-link" href="/"><ArrowLeft size={16} />返回首页</Link></section>
      </main>
      <SiteFooter />
    </div>
  );
}
