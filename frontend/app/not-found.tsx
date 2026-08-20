import Link from "next/link";
import { SiteHeader } from "@/components/site-header";

export default function NotFound() {
  return <div className="site-page"><SiteHeader /><main className="simple-page"><section><p className="hero-eyebrow">PAGE NOT FOUND</p><h1>没有找到这个页面</h1><p>链接可能已经调整，请返回首页或进入工作台。</p><Link className="outline-link" href="/">返回首页</Link></section></main></div>;
}

