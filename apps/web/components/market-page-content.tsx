"use client";

import { MerchantResourceMarket } from "@/components/merchant-resource-market";
import { MarketPulseRail } from "@/components/market-pulse-rail";
import { SiteHeader } from "@/components/site-header";
import { useI18n } from "@/components/locale-root";
import type { PublicProduct } from "@/lib/commerce-api";
import type { PublicMarketRanking } from "@/lib/public-data";

export function MarketPageContent({ initialRanking, initialProducts }: { initialRanking: PublicMarketRanking | null; initialProducts: PublicProduct[] | null }) {
  const { t } = useI18n();
  return <div className="site-page public-v2 market-public-page"><SiteHeader/><main className="public-data-page market-page"><header><p className="hero-eyebrow">算力星图 & MERCHANT LISTINGS</p><h1>{t("market.title", "算力市场")}</h1><p>{t("market.description", "算力星图自营与商家资源分区展示；可查看参数、库存、卖方与履约方式，并提交需求等待人工确认方案。")}</p></header><div className="market-page__pulse"><MarketPulseRail initialData={initialRanking}/></div><MerchantResourceMarket initialRows={initialProducts}/></main></div>;
}
