"use client";

import Link from "next/link";
import { ArrowRight, ChartLine, Database } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { apiBaseUrl, readApiError } from "@/lib/api";

type PricePoint = { date: string; median: number };
type MarketSummary = {
  gpu_model: string;
  gpu_slug: string;
  provider_count: number;
  history: PricePoint[];
};
type MarketResponse = {
  data: MarketSummary[];
  meta: { history_updated_at?: string; observed_at?: string };
};
type RangeWeeks = 4 | 8 | 14;

const ranges: { value: RangeWeeks; label: string }[] = [
  { value: 4, label: "4W" },
  { value: 8, label: "8W" },
  { value: 14, label: "3M" },
];
const chart = { width: 720, left: 34, right: 650, top: 24, bottom: 254 };

function formatPrice(value: number) {
  return value.toFixed(2);
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    timeZone: "UTC",
  });
}

function preferredMarket(items: MarketSummary[]) {
  return items.find((item) => item.gpu_slug === "nvidia-h100")
    ?? items.find((item) => item.gpu_model.toUpperCase().includes("H100"))
    ?? items[0];
}

export function GpuDailyTrendChart() {
  const [market, setMarket] = useState<MarketSummary | null>(null);
  const [updatedAt, setUpdatedAt] = useState("");
  const [weeks, setWeeks] = useState<RangeWeeks>(14);
  const [activeDate, setActiveDate] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    async function loadMarket() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/v1/public/market/summary`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(await readApiError(response));
        const payload = await response.json() as MarketResponse;
        const selected = preferredMarket(
          (payload.data ?? []).filter((item) => item.history?.some((point) => point.median > 0)),
        );
        if (!selected) throw new Error("暂无可用的 GPU 历史价格");
        setMarket(selected);
        setUpdatedAt(payload.meta?.history_updated_at ?? payload.meta?.observed_at ?? "");
        setStatus("ready");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMessage(error instanceof Error ? error.message : "行情读取失败");
        setStatus("error");
      }
    }
    void loadMarket();
    return () => controller.abort();
  }, []);

  const plot = useMemo(() => {
    const points = (market?.history ?? [])
      .filter((point) => point.date && point.median > 0)
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-weeks);
    if (points.length < 2) return null;
    const candles = points.map((point, index) => {
      const open = index === 0 ? point.median : points[index - 1].median;
      return {
        date: point.date,
        open,
        high: Math.max(open, point.median),
        low: Math.min(open, point.median),
        close: point.median,
      };
    });
    const rawMin = Math.min(...candles.map((candle) => candle.low));
    const rawMax = Math.max(...candles.map((candle) => candle.high));
    const padding = Math.max((rawMax - rawMin) * .18, rawMax * .025, .02);
    const min = Math.max(0, rawMin - padding);
    const max = rawMax + padding;
    const plotWidth = chart.right - chart.left;
    const xFor = (index: number) => chart.left + ((index + .5) / candles.length) * plotWidth;
    const yFor = (price: number) => chart.top + ((max - price) / (max - min || 1)) * (chart.bottom - chart.top);
    const candleWidth = Math.min(24, Math.max(10, (plotWidth / candles.length) * .64));
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
  }, [market, weeks]);

  if (status !== "ready" || !market || !plot) {
    return <section className="gpu-kline-card gpu-trend-state" aria-live="polite">
      {status === "loading" ? <Database size={30} weight="light" /> : <ChartLine size={30} weight="light" />}
      <strong>{status === "loading" ? "正在生成价格 K 线" : "真实行情暂不可用"}</strong>
      <span>{status === "loading" ? "正在加载 GetDeploying GPU 公开价格。" : message}</span>
      {status === "error" && <Link href="/market/trends">打开完整行情 <ArrowRight size={13} /></Link>}
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
          <h2 id="gpu-trend-title">{market.gpu_model} 周价格 K 线</h2>
          <p>GetDeploying 公开中位价 · USD / GPU·小时</p>
        </div>
        <span className="gpu-kline-simulated gpu-trend-source">公开数据</span>
      </header>

      <div className="gpu-kline-quote">
        <div><strong>{formatPrice(active.close)}</strong><span>USD / GPU·h</span></div>
        <b className={isUp ? "is-up" : "is-down"}>
          {plot.delta >= 0 ? "+" : ""}{plot.delta.toFixed(2)} · {plot.percent >= 0 ? "+" : ""}{plot.percent.toFixed(2)}%
        </b>
        <nav aria-label="K 线周期">
          {ranges.map((range) => <button
            className={weeks === range.value ? "active" : ""}
            onClick={() => { setWeeks(range.value); setActiveDate(""); }}
            type="button"
            key={range.value}
          >{range.label}</button>)}
        </nav>
      </div>

      <div className="gpu-kline-legend">
        <span className="candle">周 K 线</span>
        <span className="average">MA4 {formatPrice(active.ma4)}</span>
        <span className="volume">{market.provider_count} 家供应商</span>
        <span className="gpu-kline-ohlc">{formatDate(active.date)} · O {formatPrice(active.open)} H {formatPrice(active.high)} L {formatPrice(active.low)} C {formatPrice(active.close)}</span>
      </div>

      <div className="gpu-kline-plot gpu-candlestick-plot" onMouseLeave={() => setActiveDate("")}>
        <svg viewBox={`0 0 ${chart.width} 300`} role="img" aria-label={`${market.gpu_model} 最近三个月周价格变化 K 线`}>
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
            const bodyHeight = Math.max(3.2, Math.abs(point.closeY - point.openY));
            return <g
              className={`gpu-candle ${point.close >= point.open ? "is-up" : "is-down"}`}
              key={point.date}
              onMouseEnter={() => setActiveDate(point.date)}
              onClick={() => setActiveDate(point.date)}
            >
              <title>{point.date} · O {formatPrice(point.open)} H {formatPrice(point.high)} L {formatPrice(point.low)} C {formatPrice(point.close)}</title>
              <line className="gpu-candle__wick" x1={point.x} y1={point.highY} x2={point.x} y2={point.lowY} />
              <rect className="gpu-candle__body" x={point.x - plot.candleWidth / 2} y={bodyHeight === 3.2 ? bodyTop - 1.6 : bodyTop} width={plot.candleWidth} height={bodyHeight} rx="1" />
            </g>;
          })}
          {activeDate && <line className="gpu-kline-crosshair" x1={active.x} y1={chart.top} x2={active.x} y2={chart.bottom} />}
          {labelIndexes.map((index) => <text
            className="gpu-kline-time"
            x={plot.coordinates[index].x}
            y="286"
            textAnchor={index === 0 ? "start" : index === plot.candles.length - 1 ? "end" : "middle"}
            key={plot.candles[index].date}
          >{formatDate(plot.candles[index].date)}</text>)}
        </svg>
      </div>

      <dl className="gpu-kline-stats">
        <div><dt>区间开盘</dt><dd>{formatPrice(plot.first.open)}</dd></div>
        <div><dt>区间最高</dt><dd>{formatPrice(plot.rawMax)}</dd></div>
        <div><dt>区间最低</dt><dd>{formatPrice(plot.rawMin)}</dd></div>
        <div><dt>最新收盘</dt><dd>{formatPrice(plot.latest.close)}</dd></div>
      </dl>

      <footer>
        <span>相邻周中位价生成趋势 K 线，并非日内成交 OHLC · 更新于 {updatedAt ? new Date(updatedAt).toLocaleDateString("zh-CN") : "—"}</span>
        <Link href="/market/trends">查看完整行情 <ArrowRight size={13} /></Link>
      </footer>
    </section>
  );
}

export const GpuCandlestickChart = GpuDailyTrendChart;
