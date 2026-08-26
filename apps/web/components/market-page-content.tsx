"use client";

import { MerchantResourceMarket } from "@/components/merchant-resource-market";
import { MarketPulseRail } from "@/components/market-pulse-rail";
import { SiteHeader } from "@/components/site-header";
import { useI18n } from "@/components/locale-root";
import type { PublicProduct } from "@/lib/commerce-api";
import type { PublicMarketRanking } from "@/lib/public-data";

export function MarketPageContent({ initialRanking, initialProducts }: { initialRanking: PublicMarketRanking | null; initialProducts: PublicProduct[] | null }) {
  const { t } = useI18n();
  return <div className="site-page public-v2 market-public-page"><SiteHeader/><main className="public-data-page market-page"><header><p className="hero-eyebrow">KAI & MERCHANT LISTINGS</p><h1>{t("market.title", "算力市场")}</h1><p>{t("market.description", "KAI 自营与商家资源分区展示；商品参数、库存、卖方和履约方式均在下单前明确说明。")}</p></header><div className="market-page__pulse"><MarketPulseRail initialData={initialRanking}/></div><MerchantResourceMarket initialRows={initialProducts}/></main></div>;
}
