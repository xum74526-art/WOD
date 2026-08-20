import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import { SupplierApplicationForm } from "@/components/supplier-application-form";

export const metadata: Metadata = { title: "商家入驻" };

export default function SupplierApplyPage() {
  return <div className="site-page"><SiteHeader /><main className="application-page"><section className="application-intro"><p className="hero-eyebrow">SUPPLIER APPLICATION</p><h1>把真实服务器带到 KAI</h1><p>先完成主体实名认证，再提交商家入驻申请。两项均通过后才会获得商家后台权限。</p><ul><li>个人或企业主体实名认证</li><li>服务器来源、位置与能力</li><li>SSH 公钥授权与到期撤销</li></ul></section><section className="application-form-panel"><h2>商家入驻申请</h2><p>尚未实名？先前往 <Link href="/account/verification">实名认证</Link>，提交后可继续填写入驻资料。</p><SupplierApplicationForm /></section></main></div>;
}
