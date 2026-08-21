"use client";

import { ArrowRight, ChartLineUp, Warning } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/locale-root";
import { apiBaseUrl, readApiError } from "@/lib/api";

type PulseMarket = {
  gpu_model: string;
  gpu_variant: string;
  median_price_cny: number;
  change_24h: number;
  source_count: number;
};

type PulseResponse = {
  data?: PulseMarket[];
  meta?: { observed_at?: string };
};

export function MarketPulseRail() {
  const { locale } = useI18n();
  const [markets, setMarkets] = useState<PulseMarket[]>([]);
  const [updatedAt, setUpdatedAt] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/api/v1/public/market/ranking`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await readApiError(response));
        return response.json() as Promise<PulseResponse>;
      })
      .then((payload) => {
        const available = (payload.data ?? []).filter((item) => item.median_price_cny > 0).slice(0, 4);
        setMarkets(available);
        setUpdatedAt(payload.meta?.observed_at ?? "");
        setStatus(available.length ? "ready" : "error");
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setStatus("error");
      });
    return () => controller.abort();
  }, []);

  return <section className={`market-pulse-rail market-pulse-rail--${status}`} aria-label={locale === "en" ? "GPU market pulse" : "GPU 市场快照"} aria-live="polite">
    <header>
      <ChartLineUp size={18}/>
      <span><small>MARKET PULSE</small><strong>{locale === "en" ? "GPU rental index" : "GPU 租赁指数"}</strong></span>
    </header>
    {status === "loading" && <div className="market-pulse-loading">
      {[0, 1, 2, 3].map((item) => <i key={item}/>) }
    </div>}
    {status === "error" && <div className="market-pulse-error"><Warning size={16}/><span>{locale === "en" ? "Live quotes are temporarily unavailable" : "实时行情暂不可用"}</span></div>}
    {status === "ready" && <div className="market-pulse-quotes">
      {markets.map((market) => {
        const direction = market.change_24h >= 0 ? "up" : "down";
        const modelName = `${market.gpu_model} ${market.gpu_variant}`.trim();
        return <article key={`${market.gpu_model}:${market.gpu_variant}`}>
          <span><strong>{modelName}</strong><small>{market.source_count} {locale === "en" ? (market.source_count === 1 ? "source" : "sources") : "个数据源"}</small></span>
          <span className="market-pulse-value"><strong>{market.median_price_cny.toFixed(2)}</strong><small>CNY / GPU·h</small></span>
          <b className={`is-${direction}`}>{direction === "up" ? "▲" : "▼"} {Math.abs(market.change_24h).toFixed(2)}% / 24H</b>
        </article>;
      })}
    </div>}
    <footer>
      <span>{updatedAt ? `${locale === "en" ? "Updated" : "更新于"} ${new Date(updatedAt).toLocaleDateString(locale === "en" ? "en-US" : "zh-CN")}` : locale === "en" ? "Public market data" : "公开市场数据"}</span>
      <Link href="/market/trends">{locale === "en" ? "Open market" : "查看行情"}<ArrowRight size={13}/></Link>
    </footer>
  </section>;
}
