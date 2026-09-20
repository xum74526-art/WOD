"use client";

import Link from "next/link";
import { ArrowRight, HardDrives, MapPin, ShieldCheck, TerminalWindow } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getCurrentUser, type AuthUser } from "@/lib/api";
import { listPublicProducts, type PublicProduct } from "@/lib/commerce-api";
import { errorMessage } from "@/lib/commerce-ui";
import { useI18n } from "@/components/locale-root";
import { localizeMarketProductName, localizeMarketRegion, localizeSupplierName } from "@/lib/market-localization";
import { ProductImage } from "@/components/product-image";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";

type ViewerRole = AuthUser["role"] | "guest" | "loading";
type MarketSource = "kai" | "wod";
type SourceCatalog = {
  rows: PublicProduct[];
  page: number;
  total: number;
  totalPages: number;
  initialized: boolean;
  loading: boolean;
};
type SourceCatalogs = Record<MarketSource, SourceCatalog>;

const MARKET_PAGE_SIZE = 24;

function isKaiProduct(product: PublicProduct) {
  return product.seller_type === "kai_self_operated" || product.market_source === "kai";
}

function mergeProducts(current: PublicProduct[], incoming: PublicProduct[]) {
  const products = new Map(current.map((row) => [row.id, row]));
  incoming.forEach((row) => products.set(row.id, row));
  return Array.from(products.values());
}

function initialSourceCatalogs(rows: PublicProduct[] | null): SourceCatalogs {
  const initial = rows ?? [];
  const catalog = (sourceRows: PublicProduct[]): SourceCatalog => ({
    rows: mergeProducts([], sourceRows),
    page: 0,
    total: sourceRows.length,
    totalPages: 0,
    initialized: false,
    loading: false,
  });
  return {
    kai: catalog(initial.filter(isKaiProduct)),
    wod: catalog(initial.filter((row) => !isKaiProduct(row))),
  };
}

export function MerchantResourceMarket({ limit, initialRows = null }: { limit?: number; initialRows?: PublicProduct[] | null }) {
  const { locale, t } = useI18n();
  const { capabilities } = usePlatformCapabilities();
  const directTradeEnabled = capabilities.direct_trade_enabled === true;
  const matchmakingEnabled = capabilities.matchmaking_enabled === true;
  const [activeSource, setActiveSource] = useState<MarketSource>("kai");
  const [catalogs, setCatalogs] = useState<SourceCatalogs>(() => initialSourceCatalogs(initialRows));
  const [viewerRole, setViewerRole] = useState<ViewerRole>("loading");
  const [errors, setErrors] = useState<Partial<Record<MarketSource, string>>>({});

  useEffect(() => {
    getCurrentUser()
      .then(({ user }) => setViewerRole(user.role))
      .catch(() => setViewerRole("guest"));
  }, []);

  const loadSourcePage = useCallback(async (source: MarketSource, page: number, append: boolean) => {
    setCatalogs((current) => ({ ...current, [source]: { ...current[source], loading: true } }));
    setErrors((current) => ({ ...current, [source]: "" }));
    try {
      const result = await listPublicProducts(source, page, MARKET_PAGE_SIZE);
      setCatalogs((current) => ({
        ...current,
        [source]: {
          rows: append ? mergeProducts(current[source].rows, result.data) : mergeProducts([], result.data),
          page: result.meta.page,
          total: result.meta.total,
          totalPages: result.meta.total_pages,
          initialized: true,
          loading: false,
        },
      }));
    } catch (reason) {
      setCatalogs((current) => ({ ...current, [source]: { ...current[source], initialized: true, loading: false } }));
      setErrors((current) => ({ ...current, [source]: errorMessage(reason) }));
    }
  }, []);

  useEffect(() => {
    const catalog = catalogs[activeSource];
    if (catalog.initialized || catalog.loading) return;
    void loadSourcePage(activeSource, 1, false);
  }, [activeSource, catalogs, loadSourcePage]);

  const catalog = catalogs[activeSource];
  const rows = catalog.rows;
  const displayRows = typeof limit === "number" ? rows.slice(0, limit) : rows;
  const sourceCopy = useMemo(() => activeSource === "kai" ? {
    eyebrow: "算力星图 SELF-OPERATED",
    title: t("market.kai.title", "算力星图自营"),
    description: directTradeEnabled
      ? t("market.kai.directDescription", "算力星图发布商品与价格，由平台统一安排人工交付并记录订单状态。")
      : t("market.kai.description", "算力星图发布资源信息，提交需求后由平台人工联系确认配置、价格与交付安排。"),
  } : {
    eyebrow: "MERCHANT LISTINGS",
    title: t("market.merchant.title", "商家资源"),
    description: directTradeEnabled
      ? t("market.merchant.directDescription", "商家发布资源参数与库存，下单后由对应商家人工交付。")
      : t("market.merchant.description", "商家发布资源参数与库存，提交需求后由对应商家人工联系确认方案。"),
  }, [activeSource, directTradeEnabled, t]);

  const roleNote = viewerRole === "supplier" && activeSource === "wod"
    ? t("market.merchant.supplierView", "这里就是买家看到的商家市场；上架商品、库存与买家需求共用统一业务平台。")
    : viewerRole === "admin" && activeSource === "wod"
      ? t("market.merchant.adminView", "公开商家市场预览；商家入驻资料审核与交易状态以统一业务平台为准。")
      : sourceCopy.description;
  const loading = catalog.loading;
  const error = errors[activeSource];
  const hasMore = typeof limit !== "number" && catalog.initialized && (catalog.page < catalog.totalPages || rows.length < catalog.total);

  return <section className="merchant-market" aria-labelledby="merchant-market-title">
    <header>
      <div><p>{sourceCopy.eyebrow}</p><h2 id="merchant-market-title">{sourceCopy.title}</h2><span>{roleNote}</span></div>
      <div className="merchant-market__source-switch" role="group" aria-label={t("market.sourceSwitch", "商品来源")}>
        <button type="button" className={activeSource === "kai" ? "is-active" : ""} aria-pressed={activeSource === "kai"} onClick={() => setActiveSource("kai")}>
          <strong>{t("market.kai.title", "算力星图自营")}</strong><small>{t("market.kai.short", "平台发布与履约")}</small>
        </button>
        <button type="button" className={activeSource === "wod" ? "is-active" : ""} aria-pressed={activeSource === "wod"} onClick={() => setActiveSource("wod")}>
          <strong>{t("market.merchant.title", "商家资源")}</strong><small>{t("market.merchant.short", "商家入驻资料审核通过后发布")}</small>
        </button>
      </div>
    </header>
    {loading && displayRows.length === 0 ? <div className="merchant-market__state">{t("market.loading", "正在读取算力资源…")}</div> : error && displayRows.length === 0 ? <div className="merchant-market__state is-error">{error}</div> : displayRows.length === 0 ? <div className="merchant-market__state"><strong>{activeSource === "kai" ? t("market.kai.empty", "暂无可购买的算力星图自营资源") : t("market.merchant.empty", "暂无已发布的商家资源")}</strong><span>{activeSource === "kai" ? t("market.kai.emptyDesc", "算力星图自营资源恢复库存后会显示在这里。") : t("market.merchant.emptyDesc", "商家发布商品后会显示在这里。")}</span></div> : <div className="merchant-resource-grid">{displayRows.map((row) => {
      const kaiSelfOperated = isKaiProduct(row);
      const sellerName = localizeSupplierName(row.seller_name || row.supplier_name || row.source_name, locale);
      const displayName = localizeMarketProductName(row.name, locale);
      const fulfillmentLabel = row.fulfillment_mode === "merchant_manual"
        ? t("market.fulfillment.merchant", "商家人工交付")
        : t("market.fulfillment.platform", "平台人工交付");
      const resourceClaimLabel = row.resource_claim_source === "merchant_declared" || (!row.resource_claim_source && !kaiSelfOperated)
        ? t("market.claim.merchant", "配置与库存由商家自行申报")
        : t("market.claim.kai", "商品信息由算力星图发布");
      const inquiryAvailable = matchmakingEnabled && row.inquiry_available !== false;
      const status = directTradeEnabled
        ? row.purchasable ? t("market.availableDirect", "可下单") : t("market.unavailableDirect", "暂不可租")
        : inquiryAvailable ? t("market.available", "可询价") : t("market.unavailable", "需求服务暂未开放");
      const sellerDetails = !kaiSelfOperated && (row.supplier_id != null || row.supplier_rating != null || row.supplier_order_count != null)
        ? [row.supplier_id != null ? `ID ${row.supplier_id}` : "", row.supplier_rating != null ? t("market.rating", "评分 {rating}", { rating: row.supplier_rating.toFixed(1) }) : "", row.supplier_order_count != null ? t("market.completedOrders", "已完成 {count} 单", { count: row.supplier_order_count }) : ""].filter(Boolean).join(" · ")
        : "";
      return <article data-market-source={kaiSelfOperated ? "kai" : "wod"} key={row.id}>
        <ProductImage className="merchant-resource-image" imageUrl={row.image_url} gpuModel={row.gpu_model}/>
        <header><div><small><b>{kaiSelfOperated ? t("market.kai.title", "算力星图自营") : t("market.merchant.listing", "商家资源")}</b> · {row.supplier_id && !kaiSelfOperated ? <Link href={`/stores/${row.supplier_id}`}>{sellerName}</Link> : sellerName}</small><h3>{displayName}</h3>{sellerDetails && <em>{sellerDetails}</em>}</div><span className={(directTradeEnabled ? !row.purchasable : !inquiryAvailable) ? "is-offline" : ""}>{status}</span></header>
        <div className="merchant-resource-gpu"><strong>{row.gpu_model}</strong><span>{row.gpu_memory_gb}GB</span></div>
        <dl><div><dt><MapPin size={13}/>{t("market.region", "区域")}</dt><dd>{localizeMarketRegion(row.region, locale)}</dd></div><div><dt><HardDrives size={13}/>{t("market.stock", "可用库存")}</dt><dd>{row.available_quantity} {t("market.units", "台")}</dd></div><div><dt><TerminalWindow size={13}/>{t("market.fulfillment", "履约方式")}</dt><dd>{fulfillmentLabel}</dd></div></dl>
        <div className="merchant-resource-assurance"><ShieldCheck size={16}/><span><strong>{row.assurance_label || (kaiSelfOperated ? t("market.kai.title", "算力星图自营") : t("market.merchant.listing", "商家资源"))}</strong><small>{resourceClaimLabel} · {directTradeEnabled ? row.assurance_description : kaiSelfOperated ? t("market.kai.assurance", "提交需求后由平台人工联系确认方案。") : t("market.merchant.assurance", "提交需求后由对应商家人工联系确认方案。")}</small></span></div>
        <footer><div><small>{directTradeEnabled ? t("market.hourly", "每小时价格") : t("market.servicePrice", "服务价格")}</small><strong>{directTradeEnabled ? `${row.unit_price_ch.toLocaleString(locale === "en" ? "en-US" : "zh-CN", { maximumFractionDigits: 6 })} ${locale === "en" ? "CH / GPU·hour" : "卡时 / GPU·小时"}` : inquiryAvailable ? t("market.inquiry", "询价") : "—"}</strong></div><Link href={`/market/products/${row.id}`}>{directTradeEnabled ? row.purchasable ? t("market.buy", "立即购买") : t("market.details", "查看详情") : inquiryAvailable ? t("market.submitRequest", "提交需求") : t("market.details", "查看详情")} <ArrowRight size={15}/></Link></footer>
      </article>;
    })}</div>}
    {displayRows.length > 0 && typeof limit !== "number" && <div className="merchant-market__pagination" aria-live="polite">
      <span>{t("market.pagination.summary", "已显示 {shown} / {total} 项", { shown: rows.length, total: catalog.total })}</span>
      {hasMore && <button type="button" disabled={loading} onClick={() => void loadSourcePage(activeSource, catalog.page + 1, true)}>{loading ? t("market.pagination.loading", "正在加载…") : t("market.pagination.more", "加载更多")}</button>}
    </div>}
    {error && displayRows.length > 0 && <div className="merchant-market__pagination-error">{error}</div>}
  </section>;
}
