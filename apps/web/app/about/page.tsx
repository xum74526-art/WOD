import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "关于 北斗 kai", description: "了解北斗 kai 未来算力中心的交付方法与责任模型。" };

const principles = [
  ["可预期", "按已指定的模型、版本、区域及服务时段安排容量。"],
  ["可比较", "以一致的服务参数及计量方式描述不同供应商的容量。"],
  ["可验证", "以 Chat Completions 用量及服务质量记录交付结果。"],
];
const roles = [
  ["机构客户", "配置团队权限及算力需求", "账户安全、用量管理、数据处理及服务使用"],
  ["容量供应商", "接入 Provider 并登记可用容量", "容量来源、服务质量、计量证据及异常补救"],
  ["北斗 kai 运营团队", "协调容量、监测质量及处理异常", "接入审批、服务监察、权限隔离及运营连续性"],
];

export default function AboutPage() {
  return <div className="site-page kai-company-page"><SiteHeader/><main>
    <header className="kai-company-hero"><p className="hero-eyebrow">北斗 kai / FUTURE COMPUTE CENTER</p><h1>交付 AI 算力，<br/>构筑稳健未来。</h1><p>北斗 kai 面向机构，统一不同供应商的模型服务标准，按指定时段协调容量，持续监测服务质量，并交付真实 Chat Completions 服务。</p></header>
    <section className="kai-company-section"><header><p className="hero-eyebrow">北斗 kai 的方法</p><h2>稳健算力，始于可预期的交付</h2><p>把分散的模型服务容量整理成机构能够规划、比较及核对的服务，让算力从供应能力走向真实工作负载。</p></header><div className="kai-principle-grid">{principles.map(([title, text], index) => <article key={title}><small>0{index + 1}</small><h3>{title}</h3><p>{text}</p></article>)}</div></section>
    <section className="kai-company-section"><header><p className="hero-eyebrow">RESPONSIBILITY MODEL</p><h2>清晰分工，持续交付</h2><p>机构客户、容量供应商及北斗 kai 运营团队各自承担清楚、可追溯的服务责任。</p></header><div className="kai-role-table"><div><span>参与方</span><span>能力</span><span>责任</span></div>{roles.map(([role, capability, responsibility]) => <article key={role}><h3>{role}</h3><p>{capability}</p><p>{responsibility}</p></article>)}</div></section>
    <section className="kai-company-cta"><div><p className="hero-eyebrow">INSTITUTIONAL ACCESS</p><h2>规划下一段算力容量</h2><p>如贵机构正为指定模型、区域或时段规划容量，请联系北斗 kai。</p></div><Link className="primary-link" href="/contact">联系我们 <ArrowRight size={16}/></Link></section>
  </main><SiteFooter/></div>;
}
