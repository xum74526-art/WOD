"use client";

import { ArrowRight, ChartLineUp, Warning } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/locale-root";
import { publicApiEnvelopeRequest } from "@/lib/api";
import type { PublicMarketRanking } from "@/lib/public-data";

type PulseMarket = {
  gpu_model: string;
  gpu_variant: string;
  median_price_card_hours: number;
  change_24h: number;
  source_count: number;
};

type PulseResponse = {
  data: PulseMarket[];
  meta?: { observed_at?: string };
};

export function MarketPulseRail({ initialData = null }: { initialData?: PublicMarketRanking | null }) {
  const { t, dateLocale, formatLedgerMoney } = useI18n();
  const initialMarkets = (initialData?.data ?? []).filter((item) => item.median_price_card_hours > 0).slice(0, 4);
  const [markets, setMarkets] = useState<PulseMarket[]>(initialMarkets);
  const [updatedAt, setUpdatedAt] = useState(initialData?.meta.observed_at ?? "");
  const [status, setStatus] = useState<"loading" | "ready" | "error">(initialMarkets.length ? "ready" : "loading");

  useEffect(() => {
    if (initialMarkets.length) return;
    let active = true;
    publicApiEnvelopeRequest<PulseResponse["data"], NonNullable<PulseResponse["meta"]>>("/api/v1/public/market/ranking", 300_000)
      .then((payload) => {
        if (!active) return;
        const available = (payload.data ?? []).filter((item) => item.median_price_card_hours > 0).slice(0, 4);
        setMarkets(available);
        setUpdatedAt(payload.meta?.observed_at ?? "");
        setStatus(available.length ? "ready" : "error");
      })
      .catch(() => { if (active) setStatus("error"); });
    return () => { active = false; };
  }, [initialMarkets.length]);

  return <section className={`market-pulse-rail market-pulse-rail--${status}`} aria-label={t("home.pulse.aria", "GPU 市场快照")} aria-live="polite">
    <header>
      <ChartLineUp size={18}/>
      <span><small>MARKET PULSE</small><strong>{t("home.pulse.title", "GPU 租赁指数")}</strong></span>
    </header>
    {status === "loading" && <div className="market-pulse-loading">
      {[0, 1, 2, 3].map((item) => <i key={item}/>) }
    </div>}
    {status === "error" && <div className="market-pulse-error"><Warning size={16}/><span>{t("home.pulse.error", "实时行情暂不可用")}</span></div>}
    {status === "ready" && <div className="market-pulse-quotes">
      {markets.map((market) => {
        const direction = market.change_24h >= 0 ? "up" : "down";
        const modelName = `${market.gpu_model} ${market.gpu_variant}`.trim();
        return <article key={`${market.gpu_model}:${market.gpu_variant}`}>
          <span><strong>{modelName}</strong><small>{t(market.source_count === 1 ? "home.pulse.source" : "home.pulse.sources", "{count} 个数据源", { count: market.source_count.toLocaleString(dateLocale) })}</small></span>
          <span className="market-pulse-value"><strong>{formatLedgerMoney(market.median_price_card_hours)}</strong><small>{t("home.pulse.unit", "/ GPU·小时")}</small></span>
          <b className={`is-${direction}`}>{direction === "up" ? "▲" : "▼"} {Math.abs(market.change_24h).toLocaleString(dateLocale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}% / 24H</b>
        </article>;
      })}
    </div>}
    <footer>
      <span>{updatedAt ? t("home.pulse.updated", "更新于 {date}", { date: new Date(updatedAt).toLocaleDateString(dateLocale) }) : t("home.pulse.publicData", "公开市场数据")}</span>
      <Link href="/trend">{t("home.pulse.open", "查看行情")}<ArrowRight size={13}/></Link>
    </footer>
  </section>;
}
