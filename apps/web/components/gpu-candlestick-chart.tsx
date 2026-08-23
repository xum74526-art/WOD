"use client";

import Link from "next/link";
import { ArrowRight, ChartLine, Database } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { publicApiEnvelopeRequest } from "@/lib/api";
import { useI18n } from "@/components/locale-root";
import { getMobileMarketCandles, type MobileMarketModel } from "@/lib/mobile-market-api";
import type { InitialGpuTrend } from "@/lib/public-data";

type PricePoint = {
  date: string;
  median: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
};
type MarketSummary = {
  gpu_model: string;
  gpu_slug: string;
  provider_count: number;
  history: PricePoint[];
};
type MarketResponse = {
  data: Array<{
    gpu_model: string;
    gpu_variant: string;
    median_price_card_hours: number;
    source_count: number;
    available_gpu_count: number;
    sources: string[];
    history_day_count: number;
    history_point_count: number;
    market_status: string;
  }>;
  meta: { observed_at?: string };
};
type RangeDays = 28 | 56 | 90;

const ranges: { value: RangeDays; label: string }[] = [
  { value: 28, label: "4W" },
  { value: 56, label: "8W" },
  { value: 90, label: "3M" },
];
const chart = { width: 720, left: 34, right: 650, top: 24, bottom: 254 };

function formatPrice(value: number) {
  return value.toFixed(2);
}

function formatDate(value: string, locale: "zh-CN" | "en") {
  const timestamp = value.includes("T") ? value : `${value}T00:00:00Z`;
  return new Date(timestamp).toLocaleDateString(locale === "en" ? "en-US" : "zh-CN", {
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  });
}

export function GpuDailyTrendChart({ initialData = null }: { initialData?: InitialGpuTrend | null }) {
  const { locale } = useI18n();
  const [market, setMarket] = useState<MarketSummary | null>(initialData?.market ?? null);
  const [updatedAt, setUpdatedAt] = useState(initialData?.updated_at ?? "");
  const [days, setDays] = useState<RangeDays>(90);
  const [activeDate, setActiveDate] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">(initialData ? "ready" : "loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (initialData) return;
    let active = true;
    async function loadMarket() {
      try {
        const payload = await publicApiEnvelopeRequest<MarketResponse["data"], MarketResponse["meta"]>("/api/v1/public/market/ranking", 30_000);
        if (!active) return;
        const ranked = (payload.data ?? []).filter((item) => item.median_price_card_hours > 0);
        const withHistory = ranked.filter((item) => item.history_point_count >= 2 || item.history_day_count >= 2);
        const selected = withHistory.find((item) => item.gpu_model.toUpperCase().includes("H100")) ?? withHistory[0] ?? ranked[0];
        if (!selected) throw new Error(locale === "en" ? "No GPU market quote is available" : "暂无可用的 GPU 行情");
        const model: MobileMarketModel = {
          gpu_model: selected.gpu_model,
          gpu_variant: selected.gpu_variant,
          sources: selected.sources,
          sample_count: selected.source_count,
          available_gpu_count: selected.available_gpu_count,
          market_status: selected.market_status,
        };
        const candlePayload = await getMobileMarketCandles(model, "90d");
        if (!active) return;
        const history = (candlePayload.candles ?? []).map((point) => ({
          date: point.start_time,
          median: point.close_price_card_hours,
          open: point.open_price_card_hours,
          high: point.high_price_card_hours,
          low: point.low_price_card_hours,
          close: point.close_price_card_hours,
        }));
        if (history.length < 2) throw new Error(locale === "en" ? "GPU price history is still accumulating" : "GPU 历史价格仍在积累");
        setMarket({
          gpu_model: `${selected.gpu_model} ${selected.gpu_variant}`.trim(),
          gpu_slug: `${selected.gpu_model}-${selected.gpu_variant}`.toLowerCase(),
          provider_count: selected.source_count,
          history,
        });
        setUpdatedAt(candlePayload.server_time ?? payload.meta?.observed_at ?? "");
        setStatus("ready");
      } catch (error) {
        if (!active) return;
        setMessage(error instanceof Error ? error.message : locale === "en" ? "Failed to load market data" : "行情读取失败");
        setStatus("error");
      }
    }
    void loadMarket();
    return () => { active = false; };
  }, [initialData, locale]);

  const plot = useMemo(() => {
    const history = (market?.history ?? [])
      .filter((point) => point.date && point.median > 0)
      .sort((a, b) => a.date.localeCompare(b.date));
    const latestTimestamp = Date.parse(history.at(-1)?.date ?? "");
    const cutoff = latestTimestamp - (days - 1) * 86_400_000;
    const points = history.filter((point) => Date.parse(point.date) >= cutoff);
    if (points.length < 2) return null;
    const candles = points.map((point, index) => {
      const close = point.close && point.close > 0 ? point.close : point.median;
      const previousClose = index === 0 ? close : (points[index - 1].close || points[index - 1].median);
      const open = point.open && point.open > 0 ? point.open : previousClose;
      return {
        date: point.date,
        open,
        high: Math.max(point.high || open, open, close),
        low: Math.min(point.low || close, open, close),
        close,
      };
    });
    const rawMin = Math.min(...candles.map((candle) => candle.low));
    const rawMax = Math.max(...candles.map((candle) => candle.high));
    const rawRange = rawMax - rawMin;
    const padding = Math.max(rawRange * .08, rawMax * .001, .01);
    const min = Math.max(0, rawMin - padding);
    const max = rawMax + padding;
    const plotWidth = chart.right - chart.left;
    const xFor = (index: number) => chart.left + ((index + .5) / candles.length) * plotWidth;
    const yFor = (price: number) => chart.top + ((max - price) / (max - min || 1)) * (chart.bottom - chart.top);
    const candleWidth = Math.min(13, Math.max(3.2, (plotWidth / candles.length) * .62));
    const coordinates = candles.map((candle, index) => {
      const averageWindow = candles.slice(Math.max(0, index - 3), index + 1);
      const ma4 = averageWindow.reduce((total, item) => total + item.close, 0) / averageWindow.length;
      return {
        ...candle,
        x: xFor(index),
        openY: yFor(candle.open),
        highY: yFor(candle.high),
        lowY: yFor(candle.low),
        closeY: yFor(candle.close),
        ma4,
        maY: yFor(ma4),
      };
    });
    const maLine = coordinates.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(2)} ${point.maY.toFixed(2)}`).join(" ");
    const first = candles[0];
    const latest = candles.at(-1)!;
    const delta = latest.close - first.open;
    return {
      candles, coordinates, candleWidth, maLine, min, max, rawMin, rawMax, first, latest, delta,
      percent: first.open ? (delta / first.open) * 100 : 0,
    };
  }, [market, days]);

  if (status !== "ready" || !market || !plot) {
    return <section className="gpu-kline-card gpu-trend-state" aria-live="polite">
      {status === "loading" ? <Database size={30} weight="light" /> : <ChartLine size={30} weight="light" />}
      <strong>{status === "loading" ? (locale === "en" ? "Building the price chart" : "正在生成价格 K 线") : (locale === "en" ? "Live market data is unavailable" : "真实行情暂不可用")}</strong>
      <span>{status === "loading" ? (locale === "en" ? "Loading KAI Pricing GPU data." : "正在读取 KAI Pricing GPU 行情。") : message}</span>
      {status === "error" && <Link href="/trend">{locale === "en" ? "Open full market" : "打开完整行情"} <ArrowRight size={13} /></Link>}
    </section>;
  }

  const isUp = plot.delta >= 0;
  const active = plot.coordinates.find((item) => item.date === activeDate) ?? plot.coordinates.at(-1)!;
  const labelIndexes = [...new Set([0, Math.floor((plot.candles.length - 1) / 2), plot.candles.length - 1])];

  return (
    <section className="gpu-kline-card gpu-daily-trend" aria-labelledby="gpu-trend-title">
      <header className="gpu-kline-card__head">
        <div>
          <span className="gpu-kline-eyebrow"><i /> GPU RENTAL CANDLE INDEX</span>
          <h2 id="gpu-trend-title">{market.gpu_model} {locale === "en" ? "daily price candles" : "日价格 K 线"}</h2>
          <p>{locale === "en" ? "KAI market median" : "KAI 行情中位价"} · {locale === "en" ? "CH / GPU·h" : "卡时 / GPU·小时"}</p>
        </div>
        <span className="gpu-kline-simulated gpu-trend-source">KAI Pricing</span>
      </header>

      <div className="gpu-kline-quote">
        <div><strong>{formatPrice(active.close)}</strong><span>{locale === "en" ? "CH / GPU·h" : "卡时 / GPU·小时"}</span></div>
        <b className={isUp ? "is-up" : "is-down"}>
          {plot.delta >= 0 ? "+" : ""}{plot.delta.toFixed(2)} · {plot.percent >= 0 ? "+" : ""}{plot.percent.toFixed(2)}%
        </b>
        <nav aria-label={locale === "en" ? "Chart range" : "K 线周期"}>
          {ranges.map((range) => <button
            className={days === range.value ? "active" : ""}
            onClick={() => { setDays(range.value); setActiveDate(""); }}
            type="button"
            key={range.value}
          >{range.label}</button>)}
        </nav>
      </div>

      <div className="gpu-kline-legend">
        <span className="candle">{locale === "en" ? "Daily candles" : "日 K 线"}</span>
        <span className="average">MA4 {formatPrice(active.ma4)}</span>
        <span className="volume">{market.provider_count} {locale === "en" ? (market.provider_count === 1 ? "provider" : "providers") : "家供应商"}</span>
        <span className="gpu-kline-ohlc">{formatDate(active.date, locale)} · O {formatPrice(active.open)} H {formatPrice(active.high)} L {formatPrice(active.low)} C {formatPrice(active.close)}</span>
      </div>

      <div className="gpu-kline-plot gpu-candlestick-plot" onMouseLeave={() => setActiveDate("")}>
        <svg viewBox={`0 0 ${chart.width} 300`} role="img" aria-label={locale === "en" ? `${market.gpu_model} daily price candles for the selected period` : `${market.gpu_model} 所选周期日价格 K 线`}>
          {[0, 1, 2, 3, 4].map((line) => {
            const price = plot.max - ((plot.max - plot.min) / 4) * line;
            const y = chart.top + ((chart.bottom - chart.top) / 4) * line;
            return <g className="gpu-kline-grid" key={line}>
              <line x1={chart.left} y1={y} x2={chart.right} y2={y} />
              <text x={chart.right + 14} y={y + 4}>{formatPrice(price)}</text>
            </g>;
          })}
          <path className="gpu-kline-ma" d={plot.maLine} />
          {plot.coordinates.map((point) => {
            const bodyTop = Math.min(point.openY, point.closeY);
            const bodyHeight = Math.max(2.4, Math.abs(point.closeY - point.openY));
            return <g
              className={`gpu-candle ${point.close >= point.open ? "is-up" : "is-down"}`}
              key={point.date}
              onMouseEnter={() => setActiveDate(point.date)}
              onClick={() => setActiveDate(point.date)}
            >
              <title>{`${point.date} · O ${formatPrice(point.open)} H ${formatPrice(point.high)} L ${formatPrice(point.low)} C ${formatPrice(point.close)}`}</title>
              <line className="gpu-candle__wick" x1={point.x} y1={point.highY} x2={point.x} y2={point.lowY} />
              <rect className="gpu-candle__body" x={point.x - plot.candleWidth / 2} y={bodyHeight === 2.4 ? bodyTop - 1.2 : bodyTop} width={plot.candleWidth} height={bodyHeight} rx=".5" />
            </g>;
          })}
          {activeDate && <line className="gpu-kline-crosshair" x1={active.x} y1={chart.top} x2={active.x} y2={chart.bottom} />}
          {labelIndexes.map((index) => <text
            className="gpu-kline-time"
            x={plot.coordinates[index].x}
            y="286"
            textAnchor={index === 0 ? "start" : index === plot.candles.length - 1 ? "end" : "middle"}
            key={plot.candles[index].date}
          >{formatDate(plot.candles[index].date, locale)}</text>)}
        </svg>
      </div>

      <dl className="gpu-kline-stats">
        <div><dt>{locale === "en" ? "Range open" : "区间开盘"}</dt><dd>{formatPrice(plot.first.open)}</dd></div>
        <div><dt>{locale === "en" ? "Range high" : "区间最高"}</dt><dd>{formatPrice(plot.rawMax)}</dd></div>
        <div><dt>{locale === "en" ? "Range low" : "区间最低"}</dt><dd>{formatPrice(plot.rawMin)}</dd></div>
        <div><dt>{locale === "en" ? "Latest close" : "最新收盘"}</dt><dd>{formatPrice(plot.latest.close)}</dd></div>
      </dl>

      <footer>
        <span>{locale === "en" ? "Candles use KAI Pricing market history" : "K 线基于 KAI Pricing 行情历史"} · {locale === "en" ? "Updated" : "更新于"} {updatedAt ? new Date(updatedAt).toLocaleDateString(locale === "en" ? "en-US" : "zh-CN") : "—"}</span>
        <Link href="/trend">{locale === "en" ? "Open full market" : "查看完整行情"} <ArrowRight size={13} /></Link>
      </footer>
    </section>
  );
}

export const GpuCandlestickChart = GpuDailyTrendChart;
