"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { ArrowClockwise, ArrowDown, ArrowUp, CaretDown, CaretUp, ChartLine, Database, MagnifyingGlass, MapPin } from "@phosphor-icons/react";
import { publicApiEnvelopeRequest } from "@/lib/api";
import { getMobileLatestMarket, getMobileMarketModels, getMobileMarketSources, getMobileRegionalQuotes, type MobileLatestMarket, type MobileMarketModel, type MobileMarketSource, type MobileRegionalQuotes } from "@/lib/mobile-market-api";
import { KAI_REALTIME_SOURCE } from "@/lib/web-business-contract";
import { MarketCandlestickChart } from "@/components/market-candlestick-chart";
import type { MarketChartSnapshot } from "@/lib/market-candlestick-chart";

export type PricePoint = { date: string; median: number };
export type MarketSummary = {
  gpu_model: string;
  tier?: string;
  vram_gb?: number;
  min_price: number;
  median_price: number;
  official_min_price?: number;
  official_median_price?: number;
  history: PricePoint[];
};
export type MarketMeta = { observed_at: string; history_updated_at?: string };
export type MarketResponse = { data: MarketSummary[]; meta: MarketMeta };
export type InitialMarketDashboard = MarketResponse & {
  models: MobileMarketModel[];
  sources: MobileMarketSource[];
};
type RangeDays = 28 | 56 | 90;
type SortKey = "price" | "day" | "week" | "updated";
type Direction = "all" | "up" | "down";

const ranges: { value: RangeDays; label: string }[] = [
  { value: 28, label: "4周" },
  { value: 56, label: "8周" },
  { value: 90, label: "3个月" },
];
const PAGE_SIZE = 15;
const MARKET_AUTO_REFRESH_MS = 10_000;

function validHistory(item: MarketSummary) {
  return item.history.filter((point) => point.median > 0);
}

function findMobileModel(models: MobileMarketModel[], label: string) {
  const selected = label.trim().toLowerCase();
  return models.find((item) => `${item.gpu_model} ${item.gpu_variant}`.trim().toLowerCase() === selected)
    ?? models.find((item) => item.gpu_model.trim().toLowerCase() === selected);
}

function pointsWithinDays<T extends { date: string }>(input: T[], days: number) {
  const points = [...input]
    .filter((point) => Number.isFinite(Date.parse(point.date)))
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  const latest = points.at(-1);
  if (!latest) return points;
  const cutoff = Date.parse(latest.date) - Math.max(days - 1, 0) * 86_400_000;
  return points.filter((point) => Date.parse(point.date) >= cutoff);
}

function rangePoints(item: MarketSummary, days: number) {
  return pointsWithinDays(validHistory(item), days);
}

function preferredMarketModel(items: MarketSummary[], models: MobileMarketModel[] = []) {
  return [...items].sort((a, b) => {
    const aSevenDayCoverage = new Set(rangePoints(a, 7).map((point) => point.date.slice(0, 10))).size >= 7 ? 1 : 0;
    const bSevenDayCoverage = new Set(rangePoints(b, 7).map((point) => point.date.slice(0, 10))).size >= 7 ? 1 : 0;
    if (aSevenDayCoverage !== bSevenDayCoverage) return bSevenDayCoverage - aSevenDayCoverage;
    const a4090 = /^RTX\s*4090(?:\s|$)/i.test(a.gpu_model) ? 1 : 0;
    const b4090 = /^RTX\s*4090(?:\s|$)/i.test(b.gpu_model) ? 1 : 0;
    if (a4090 !== b4090) return b4090 - a4090;
    const aSamples = findMobileModel(models, a.gpu_model)?.sample_count ?? 0;
    const bSamples = findMobileModel(models, b.gpu_model)?.sample_count ?? 0;
    if (aSamples !== bSamples) return bSamples - aSamples;
    return validHistory(b).length - validHistory(a).length;
  })[0]?.gpu_model ?? "";
}

function priceStats(item: MarketSummary, days: number) {
  const points = rangePoints(item, days);
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

function regionalCardHours(value: number | null, rate: number | undefined) {
  if (value == null || !Number.isFinite(value) || !rate || !Number.isFinite(rate) || rate <= 0) return "—";
  return `${(value / rate).toFixed(3)} 卡时`;
}

function linearPath(points: { x: number; y: number }[]) {
  return points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
}

function visualTrendPoints(values: number[], targetCount = 36) {
  if (values.length <= targetCount || targetCount < 3) {
    return values.map((value, index) => ({ index, value }));
  }

  // Largest-triangle sampling keeps real turning points instead of averaging
  // away the peaks and valleys that make a price trend readable.
  const sampled = [{ index: 0, value: values[0] }];
  const bucketSize = (values.length - 2) / (targetCount - 2);
  let anchorIndex = 0;

  for (let bucket = 0; bucket < targetCount - 2; bucket += 1) {
    const averageStart = Math.floor((bucket + 1) * bucketSize) + 1;
    const averageEnd = Math.min(Math.floor((bucket + 2) * bucketSize) + 1, values.length);
    const averageEntries = values.slice(averageStart, averageEnd);
    const averageX = averageEntries.length
      ? averageStart + (averageEntries.length - 1) / 2
      : values.length - 1;
    const averageY = averageEntries.length
      ? averageEntries.reduce((sum, value) => sum + value, 0) / averageEntries.length
      : values.at(-1)!;

    const rangeStart = Math.floor(bucket * bucketSize) + 1;
    const rangeEnd = Math.min(Math.floor((bucket + 1) * bucketSize) + 1, values.length - 1);
    let selectedIndex = rangeStart;
    let largestArea = -1;

    for (let index = rangeStart; index < Math.max(rangeStart + 1, rangeEnd); index += 1) {
      const area = Math.abs(
        (anchorIndex - averageX) * (values[index] - values[anchorIndex])
        - (anchorIndex - index) * (averageY - values[anchorIndex]),
      );
      if (area > largestArea) {
        largestArea = area;
        selectedIndex = index;
      }
    }

    sampled.push({ index: selectedIndex, value: values[selectedIndex] });
    anchorIndex = selectedIndex;
  }

  sampled.push({ index: values.length - 1, value: values.at(-1)! });
  return sampled;
}

function monotonePath(points: { x: number; y: number }[]) {
  if (points.length < 2) return linearPath(points);
  const slopes = points.slice(1).map((point, index) => {
    const previous = points[index];
    return (point.y - previous.y) / (point.x - previous.x || 1);
  });
  const tangents = points.map((_point, index) => {
    if (index === 0) return slopes[0];
    if (index === points.length - 1) return slopes.at(-1)!;
    const before = slopes[index - 1];
    const after = slopes[index];
    return before * after <= 0 ? 0 : (2 * before * after) / (before + after);
  });
  for (let index = 0; index < slopes.length; index += 1) {
    if (slopes[index] === 0) {
      tangents[index] = 0;
      tangents[index + 1] = 0;
      continue;
    }
    const left = tangents[index] / slopes[index];
    const right = tangents[index + 1] / slopes[index];
    const magnitude = Math.hypot(left, right);
    if (magnitude > 3) {
      const scale = 3 / magnitude;
      tangents[index] = scale * left * slopes[index];
      tangents[index + 1] = scale * right * slopes[index];
    }
  }
  return points.slice(1).reduce((path, point, index) => {
    const previous = points[index];
    const width = point.x - previous.x;
    return `${path} C ${previous.x + width / 3} ${previous.y + tangents[index] * width / 3}, ${point.x - width / 3} ${point.y - tangents[index + 1] * width / 3}, ${point.x} ${point.y}`;
  }, `M ${points[0].x} ${points[0].y}`);
}

function MiniTrend({ item, days, tone }: { item: MarketSummary; days: RangeDays; tone: "up" | "down" }) {
  const stats = priceStats(item, days);
  if (!stats.enough) return <span className="trend-mini-empty">历史积累中</span>;
  const rawValues = stats.points.map((point) => point.median);
  const visualPoints = visualTrendPoints(rawValues);
  const values = visualPoints.map((point) => point.value);
  const min = Math.min(...values);
  const rawRange = Math.max(...values) - min;
  const padding = Math.max(rawRange * .11, Math.max(...values) * .005, .01);
  const chartMin = min - padding;
  const chartRange = rawRange + padding * 2 || 1;
  const points = visualPoints.map(({ index, value }) => ({
    x: (index / Math.max(1, rawValues.length - 1)) * 240,
    y: 54 - ((value - chartMin) / chartRange) * 45,
  }));
  const line = monotonePath(points);
  const fillId = `trend-fill-${item.gpu_model.replace(/[^a-z0-9]/gi, "-").toLowerCase()}`;
  const area = `${line} L 240 64 L 0 64 Z`;
  return <svg className={`trend-mini-line is-${tone}`} viewBox="0 0 240 64" preserveAspectRatio="none" aria-hidden="true">
    <defs><linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={tone === "up" ? "#0b8f83" : "#d9434f"} stopOpacity=".22" /><stop offset="100%" stopColor={tone === "up" ? "#0b8f83" : "#d9434f"} stopOpacity="0" /></linearGradient></defs>
    <path className="trend-mini-area" d={area} fill={`url(#${fillId})`} />
    <path className="trend-mini-stroke" d={line} />
  </svg>;
}

export function LiveMarketPanel({ featured = false, initialData = null }: { featured?: boolean; initialData?: InitialMarketDashboard | null }) {
  const initialMarkets = (initialData?.data ?? []).filter((item) => item.median_price > 0 || validHistory(item).length > 0);
  const initialModel = preferredMarketModel(initialMarkets, initialData?.models);
  const [markets, setMarkets] = useState<MarketSummary[]>(initialMarkets);
  const [meta, setMeta] = useState<MarketMeta | null>(initialData?.meta ?? null);
  const [selectedModel, setSelectedModel] = useState(initialModel);
  const [gpuPickerQuery, setGpuPickerQuery] = useState(initialModel);
  const [gpuPickerOpen, setGpuPickerOpen] = useState(false);
  const [gpuPickerDirty, setGpuPickerDirty] = useState(false);
  const [gpuPickerActive, setGpuPickerActive] = useState(0);
  const [days, setDays] = useState<RangeDays>(90);
  const [query, setQuery] = useState("");
  const [memory, setMemory] = useState("all");
  const [direction, setDirection] = useState<Direction>("all");
  const [mobileBoard, setMobileBoard] = useState<"gainers" | "losers">("gainers");
  const [sortKey, setSortKey] = useState<SortKey>("price");
  const [sortAsc, setSortAsc] = useState(true);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(initialData ? "ready" : "loading");
  const [message, setMessage] = useState("");
  const [mobileModels, setMobileModels] = useState<MobileMarketModel[]>(initialData?.models ?? []);
  const [sourceStates, setSourceStates] = useState<MobileMarketSource[]>(
    (initialData?.sources ?? []).filter((source) => source.source.toLowerCase() === KAI_REALTIME_SOURCE),
  );
  const [latest, setLatest] = useState<MobileLatestMarket | null>(null);
  const [regionalQuotes, setRegionalQuotes] = useState<MobileRegionalQuotes | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [chartSnapshot, setChartSnapshot] = useState<MarketChartSnapshot | null>(null);
  const selectedModelRef = useRef(initialModel);
  const catalogRequest = useRef(0);

  const load = useCallback(async (force = false, showLoading = true) => {
    const request = ++catalogRequest.current;
    if (showLoading) setStatus("loading");
    try {
      const [payload, modelsPayload, sourcesPayload] = await Promise.all([
        publicApiEnvelopeRequest<MarketSummary[], MarketMeta>("/api/v1/public/market/summary", 60_000, force) as Promise<MarketResponse>,
        getMobileMarketModels(),
        getMobileMarketSources(),
      ]);
      if (request !== catalogRequest.current) return;
      const data = (payload.data ?? []).filter((item) => item.median_price > 0 || validHistory(item).length > 0);
      const nextMobileModels = modelsPayload.items ?? [];
      const currentSelection = selectedModelRef.current;
      const selectableMarkets = data.filter((item) => Boolean(findMobileModel(nextMobileModels, item.gpu_model)));
      const selectionIsValid = Boolean(
        currentSelection
        && data.some((item) => item.gpu_model === currentSelection)
        && findMobileModel(nextMobileModels, currentSelection),
      );
      const preferredModel = preferredMarketModel(
        selectableMarkets.length ? selectableMarkets : data,
        nextMobileModels,
      );
      const nextSelectedModel = selectionIsValid ? currentSelection : preferredModel;
      setMarkets(data);
      setMeta(payload.meta);
      setMobileModels(nextMobileModels);
      setSourceStates((sourcesPayload.items ?? []).filter((source) => source.source.toLowerCase() === KAI_REALTIME_SOURCE));
      selectedModelRef.current = nextSelectedModel;
      setSelectedModel(nextSelectedModel);
      if (nextSelectedModel !== currentSelection) {
        setGpuPickerQuery(nextSelectedModel);
        setGpuPickerOpen(false);
        setGpuPickerDirty(false);
        setGpuPickerActive(0);
        setChartSnapshot(null);
      } else {
        setGpuPickerQuery((current) => current || nextSelectedModel);
      }
      setMessage("");
      setStatus("ready");
    } catch (error) {
      if (request !== catalogRequest.current) return;
      setMessage(error instanceof Error ? error.message : "行情读取失败");
      setStatus((current) => showLoading || current === "loading" ? "error" : current);
    }
  }, []);
  useEffect(() => { void load(false, !initialData); }, [initialData, load]);
  useEffect(() => {
    const timer = window.setInterval(() => { void load(true, false); }, MARKET_AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const model = findMobileModel(mobileModels, selectedModel);
    if (!model) { setLatest(null); setRegionalQuotes(null); return; }
    let active = true;
    setLiveLoading(true);
    setLatest((current) => current?.gpu_model === model.gpu_model && current.gpu_variant === model.gpu_variant ? current : null);
    setRegionalQuotes((current) => current?.gpu_model === model.gpu_model && current.gpu_variant === model.gpu_variant ? current : null);
    Promise.allSettled([getMobileLatestMarket(model), getMobileRegionalQuotes(model)])
      .then(([latestResult, regionalResult]) => {
        if (!active) return;
        if (latestResult.status === "fulfilled") setLatest(latestResult.value);
        if (regionalResult.status === "fulfilled") setRegionalQuotes(regionalResult.value);
      })
      .finally(() => { if (active) setLiveLoading(false); });
    return () => { active = false; };
  }, [mobileModels, selectedModel]);

  const memories = useMemo(() => [...new Set(markets.map((item) => item.vram_gb).filter((value): value is number => Boolean(value)))].sort((a, b) => a - b), [markets]);
  const selected = markets.find((item) => item.gpu_model === selectedModel) ?? null;
  const selectedMobileModel = selected ? findMobileModel(mobileModels, selected.gpu_model) ?? null : null;
  const selectedStats = selected ? priceStats(selected, days) : null;
  const longRangeLabel = ranges.find((range) => range.value === days)?.label ?? `${days} 天`;
  const selectedChartIdentity = selectedMobileModel
    ? `${selectedMobileModel.gpu_model}|${selectedMobileModel.gpu_variant}`
    : "";
  const activeChartSnapshot = chartSnapshot?.identity === selectedChartIdentity ? chartSnapshot : null;
  const chartSummary = activeChartSnapshot?.summary ?? null;
  const chartRangeLabel = activeChartSnapshot?.range === "24h"
    ? "24小时"
    : activeChartSnapshot?.range === "7d"
      ? "7天"
      : activeChartSnapshot?.range === "30d"
        ? "30天"
        : "当前周期";
  const dailyMovers = markets.map((item) => priceStats(item, 7)).filter((stats) => stats.enough);
  const risingToday = dailyMovers.filter((stats) => stats.delta > 0).length;
  const fallingToday = dailyMovers.filter((stats) => stats.delta < 0).length;

  const filtered = useMemo(() => markets.filter((item) => {
    const needle = query.trim().toLowerCase();
    const searchable = [
      item.gpu_model,
      item.tier ?? "",
      item.vram_gb ? `${item.vram_gb}GB` : "",
    ].join(" ").toLowerCase();
    if (needle && !searchable.includes(needle)) return false;
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
    const value = (item: MarketSummary) => sortKey === "price" ? priceStats(item, 7).current : sortKey === "day" ? priceStats(item, 7).percent : sortKey === "week" ? priceStats(item, 28).percent : new Date(meta?.history_updated_at ?? meta?.observed_at ?? 0).getTime();
    return (value(a) - value(b)) * (sortAsc ? 1 : -1);
  }), [filtered, sortKey, sortAsc, meta]);
  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageItems = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const gpuPickerOptions = useMemo(() => {
    const needle = gpuPickerDirty ? gpuPickerQuery.trim().toLowerCase() : "";
    if (!needle) return markets;
    const matches = markets.filter((item) => [
      item.gpu_model,
      item.tier ?? "",
      item.vram_gb ? `${item.vram_gb}gb` : "",
    ].some((value) => value.toLowerCase().includes(needle)));
    const relevance = (item: MarketSummary) => {
      const label = item.gpu_model.trim().toLowerCase();
      const family = label.split(/\s+/)[0];
      if (label === needle) return 0;
      if (family === needle) return 1;
      if (label.startsWith(needle)) return 2;
      return 3;
    };
    return matches.sort((a, b) => relevance(a) - relevance(b) || a.gpu_model.localeCompare(b.gpu_model));
  }, [gpuPickerDirty, gpuPickerQuery, markets]);
  useEffect(() => setPage(1), [query, memory, direction, days, sortKey, sortAsc]);
  useEffect(() => { if (page > pageCount) setPage(pageCount); }, [page, pageCount]);

  const changeSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((value) => !value);
    else { setSortKey(key); setSortAsc(key === "price"); }
  };
  const chooseGpu = (model: string, scrollToChart = true) => {
    selectedModelRef.current = model;
    setSelectedModel(model);
    setChartSnapshot(null);
    setGpuPickerQuery(model);
    setGpuPickerOpen(false);
    setGpuPickerDirty(false);
    setGpuPickerActive(0);
    if (scrollToChart) document.getElementById("gpu-main-chart")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const updateGpuPicker = (value: string) => {
    setGpuPickerQuery(value);
    setGpuPickerOpen(true);
    setGpuPickerDirty(true);
    setGpuPickerActive(0);
  };
  const commitGpuPicker = () => {
    if (!gpuPickerDirty) {
      setGpuPickerQuery(selectedModel);
      setGpuPickerOpen(false);
      return;
    }
    const needle = gpuPickerQuery.trim().toLowerCase();
    const exact = markets.find((item) => item.gpu_model.toLowerCase() === needle);
    const family = gpuPickerOptions.find((item) => item.gpu_model.trim().toLowerCase().split(/\s+/)[0] === needle);
    const next = exact ?? family ?? (gpuPickerOptions.length === 1 ? gpuPickerOptions[0] : null);
    if (next) chooseGpu(next.gpu_model, false);
    else setGpuPickerQuery(selectedModel);
    setGpuPickerOpen(false);
    setGpuPickerDirty(false);
  };
  const handleGpuPickerKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setGpuPickerOpen(false);
      setGpuPickerQuery(selectedModel);
      setGpuPickerDirty(false);
      return;
    }
    if (!gpuPickerOptions.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setGpuPickerOpen(true);
      setGpuPickerActive((current) => {
        const offset = event.key === "ArrowDown" ? 1 : -1;
        return (current + offset + gpuPickerOptions.length) % gpuPickerOptions.length;
      });
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (gpuPickerOpen && gpuPickerOptions.length) {
        chooseGpu(gpuPickerOptions[gpuPickerActive]?.gpu_model ?? gpuPickerOptions[0].gpu_model, false);
      } else {
        commitGpuPicker();
      }
    }
  };

  if (status === "loading") return <section className="trend-state-panel"><Database size={34} weight="light" /><strong>正在加载算力行情</strong><p>正在读取真实历史价格。</p></section>;
  if (status === "error") {
    return <section className="trend-state-panel is-error">
      <Database size={34} weight="light" />
      <strong>KAI 行情服务暂时不可用</strong>
      <p>{message}</p>
      <div className="trend-state-actions">
        <button type="button" onClick={() => void load(true)}><ArrowClockwise size={15} />重新读取</button>
        <Link href="/market">浏览服务器</Link>
      </div>
    </section>;
  }
  if (!markets.length) return <section className="trend-state-panel"><ChartLine size={34} weight="light" /><strong>暂无行情数据</strong><p>当前没有足够的真实历史价格。</p></section>;
  if (featured) return <section className="market-panel trend-home-preview"><div className="market-panel__head"><div><p className="hero-eyebrow">GPU PRICE TRENDS</p><h2>GPU 算力行情</h2><p>观察真实价格变化，再进入市场寻找资源。</p></div><Link href="/trend">查看完整行情</Link></div><div>{markets.slice(0, 3).map((item) => { const stats = priceStats(item, 7); return <article key={item.gpu_model}><span><strong>{item.gpu_model}</strong><small>{item.vram_gb ? `${item.vram_gb}GB 显存` : item.tier}</small></span><span><small>当前价格</small><strong>{formatPrice(stats.current)}</strong></span><span className={stats.percent >= 0 ? "is-up" : "is-down"}><small>本周涨跌</small><strong>{stats.enough ? formatChange(stats.percent, "%") : "—"}</strong></span></article>; })}</div></section>;

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
          <div
            className="trend-focus-gpu-picker"
            onBlur={(event) => {
              if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
              commitGpuPicker();
            }}
          >
            <label htmlFor="trend-gpu-search">主图 GPU</label>
            <div className={`trend-focus-picker-shell ${gpuPickerOpen ? "is-open" : ""}`}>
              <MagnifyingGlass size={18} />
              <input
                id="trend-gpu-search"
                value={gpuPickerQuery}
                onChange={(event) => updateGpuPicker(event.target.value)}
                onFocus={(event) => {
                  setGpuPickerOpen(true);
                  setGpuPickerDirty(false);
                  setGpuPickerActive(0);
                  event.currentTarget.select();
                }}
                onClick={() => {
                  if (gpuPickerOpen) return;
                  setGpuPickerOpen(true);
                  setGpuPickerDirty(false);
                  setGpuPickerActive(0);
                }}
                onKeyDown={handleGpuPickerKeyDown}
                placeholder="输入 GPU 型号"
                role="combobox"
                aria-label="选择要查看的 GPU"
                aria-autocomplete="list"
                aria-expanded={gpuPickerOpen}
                aria-controls="trend-gpu-options"
                aria-activedescendant={gpuPickerOpen && gpuPickerOptions.length ? `trend-gpu-option-${gpuPickerActive}` : undefined}
              />
              {selected.vram_gb && <em>{selected.vram_gb}GB</em>}
              <button
                className="trend-focus-picker-toggle"
                type="button"
                aria-label={gpuPickerOpen ? "收起 GPU 选择" : "展开 GPU 选择"}
                aria-expanded={gpuPickerOpen}
                onClick={() => setGpuPickerOpen((value) => {
                  const next = !value;
                  if (next) {
                    setGpuPickerDirty(false);
                    setGpuPickerActive(0);
                  }
                  return next;
                })}
              ><CaretDown size={15} /></button>
            </div>
            {gpuPickerOpen && <div className="trend-focus-gpu-options" id="trend-gpu-options" role="listbox">
              {gpuPickerOptions.length ? gpuPickerOptions.map((item, index) => <button
                className={index === gpuPickerActive ? "is-active" : ""}
                id={`trend-gpu-option-${index}`}
                type="button"
                role="option"
                aria-selected={item.gpu_model === selectedModel}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setGpuPickerActive(index)}
                onClick={() => chooseGpu(item.gpu_model, false)}
                key={item.gpu_model}
              >
                <span><strong>{item.gpu_model}</strong><small>{item.tier || "GPU 算力型号"}</small></span>
                <em>{item.vram_gb ? `${item.vram_gb}GB` : "—"}</em>
              </button>) : <p>没有匹配的 GPU 型号</p>}
            </div>}
          </div>
          <div className="trend-focus-period"><span>长期排行周期</span><div className="trend-ranges" aria-label="长期排行周期">{ranges.map((range) => <button className={days === range.value ? "is-active" : ""} aria-pressed={days === range.value} onClick={() => setDays(range.value)} type="button" key={range.value}>{range.label}</button>)}</div></div>
        </div>
        <div className="trend-focus-quote">
          <div className="trend-current-price"><span>当前实时中位价</span><strong>{latest?.summary.median_price_card_hours ? formatPrice(latest.summary.median_price_card_hours) : selectedStats.current ? formatPrice(selectedStats.current) : "数据不足"}</strong><small>{liveLoading ? "正在刷新实时行情" : latest ? `${latest.summary.sample_count} 条 KAI 报价` : "历史行情兼容模式"}</small></div>
          {selectedStats.enough && <div className={`trend-focus-change ${selectedStats.delta >= 0 ? "is-up" : "is-down"}`}><span>长期 · {longRangeLabel}涨跌</span><strong>{formatChange(selectedStats.percent, "%")}</strong></div>}
          <Link href={`/market?gpu=${encodeURIComponent(selected.gpu_model)}`}>查看可租资源</Link>
        </div>
      </header>
      <MarketCandlestickChart model={selectedMobileModel} initialLatest={latest} onLatest={setLatest} onSnapshot={setChartSnapshot} />
      <div className="trend-period-stats" aria-label={`${chartRangeLabel} K 线统计`}>
        <span><small>{chartRangeLabel}历史最高价</small><strong>{chartSummary ? formatPrice(chartSummary.high) : "—"}</strong></span>
        <span><small>{chartRangeLabel}历史最低价</small><strong>{chartSummary ? formatPrice(chartSummary.low) : "—"}</strong></span>
        <span><small>{chartRangeLabel}历史中位价</small><strong>{chartSummary ? formatPrice(chartSummary.median) : "—"}</strong></span>
        <span><small>{chartRangeLabel}历史涨跌</small><strong className={chartSummary ? chartSummary.change >= 0 ? "is-up" : "is-down" : undefined}>{chartSummary ? formatChange(chartSummary.changePct, "%") : "—"}</strong></span>
      </div>
    </section>}

    {selected && <section className="trend-regional-spread" aria-labelledby="trend-regional-title">
      <header><div><p className="hero-eyebrow">KAI REGIONAL QUOTES</p><h2 id="trend-regional-title">区域价差</h2><span>{selected.gpu_model}{regionalQuotes?.gpu_variant ? ` · ${regionalQuotes.gpu_variant}` : ""}</span></div><small>{regionalQuotes ? `${regionalQuotes.region_count} 个区域 · ${regionalQuotes.market_status}` : liveLoading ? "正在刷新" : "暂无区域报价"}</small></header>
      {regionalQuotes?.regions.length ? <div className="trend-regional-grid">{regionalQuotes.regions.map((region) => <article className={region.is_lowest ? "is-lowest" : ""} key={region.region_code || region.region}><div><MapPin size={16}/><span><strong>{region.region}</strong><small>{region.quote_sample_count} 条报价 · {region.location_count} 个地点</small></span></div><dl><div><dt>中位价</dt><dd>{regionalCardHours(region.median_price_cny, latest?.summary.card_hour_rmb_rate)}</dd></div><div><dt>区间</dt><dd>{regionalCardHours(region.min_price_cny, latest?.summary.card_hour_rmb_rate)} – {regionalCardHours(region.max_price_cny, latest?.summary.card_hour_rmb_rate)}</dd></div></dl><b>{region.is_lowest ? "当前最低" : region.relative_to_lowest_pct == null ? "—" : `较最低 +${region.relative_to_lowest_pct.toFixed(2)}%`}</b></article>)}</div> : <div className="trend-regional-empty">{liveLoading ? "正在读取同型号区域报价…" : "该型号当前没有可比较的区域报价"}</div>}
      <p>按同一 GPU 型号与显存比较 KAI 当前报价观察值，统一显示为卡时 / GPU·小时；报价数量不代表实时库存。</p>
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
        <div className="trend-direction" aria-label="涨跌筛选">{([["all", "全部"], ["up", "只看上涨"], ["down", "只看下跌"]] as const).map(([value, label]) => <button className={direction === value ? "is-active" : ""} aria-pressed={direction === value} onClick={() => setDirection(value)} type="button" key={value}>{label}</button>)}</div>
        <span className="trend-filter-count" aria-live="polite">当前显示 {sorted.length} 种</span>
      </div>
      {sorted.length ? <div className="trend-table">
        <div className="trend-table-head"><span>GPU</span><span>显存</span><button onClick={() => changeSort("price")} type="button">当前价 {sortKey === "price" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button><button onClick={() => changeSort("day")} type="button">本周涨跌 {sortKey === "day" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button><button onClick={() => changeSort("week")} type="button">4周涨跌 {sortKey === "week" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button><span>3个月涨跌</span><span>最高价</span><span>最低价</span><button onClick={() => changeSort("updated")} type="button">更新时间 {sortKey === "updated" && (sortAsc ? <CaretUp /> : <CaretDown />)}</button></div>
        <div className="trend-table-body">{pageItems.map((item) => {
          const day = priceStats(item, 7); const week = priceStats(item, 28); const month = priceStats(item, 90); const current = day.current;
          return <button className={selectedModel === item.gpu_model ? "is-selected" : ""} type="button" onClick={() => chooseGpu(item.gpu_model)} key={item.gpu_model}><span><strong>{item.gpu_model}</strong><small>{item.tier || "GPU"}</small></span><span data-label="显存">{item.vram_gb ? `${item.vram_gb}GB` : "—"}</span><span data-label="当前价"><strong>{formatPrice(current)}</strong></span><span data-label="本周" className={day.percent >= 0 ? "is-up" : "is-down"}>{day.enough ? formatChange(day.percent, "%") : "—"}</span><span data-label="4周" className={week.percent >= 0 ? "is-up" : "is-down"}>{week.enough ? formatChange(week.percent, "%") : "—"}</span><span data-label="3个月" className={month.percent >= 0 ? "is-up" : "is-down"}>{month.enough ? formatChange(month.percent, "%") : "—"}</span><span data-label="最高价">{month.enough ? formatPrice(month.high) : "—"}</span><span data-label="最低价">{month.enough ? formatPrice(month.low) : "—"}</span><span data-label="更新时间">{new Date(meta?.history_updated_at ?? meta?.observed_at ?? "").toLocaleDateString("zh-CN")}</span></button>;
        })}</div>
        <nav className="trend-pagination" aria-label="GPU 行情分页"><span>第 {page} / {pageCount} 页 · 共 {sorted.length} 种</span><div><button type="button" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>{Array.from({ length: pageCount }, (_, index) => index + 1).map((value) => <button className={page === value ? "is-active" : ""} type="button" onClick={() => setPage(value)} aria-label={`第 ${value} 页`} aria-current={page === value ? "page" : undefined} key={value}>{value}</button>)}<button type="button" disabled={page === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>下一页</button></div></nav>
      </div> : <div className="trend-search-empty"><MagnifyingGlass size={28} /><strong>没有匹配的行情</strong><p>请调整 GPU 型号、显存或涨跌条件。</p></div>}
    </section>
  </section>;
}
