"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type PointerEvent as ReactPointerEvent } from "react";
import { ArrowClockwise, ArrowDown, ArrowUp, CaretDown, CaretUp, ChartLine, Database, MagnifyingGlass } from "@phosphor-icons/react";
import { publicApiEnvelopeRequest } from "@/lib/api";
import { getMobileLatestMarket, getMobileMarketCandles, getMobileMarketModels, getMobileMarketSources, type MobileLatestMarket, type MobileMarketCandle, type MobileMarketModel, type MobileMarketSource } from "@/lib/mobile-market-api";

type PricePoint = { date: string; median: number };
type MarketSummary = {
  gpu_model: string;
  tier?: string;
  vram_gb?: number;
  min_price: number;
  median_price: number;
  official_min_price?: number;
  official_median_price?: number;
  history: PricePoint[];
};
type MarketMeta = { observed_at: string; history_updated_at?: string };
type MarketResponse = { data: MarketSummary[]; meta: MarketMeta };
type RangeWeeks = 2 | 4 | 8 | 14;
type SortKey = "price" | "day" | "week" | "updated";
type Direction = "all" | "up" | "down";

const ranges: { value: RangeWeeks; label: string }[] = [
  { value: 4, label: "4周" },
  { value: 8, label: "8周" },
  { value: 14, label: "3个月" },
];
const PAGE_SIZE = 15;

function validHistory(item: MarketSummary) {
  return item.history.filter((point) => point.median > 0);
}

function rangePoints(item: MarketSummary, weeks: RangeWeeks) {
  return validHistory(item).slice(0, weeks).reverse();
}

function priceStats(item: MarketSummary, weeks: RangeWeeks) {
  const points = rangePoints(item, weeks);
  const enough = points.length >= 2;
  if (!enough) return { points, enough: false, current: points.at(-1)?.median ?? 0, high: 0, low: 0, median: 0, delta: 0, percent: 0 };
  const values = points.map((point) => point.median);
  const current = values.at(-1) ?? 0;
  const start = values[0];
  const delta = current - start;
  return {
    points,
    enough: true,
    current,
    high: Math.max(...values),
    low: Math.min(...values),
    median: [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)],
    delta,
    percent: start ? (delta / start) * 100 : 0,
  };
}

function formatPrice(value: number) {
  return `${value.toFixed(3)} 卡时`;
}

function formatChange(value: number, suffix = "") {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}${suffix}`;
}

function linearPath(points: { x: number; y: number }[]) {
  return points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
}

function MiniTrend({ item, days, tone }: { item: MarketSummary; days: RangeWeeks; tone: "up" | "down" }) {
  const stats = priceStats(item, days);
  if (!stats.enough) return <span className="trend-mini-empty">数据不足</span>;
  const values = stats.points.map((point) => point.median);
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const points = values.map((value, index) => ({ x: (index / Math.max(1, values.length - 1)) * 100, y: 28 - ((value - min) / range) * 23 }));
  return <svg className={`trend-mini-line is-${tone}`} viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><path d={linearPath(points)} fill="none" stroke={tone === "up" ? "#168866" : "#d84c55"} strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /></svg>;
}

function MainPriceChart({ item, days, realCandles = [] }: { item: MarketSummary; days: RangeWeeks; realCandles?: MobileMarketCandle[] }) {
  const stats = useMemo(() => priceStats(item, days), [item, days]);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  useEffect(() => setActiveIndex(null), [item.gpu_model, days]);

  if (!stats.enough) {
    return <div className="trend-chart-state"><ChartLine size={34} weight="light" /><strong>历史数据不足</strong><p>当前只有 {validHistory(item).length} 个公开周价格点。</p></div>;
  }

  const fallbackCandles = stats.points.map((point, index) => {
    const open = index === 0 ? point.median : stats.points[index - 1].median;
    return {
      ...point,
      open,
      high: Math.max(open, point.median),
      low: Math.min(open, point.median),
      close: point.median,
    };
  });
  const candles = realCandles.length > 1 ? realCandles.map((point) => ({
    date: point.start_time.slice(0, 10),
    median: point.close_price_cny,
    open: point.open_price_cny,
    high: point.high_price_cny,
    low: point.low_price_cny,
    close: point.close_price_cny,
  })) : fallbackCandles;
  const rawMin = Math.min(...candles.map((candle) => candle.low));
  const rawMax = Math.max(...candles.map((candle) => candle.high));
  const padding = Math.max((rawMax - rawMin) * .16, rawMax * .025, .02);
  const chartMin = Math.max(0, rawMin - padding);
  const chartMax = rawMax + padding;
  const plot = { left: 54, right: 946, top: 52, bottom: 292 };
  const scaleY = (value: number) => plot.top + ((chartMax - value) / (chartMax - chartMin || 1)) * (plot.bottom - plot.top);
  const candleWidth = Math.min(34, Math.max(13, ((plot.right - plot.left) / candles.length) * .56));
  const chartCandles = candles.map((candle, index) => {
    const averageWindow = candles.slice(Math.max(0, index - 3), index + 1);
    const ma4 = averageWindow.reduce((total, entry) => total + entry.close, 0) / averageWindow.length;
    return {
      ...candle,
      x: plot.left + ((index + .5) / candles.length) * (plot.right - plot.left),
      openY: scaleY(candle.open),
      highY: scaleY(candle.high),
      lowY: scaleY(candle.low),
      closeY: scaleY(candle.close),
      ma4,
      maY: scaleY(ma4),
    };
  });
  const maLine = linearPath(chartCandles.map((candle) => ({ x: candle.x, y: candle.maY })));
  const highPoint = chartCandles.reduce((best, point) => point.high > best.high ? point : best);
  const lowPoint = chartCandles.reduce((best, point) => point.low < best.low ? point : best);
  const active = activeIndex === null ? chartCandles.at(-1)! : chartCandles[activeIndex];

  const selectPoint = (event: ReactPointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const pointerRatio = (event.clientX - rect.left) / rect.width;
    const chartRatio = Math.max(0, Math.min(1, (pointerRatio - .054) / .892));
    setActiveIndex(Math.round(chartRatio * (chartCandles.length - 1)));
  };

  const trendTone = stats.delta > 0 ? "is-up" : stats.delta < 0 ? "is-down" : "is-flat";

  return <div className={`trend-main-chart ${trendTone}`} onPointerMove={selectPoint} onPointerLeave={() => setActiveIndex(null)} onPointerDown={selectPoint}>
    <svg viewBox="0 0 1000 330" preserveAspectRatio="none" role="img" aria-label={`${item.gpu_model} 周价格 K 线`}>
      {[0, 1, 2, 3, 4].map((line) => {
        const y = plot.top + ((plot.bottom - plot.top) / 4) * line;
        return <line className="trend-grid-line" x1={plot.left} x2={plot.right} y1={y} y2={y} key={line} />;
      })}
      <line className="trend-median-line" x1={plot.left} x2={plot.right} y1={scaleY(stats.median)} y2={scaleY(stats.median)} />
      <path className="trend-kline-ma" d={maLine} key={`ma-${item.gpu_model}-${days}`} />
      {chartCandles.map((candle) => {
        const bodyTop = Math.min(candle.openY, candle.closeY);
        const bodyHeight = Math.max(3.5, Math.abs(candle.closeY - candle.openY));
        return <g className={`trend-candle ${candle.close >= candle.open ? "is-up" : "is-down"}`} key={candle.date}>
          <title>{candle.date} · O {candle.open.toFixed(3)} H {candle.high.toFixed(3)} L {candle.low.toFixed(3)} C {candle.close.toFixed(3)}</title>
          <line className="trend-candle__wick" x1={candle.x} x2={candle.x} y1={candle.highY} y2={candle.lowY} />
          <rect className="trend-candle__body" x={candle.x - candleWidth / 2} y={bodyHeight === 3.5 ? bodyTop - 1.75 : bodyTop} width={candleWidth} height={bodyHeight} />
        </g>;
      })}
      {activeIndex !== null && <line className="trend-cursor-line" x1={active.x} x2={active.x} y1={plot.top} y2={plot.bottom} />}
    </svg>
    <div className="trend-chart-legend">
      <span><i className="is-candle-up" />上涨</span>
      <span><i className="is-candle-down" />下跌</span>
      <span><i className="is-average" />MA4 {active.ma4.toFixed(3)}</span>
      <span className="trend-chart-ohlc">{new Date(`${active.date}T00:00:00Z`).toLocaleDateString("zh-CN", { timeZone: "UTC" })} · O {active.open.toFixed(3)} H {active.high.toFixed(3)} L {active.low.toFixed(3)} C {active.close.toFixed(3)}</span>
    </div>
    <span className="trend-high-label" style={{ left: `${highPoint.x / 10}%`, top: `${highPoint.highY / 3.3}%` }}>最高 {formatPrice(highPoint.high)}</span>
    <span className="trend-low-label" style={{ left: `${lowPoint.x / 10}%`, top: `${lowPoint.lowY / 3.3}%` }}>最低 {formatPrice(lowPoint.low)}</span>
    <span className="trend-median-label" style={{ top: `${scaleY(stats.median) / 3.3}%` }}>中位价 {formatPrice(stats.median)}</span>
    {activeIndex !== null && <div className="trend-chart-tooltip" style={{ left: `${Math.max(10, Math.min(90, active.x / 10))}%`, top: `${Math.max(7, active.highY / 3.3 - 6)}%` }}><strong>{formatPrice(active.close)} / GPU·小时</strong><span>开 {active.open.toFixed(3)} · 高 {active.high.toFixed(3)} · 低 {active.low.toFixed(3)} · 收 {active.close.toFixed(3)}</span><span>{new Date(`${active.date}T00:00:00Z`).toLocaleDateString("zh-CN", { timeZone: "UTC" })}</span></div>}
    <div className="trend-axis-dates"><span>{new Date(`${stats.points[0].date}T00:00:00`).toLocaleDateString("zh-CN")}</span><span>{new Date(`${stats.points.at(-1)!.date}T00:00:00`).toLocaleDateString("zh-CN")}</span></div>
  </div>;
}

export function LiveMarketPanel({ featured = false }: { featured?: boolean }) {
  const [markets, setMarkets] = useState<MarketSummary[]>([]);
  const [meta, setMeta] = useState<MarketMeta | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [gpuPickerQuery, setGpuPickerQuery] = useState("");
  const [days, setDays] = useState<RangeWeeks>(14);
  const [query, setQuery] = useState("");
  const [memory, setMemory] = useState("all");
  const [direction, setDirection] = useState<Direction>("all");
  const [mobileBoard, setMobileBoard] = useState<"gainers" | "losers">("gainers");
  const [sortKey, setSortKey] = useState<SortKey>("price");
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [mobileModels, setMobileModels] = useState<MobileMarketModel[]>([]);
  const [sourceStates, setSourceStates] = useState<MobileMarketSource[]>([]);
  const [latest, setLatest] = useState<MobileLatestMarket | null>(null);
  const [realCandles, setRealCandles] = useState<MobileMarketCandle[]>([]);
  const [liveLoading, setLiveLoading] = useState(false);

  const load = useCallback(async (force = false) => {
    setStatus("loading");
    try {
      const [payload, modelsPayload, sourcesPayload] = await Promise.all([
        publicApiEnvelopeRequest<MarketSummary[], MarketMeta>("/api/v1/public/market/summary", 60_000, force) as Promise<MarketResponse>,
        getMobileMarketModels(),
        getMobileMarketSources(),
      ]);
      const data = (payload.data ?? []).filter((item) => validHistory(item).length > 1);
      setMarkets(data);
      setMeta(payload.meta);
      setMobileModels(modelsPayload.items ?? []);
      setSourceStates(sourcesPayload.items ?? []);
      setSelectedModel((current) => current || data[0]?.gpu_model || "");
      setGpuPickerQuery((current) => current || data[0]?.gpu_model || "");
      setStatus("ready");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "行情读取失败");
      setStatus("error");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const model = mobileModels.find((item) => item.gpu_model.toLowerCase() === selectedModel.toLowerCase());
    if (!model) { setLatest(null); setRealCandles([]); return; }
    let active = true;
    setLiveLoading(true);
    const range = days <= 4 ? "7d" : "30d";
    Promise.all([getMobileLatestMarket(model), getMobileMarketCandles(model, range)])
      .then(([latestPayload, candlePayload]) => {
        if (!active) return;
        setLatest(latestPayload);
        setRealCandles(candlePayload.candles ?? []);
      })
      .catch(() => { if (active) { setLatest(null); setRealCandles([]); } })
      .finally(() => { if (active) setLiveLoading(false); });
    return () => { active = false; };
  }, [mobileModels, selectedModel, days]);

  const memories = useMemo(() => [...new Set(markets.map((item) => item.vram_gb).filter((value): value is number => Boolean(value)))].sort((a, b) => a - b), [markets]);
  const selected = markets.find((item) => item.gpu_model === selectedModel) ?? markets[0];
  const selectedStats = selected ? priceStats(selected, days) : null;
  const dailyMovers = markets.map((item) => priceStats(item, 2)).filter((stats) => stats.enough);
  const risingToday = dailyMovers.filter((stats) => stats.delta > 0).length;
  const fallingToday = dailyMovers.filter((stats) => stats.delta < 0).length;

  const filtered = useMemo(() => markets.filter((item) => {
    if (!item.gpu_model.toLowerCase().includes(query.trim().toLowerCase())) return false;
    if (memory !== "all" && item.vram_gb !== Number(memory)) return false;
    const change = priceStats(item, days);
    if (direction === "up" && (!change.enough || change.delta <= 0)) return false;
    if (direction === "down" && (!change.enough || change.delta >= 0)) return false;
    return true;
  }), [markets, query, memory, direction, days]);

  const ranked = useMemo(() => markets.map((item) => ({ item, stats: priceStats(item, days) })).filter((entry) => entry.stats.enough), [markets, days]);
  const gainers = [...ranked].filter((entry) => entry.stats.delta > 0).sort((a, b) => b.stats.percent - a.stats.percent).slice(0, 5);
  const losers = [...ranked].filter((entry) => entry.stats.delta < 0).sort((a, b) => a.stats.percent - b.stats.percent).slice(0, 5);

  const sorted = useMemo(() => [...filtered].sort((a, b) => {
    const value = (item: MarketSummary) => sortKey === "price" ? priceStats(item, 2).current : sortKey === "day" ? priceStats(item, 2).percent : sortKey === "week" ? priceStats(item, 4).percent : new Date(meta?.history_updated_at ?? meta?.observed_at ?? 0).getTime();
    return (value(a) - value(b)) * (sortAsc ? 1 : -1);
  }), [filtered, sortKey, sortAsc, meta]);
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageItems = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  useEffect(() => setPage(1), [query, memory, direction, days, sortKey, sortAsc]);
  useEffect(() => { if (page > pageCount) setPage(pageCount); }, [page, pageCount]);

  const changeSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((value) => !value);
    else { setSortKey(key); setSortAsc(key === "price"); }
  };
  const chooseGpu = (model: string, scrollToChart = true) => {
    setSelectedModel(model);
    setGpuPickerQuery(model);
    if (scrollToChart) document.getElementById("gpu-main-chart")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const updateGpuPicker = (value: string) => {
    setGpuPickerQuery(value);
    const match = markets.find((item) => item.gpu_model.toLowerCase() === value.trim().toLowerCase());
    if (match) chooseGpu(match.gpu_model, false);
  };

  if (status === "loading") return <section className="trend-state-panel"><Database size={34} weight="light" /><strong>正在加载算力行情</strong><p>正在读取真实历史价格。</p></section>;
  if (status === "error") {
    const needsConfiguration = message.includes("GetDeploying API Key");
    return <section className={`trend-state-panel ${needsConfiguration ? "is-configuration" : "is-error"}`}>
      <Database size={34} weight="light" />
      <strong>{needsConfiguration ? "行情源尚未启用" : "行情服务暂时不可用"}</strong>
      <p>{needsConfiguration ? "服务器还没有配置 GetDeploying 行情凭证。服务器租赁功能不受影响。" : message}</p>
      <div className="trend-state-actions">
        {!needsConfiguration && <button type="button" onClick={() => void load(true)}><ArrowClockwise size={15} />重新读取</button>}
        {needsConfiguration && <a href="https://getdeploying.com/gpus" target="_blank" rel="noreferrer">查看数据来源</a>}
        <Link href="/market">浏览服务器</Link>
      </div>
    </section>;
  }
  if (!markets.length) return <section className="trend-state-panel"><ChartLine size={34} weight="light" /><strong>暂无行情数据</strong><p>当前没有足够的真实历史价格。</p></section>;
  if (featured) return <section className="market-panel trend-home-preview"><div className="market-panel__head"><div><p className="hero-eyebrow">GPU PRICE TRENDS</p><h2>GPU 算力行情</h2><p>观察真实价格变化，再进入市场寻找资源。</p></div><Link href="/market/trends">查看完整行情</Link></div><div>{markets.slice(0, 3).map((item) => { const stats = priceStats(item, 2); return <article key={item.gpu_model}><span><strong>{item.gpu_model}</strong><small>{item.vram_gb ? `${item.vram_gb}GB 显存` : item.tier}</small></span><span><small>当前价格</small><strong>{formatPrice(stats.current)}</strong></span><span className={stats.percent >= 0 ? "is-up" : "is-down"}><small>本周涨跌</small><strong>{stats.enough ? formatChange(stats.percent, "%") : "—"}</strong></span></article>; })}</div></section>;

  return <section className="trend-dashboard">
    <div className="trend-overview">
      <article><span>收录 GPU 型号</span><strong>{markets.length}</strong><small>完整行情目录</small></article>
      <article><span>本周上涨</span><strong className="is-up">{risingToday}</strong><small>较上一周价格点</small></article>
      <article><span>本周下跌</span><strong className="is-down">{fallingToday}</strong><small>较上一周价格点</small></article>
      <article><span>最近更新时间</span><strong className="is-time">{new Date(meta?.history_updated_at ?? meta?.observed_at ?? "").toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</strong><small>{new Date(meta?.history_updated_at ?? meta?.observed_at ?? "").toLocaleDateString("zh-CN")}</small></article>
    </div>
    <div className="trend-source-status" aria-label="行情数据源状态">
      <strong>实时数据源</strong>
      {sourceStates.filter((source) => source.enabled).map((source) => <span className={source.has_error ? "is-error" : "is-ready"} key={source.source}><i />{source.source_name} · {source.status}</span>)}
    </div>

    {selected && selectedStats && <section className="trend-focus" id="gpu-main-chart">
      <header>
        <div className="trend-focus-tools">
          <label className="trend-focus-gpu-picker">
            <span>GPU 型号</span>
            <div><MagnifyingGlass size={18} /><input list="trend-gpu-options" value={gpuPickerQuery} onChange={(event) => updateGpuPicker(event.target.value)} onBlur={() => setGpuPickerQuery(selectedModel)} placeholder="输入 GPU 型号" aria-label="选择要查看的 GPU" />{selected.vram_gb && <em>{selected.vram_gb}GB</em>}</div>
          </label>
          <datalist id="trend-gpu-options">{markets.map((item) => <option value={item.gpu_model} key={item.gpu_model}>{item.vram_gb ? `${item.vram_gb}GB 显存` : item.tier}</option>)}</datalist>
          <div className="trend-focus-period"><span>观察周期</span><div className="trend-ranges" aria-label="时间范围">{ranges.map((range) => <button className={days === range.value ? "is-active" : ""} onClick={() => setDays(range.value)} type="button" key={range.value}>{range.label}</button>)}</div></div>
        </div>
        <div className="trend-focus-quote">
          <div className="trend-current-price"><span>当前实时中位价</span><strong>{latest?.summary.median_price_cny ? formatPrice(latest.summary.median_price_cny) : selectedStats.current ? formatPrice(selectedStats.current) : "数据不足"}</strong><small>{liveLoading ? "正在刷新实时行情" : latest ? `${latest.summary.source_count} 个来源 · ${latest.summary.available_gpu_count} 张可用` : "历史行情兼容模式"}</small></div>
          {selectedStats.enough && <div className={`trend-focus-change ${selectedStats.delta >= 0 ? "is-up" : "is-down"}`}><span>{ranges.find((range) => range.value === days)?.label}涨跌</span><strong>{formatChange(selectedStats.percent, "%")}</strong></div>}
          <Link href={`/market?gpu=${encodeURIComponent(selected.gpu_model)}`}>查看可租资源</Link>
        </div>
      </header>
      <MainPriceChart item={selected} days={days} realCandles={realCandles} />
      <div className="trend-period-stats">
        <span><small>周期最高价</small><strong>{selectedStats.enough ? formatPrice(selectedStats.high) : "—"}</strong></span>
        <span><small>周期最低价</small><strong>{selectedStats.enough ? formatPrice(selectedStats.low) : "—"}</strong></span>
        <span><small>市场中位价</small><strong>{selectedStats.enough ? formatPrice(selectedStats.median) : "—"}</strong></span>
        <span><small>周期涨跌</small><strong className={selectedStats.delta >= 0 ? "is-up" : "is-down"}>{selectedStats.enough ? formatChange(selectedStats.percent, "%") : "—"}</strong></span>
      </div>
    </section>}

    <div className="trend-mobile-board-tabs"><button className={mobileBoard === "gainers" ? "is-active" : ""} onClick={() => setMobileBoard("gainers")} type="button">涨幅榜</button><button className={mobileBoard === "losers" ? "is-active" : ""} onClick={() => setMobileBoard("losers")} type="button">跌幅榜</button></div>
    <div className="trend-leaderboards">
      <section className={mobileBoard === "gainers" ? "is-mobile-active" : ""}><header><div><ArrowUp size={16} /><h2>涨幅榜</h2></div><small>{ranges.find((range) => range.value === days)?.label}</small></header>{gainers.length ? <div>{gainers.map(({ item, stats }, index) => <button type="button" onClick={() => chooseGpu(item.gpu_model)} key={item.gpu_model}><span className="trend-rank">{index + 1}</span><span><strong>{item.gpu_model}</strong><small>{formatPrice(stats.current)}</small></span><MiniTrend item={item} days={days} tone="up" /><span className="trend-move is-up"><strong>{formatChange(stats.percent, "%")}</strong><small>{formatChange(stats.delta)} 卡时</small></span></button>)}</div> : <p className="trend-list-empty">该周期暂无真实上涨数据</p>}</section>
      <section className={mobileBoard === "losers" ? "is-mobile-active" : ""}><header><div><ArrowDown size={16} /><h2>跌幅榜</h2></div><small>{ranges.find((range) => range.value === days)?.label}</small></header>{losers.length ? <div>{losers.map(({ item, stats }, index) => <button type="button" onClick={() => chooseGpu(item.gpu_model)} key={item.gpu_model}><span className="trend-rank">{index + 1}</span><span><strong>{item.gpu_model}</strong><small>{formatPrice(stats.current)}</small></span><MiniTrend item={item} days={days} tone="down" /><span className="trend-move is-down"><strong>{formatChange(stats.percent, "%")}</strong><small>{formatChange(stats.delta)} 卡时</small></span></button>)}</div> : <p className="trend-list-empty">该周期暂无真实下跌数据</p>}</section>
    </div>

    <section className="trend-table-section">
      <header><div><h2>GPU 完整行情</h2><p>点击某一行切换上方主走势图</p></div><span>{sorted.length} 种 GPU</span></header>
      <div className="trend-filters trend-table-filters">
        <label className="trend-search"><MagnifyingGlass size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索完整行情" aria-label="搜索完整行情中的 GPU 型号" /></label>
        <select value={memory} onChange={(event) => setMemory(event.target.value)} aria-label="显存筛选"><option value="all">全部显存</option>{memories.map((value) => <option value={value} key={value}>{value}GB</option>)}</select>
        <div className="trend-direction" aria-label="涨跌筛选">{([["all", "全部"], ["up", "只看上涨"], ["down", "只看下跌"]] as const).map(([value, label]) => <button className={direction === value ? "is-active" : ""} onClick={() => setDirection(value)} type="button" key={value}>{label}</button>)}</div>
        <span className="trend-filter-count">当前显示 {sorted.length} 种</span>
      </div>
      {sorted.length ? <div className="trend-table">
        <div className="trend-table-head"><span>GPU</span><span>显存</span><button onClick={() => changeSort("price")} type="button">当前价 {sortKey === "price" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button><button onClick={() => changeSort("day")} type="button">本周涨跌 {sortKey === "day" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button><button onClick={() => changeSort("week")} type="button">4周涨跌 {sortKey === "week" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button><span>3个月涨跌</span><span>最高价</span><span>最低价</span><button onClick={() => changeSort("updated")} type="button">更新时间 {sortKey === "updated" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button></div>
        <div className="trend-table-body">{pageItems.map((item) => {
          const day = priceStats(item, 2); const week = priceStats(item, 4); const month = priceStats(item, 14); const current = day.current;
          return <button className={selectedModel === item.gpu_model ? "is-selected" : ""} type="button" onClick={() => chooseGpu(item.gpu_model)} key={item.gpu_model}><span><strong>{item.gpu_model}</strong><small>{item.tier || "GPU"}</small></span><span data-label="显存">{item.vram_gb ? `${item.vram_gb}GB` : "—"}</span><span data-label="当前价"><strong>{formatPrice(current)}</strong></span><span data-label="本周" className={day.percent >= 0 ? "is-up" : "is-down"}>{day.enough ? formatChange(day.percent, "%") : "—"}</span><span data-label="4周" className={week.percent >= 0 ? "is-up" : "is-down"}>{week.enough ? formatChange(week.percent, "%") : "—"}</span><span data-label="3个月" className={month.percent >= 0 ? "is-up" : "is-down"}>{month.enough ? formatChange(month.percent, "%") : "—"}</span><span data-label="最高价">{month.enough ? formatPrice(month.high) : "—"}</span><span data-label="最低价">{month.enough ? formatPrice(month.low) : "—"}</span><span data-label="更新时间">{new Date(meta?.history_updated_at ?? meta?.observed_at ?? "").toLocaleDateString("zh-CN")}</span></button>;
        })}</div>
        <nav className="trend-pagination" aria-label="GPU 行情分页"><span>第 {page} / {pageCount} 页 · 共 {sorted.length} 种</span><div><button type="button" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>{Array.from({ length: pageCount }, (_, index) => index + 1).map((value) => <button className={page === value ? "is-active" : ""} type="button" onClick={() => setPage(value)} aria-label={`第 ${value} 页`} aria-current={page === value ? "page" : undefined} key={value}>{value}</button>)}<button type="button" disabled={page === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>下一页</button></div></nav>
      </div> : <div className="trend-search-empty"><MagnifyingGlass size={28} /><strong>没有匹配的行情</strong><p>请调整 GPU 型号、显存或涨跌条件。</p></div>}
    </section>
  </section>;
}
