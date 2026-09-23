import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import { SupplierApplicationForm } from "@/components/supplier-application-form";
import { I18nText } from "@/components/locale-root";

export const metadata: Metadata = { title: "商家入駐" };

export default function SupplierApplyPage() {
  return <div className="site-page public-v2 supplier-apply-page"><SiteHeader /><main className="application-page"><section className="application-intro"><p className="hero-eyebrow">SUPPLIER APPLICATION</p><h1><I18nText id="supplier.apply.title" zh="把真实服务器带到KAI星算" /></h1><p><I18nText id="supplier.apply.description" zh="商家入驻资料和主体实名认证分别提交、分别审核；两项均通过后才可进入商家后台。" /></p><ul><li><I18nText id="supplier.apply.step.identity" zh="个人或企业主体实名认证" /></li><li><I18nText id="supplier.apply.step.source" zh="服务器来源、位置与能力说明" /></li><li><I18nText id="supplier.apply.step.inventory" zh="商品参数与库存由商家自行申报" /></li></ul></section><section className="application-form-panel"><h2><I18nText id="supplier.apply.formTitle" zh="商家入驻申请" /></h2><p><I18nText id="supplier.apply.formDescriptionBefore" zh="可以先提交入驻资料；管理员审核通过前，还需完成 " /><Link href="/account/verification"><I18nText id="supplier.apply.formDescriptionLink" zh="实名认证" /></Link><I18nText id="supplier.apply.formDescriptionAfter" zh="。" /></p><SupplierApplicationForm /></section></main></div>;
}
