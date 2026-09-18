"use client";

import Link from "next/link";
import { Brand } from "@/components/brand";
import { useI18n } from "@/components/locale-root";

export function SiteFooter() {
  const { t } = useI18n();
  return (
    <footer className="site-footer site-footer--kai">
      <div className="site-footer__brand">
        <Brand />
        <p>{t("footer.description", "算力星图未来算力中心。连接机构需求、容量供应商与可核对的算力交付。")}</p>
        <small>{t("footer.disclaimer", "© 2026 算力星图。服务及参数以正式服务文件及生效版本为准。")}</small>
      </div>
      <nav aria-label={t("footer.product", "产品")}><strong>{t("footer.product", "产品")}</strong><Link href="/market">{t("nav.market", "算力市场")}</Link><Link href="/trend">{t("nav.trends", "算力行情")}</Link><Link href="/download">{t("nav.download", "下载 App")}</Link><Link href="/account/assets">{t("footer.assets", "我的资产")}</Link></nav>
      <nav aria-label={t("footer.ecosystem", "生态")}><strong>{t("footer.ecosystem", "生态")}</strong><Link href="/community">{t("nav.community", "资讯")}</Link><Link href="/account/requests">{t("footer.requests", "需求与方案")}</Link><Link href="/supplier/apply">{t("nav.supplierApply", "商家入驻")}</Link></nav>
      <nav aria-label={t("footer.company", "公司")}><strong>{t("footer.company", "公司")}</strong><Link href="/about">{t("footer.about", "关于算力星图")}</Link><Link href="/contact">{t("footer.contact", "联系我们")}</Link></nav>
      <nav aria-label={t("footer.support", "支持")}><strong>{t("footer.support", "支持")}</strong><Link href="/help">{t("footer.help", "帮助中心")}</Link><Link href="/terms">{t("footer.terms", "用户协议")}</Link><Link href="/privacy">{t("footer.privacy", "隐私政策")}</Link><Link href="/image-attributions">{t("footer.imageAttributions", "图片来源与许可")}</Link></nav>
    </footer>
  );
}
