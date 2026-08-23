"use client";

import Link from "next/link";
import { ArrowRight, Cpu, HardDrives, MapPin } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { getCurrentUser, type AuthUser } from "@/lib/api";
import { listPublicProducts, type PublicProduct } from "@/lib/commerce-api";
import { errorMessage } from "@/lib/commerce-ui";
import { useI18n } from "@/components/locale-root";
import { localizeMarketProductName, localizeMarketRegion, localizeSupplierName } from "@/lib/market-localization";

type ViewerRole = AuthUser["role"] | "guest" | "loading";

export function MerchantResourceMarket({ limit, initialRows = null }: { limit?: number; initialRows?: PublicProduct[] | null }) {
  const { locale, t } = useI18n();
  const [rows, setRows] = useState<PublicProduct[]>(initialRows ?? []);
  const [viewerRole, setViewerRole] = useState<ViewerRole>("loading");
  const [loading, setLoading] = useState(initialRows === null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (initialRows === null) {
      listPublicProducts()
        .then((result) => setRows(result.data))
        .catch((reason) => setError(errorMessage(reason)))
        .finally(() => setLoading(false));
    }
    getCurrentUser()
      .then(({ user }) => setViewerRole(user.role))
      .catch(() => setViewerRole("guest"));
  }, [initialRows]);

  const displayRows = typeof limit === "number" ? rows.slice(0, limit) : rows;

  const marketDescription = viewerRole === "supplier"
    ? (locale === "en" ? "This is the public market buyers see. Products, stock, and orders use the unified business platform." : "这里是买家看到的公开市场；商品、库存与订单使用统一业务平台。")
    : viewerRole === "admin"
      ? (locale === "en" ? "Public market preview. Review and publish servers from the admin console." : "这里是公开市场预览；服务器审核与发布请在管理控制台完成。")
      : (locale === "en" ? "Browse available compute resources. Suppliers deliver SSH access after purchase." : "浏览可用算力资源；下单后由商家交付 SSH 信息。");

  return <section className="merchant-market" aria-labelledby="merchant-market-title">
    <header><div><p>北斗 kai SHARED COMPUTE</p><h2 id="merchant-market-title">{t("market.shared", "共享算力资源")}</h2><span>{marketDescription}</span></div></header>
    {loading ? <div className="merchant-market__state">{t("market.loading", "正在读取商家资源…")}</div> : error ? <div className="merchant-market__state is-error">{error}</div> : displayRows.length === 0 ? <div className="merchant-market__state"><strong>{t("market.empty", "暂无已发布资源")}</strong><span>{t("market.emptyDesc", "商家资源审核通过后会自动出现在这里。")}</span></div> : <div className="merchant-resource-grid">{displayRows.map((row) => {
      const legacyTestResource = row.name === "错误型号资源";
      const action = viewerRole === "supplier" ? { href: "/supplier/resources", label: t("market.manage", "管理服务器") } : viewerRole === "admin" ? { href: "/admin/resources", label: t("market.review", "审核服务器") } : viewerRole === "loading" ? { href: `/market/products/${row.id}`, label: t("market.view", "查看服务器") } : { href: `/market/products/${row.id}`, label: t("market.rent", "查看并租用") };
      const displayName = localizeMarketProductName(legacyTestResource ? `${row.gpu_model} ${row.gpu_memory_gb}GB 独占训练节点` : row.name, locale);
      const supplierName = localizeSupplierName(row.source_name, locale);
      const displayCpuCores = row.cpu_cores || (legacyTestResource ? 64 : null);
      const displayRamGb = row.ram_gb || (legacyTestResource ? 512 : null);
      const status = row.purchasable ? t("market.available", "可下单") : legacyTestResource ? (locale === "en" ? "Published" : "已发布") : t("market.unavailable", "暂不可租");
      return <article key={row.id}>
        <header><div><small>{row.supplier_id ? <Link href={`/stores/${row.supplier_id}`}>{supplierName}</Link> : supplierName}</small><h3>{displayName}</h3></div><span className={!row.server_online && !legacyTestResource ? "is-offline" : ""}>{status}</span></header>
        <div className="merchant-resource-gpu"><Cpu size={24}/><strong>{row.gpu_model}</strong><span>{row.gpu_memory_gb}GB</span></div>
        <dl><div><dt><MapPin size={13}/>{t("market.region", "区域")}</dt><dd>{localizeMarketRegion(row.region, locale)}</dd></div><div><dt><HardDrives size={13}/>{t("market.config", "配置")}</dt><dd>{displayCpuCores || "—"}C / {displayRamGb || "—"}GB</dd></div></dl>
        <footer><div><small>{t("market.hourly", "每小时价格")}</small><strong>{row.unit_price_ch.toLocaleString(locale === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: 6 })} {locale === "en" ? "CH / GPU·hour" : "卡时 / GPU·小时"}</strong></div><Link href={action.href}>{action.label} <ArrowRight size={15}/></Link></footer>
      </article>;
    })}</div>}
  </section>;
}
