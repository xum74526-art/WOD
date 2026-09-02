"use client";

import { Minus, Plus } from "@phosphor-icons/react";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  getMobileLatestMarket,
  getMobileMarketCandles,
  type MobileLatestMarket,
  type MobileMarketCandles,
  type MobileMarketModel,
} from "@/lib/mobile-market-api";
import {
  canMergeLiveReference,
  candleBodyWidth,
  candleTimeGeometry,
  chartCanvasLayout,
  chartPointerIndex,
  chartTimeTicks,
  contiguousValueSegments,
  defaultCandleZoomLimit,
  expectedCandleCount,
  marketCandleBucketLabel,
  marketChartQuarantineNotice,
  marketChartSummary,
  matchesMarketCandleSelection,
  mergeLiveReference,
  marketChartCoverage,
  movingAverageByTime,
  nextCandleZoomLimit,
  normalizeMarketCandles,
  paddedPriceDomain,
  resolveMarketChartLatestReadout,
  resolveMarketChartReferences,
  type MarketChartCandle,
  type MarketChartRange,
  type MarketChartSnapshot,
} from "@/lib/market-candlestick-chart";
import styles from "./market-candlestick-chart.module.css";

type ScopedValue<T> = { key: string; value: T };

type MarketCandlestickChartProps = {
  model: MobileMarketModel | null;
  initialLatest?: MobileLatestMarket | null;
  onLatest?: (value: MobileLatestMarket) => void;
  onSnapshot?: (snapshot: MarketChartSnapshot) => void;
};

type ChartPoint = MarketChartCandle & {
  x: number;
  openY: number;
  highY: number;
  lowY: number;
  closeY: number;
};

const MOBILE_WIDTH = 360;
const RANGE_OPTIONS: Array<{ value: MarketChartRange; label: string }> = [
  { value: "7d", label: "7天" },
  { value: "30d", label: "30天" },
];
const LATEST_REFRESH_MS = 10_000;
const HISTORY_REFRESH_MS: Record<MarketChartRange, number> = {
  "24h": 30_000,
  "7d": 300_000,
  "30d": 300_000,
};
const MA_SERIES = [
  { period: 5, color: "var(--kline-ma-5)" },
  { period: 10, color: "var(--kline-ma-10)" },
  { period: 20, color: "var(--kline-ma-20)" },
] as const;

function modelIdentity(model: MobileMarketModel | null) {
  return model ? `${model.gpu_model}|${model.gpu_variant}` : "";
}

function formatPrice(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "--";
  return value >= 100 ? value.toFixed(2) : value.toFixed(3);
}

function formatAxis(value: number, span = 1) {
  const digits = Math.abs(span) < 0.01 ? 4 : Math.abs(span) < 1 ? 3 : 2;
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, useGrouping: false });
}

function formatDateTime(value: number | string | null | undefined) {
  const timestamp = typeof value === "number" ? value : value ? Date.parse(value) : Number.NaN;
  if (!Number.isFinite(timestamp)) return "当前报价";
  return new Date(timestamp).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatTimeLabel(time: number, range: MarketChartRange) {
  const value = new Date(time);
  const pad = (part: number) => String(part).padStart(2, "0");
  const monthDay = `${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  const clock = `${pad(value.getHours())}:${pad(value.getMinutes())}`;
  return range === "24h" ? `${monthDay} ${clock}` : monthDay;
}

function latestObservationAt(value: MobileLatestMarket | null) {
  const timestamps = (value?.items ?? [])
    .map((item) => Date.parse(item.observed_at || item.source_checked_at || ""))
    .filter(Number.isFinite);
  if (timestamps.length) return new Date(Math.max(...timestamps)).toISOString();
  return null;
}

function candleChange(candle: MarketChartCandle | undefined) {
  if (!candle || candle.open === 0) return null;
  return ((candle.close - candle.open) / candle.open) * 100;
}

function signedPercent(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function linePath(points: Array<{ x: number; y: number }>) {
  return points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}

export function MarketCandlestickChart({ model, initialLatest = null, onLatest, onSnapshot }: MarketCandlestickChartProps) {
  const chartStatusId = useId();
  const identity = modelIdentity(model);
  const [range, setRange] = useState<MarketChartRange>("30d");
  const selectionKey = `${identity}|${range}`;
  const [candleState, setCandleState] = useState<ScopedValue<MobileMarketCandles> | null>(null);
  const [latestState, setLatestState] = useState<ScopedValue<MobileLatestMarket> | null>(() => (
    initialLatest && identity ? { key: identity, value: initialLatest } : null
  ));
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyErrorState, setHistoryErrorState] = useState<ScopedValue<string> | null>(null);
  const [requestedVisibleCount, setRequestedVisibleCount] = useState(defaultCandleZoomLimit("30d", MOBILE_WIDTH));
  const [selectedRelativeIndex, setSelectedRelativeIndex] = useState(0);
  const [cursorVisible, setCursorVisible] = useState(false);
  const [renderedChartWidth, setRenderedChartWidth] = useState(MOBILE_WIDTH);
  const historyRequest = useRef(0);
  const latestRequest = useRef(0);
  const historyInFlight = useRef<string | null>(null);
  const latestInFlight = useRef<string | null>(null);
  const latestIdentity = useRef(identity);
  const zoomTouched = useRef(false);
  const zoomSelection = useRef(selectionKey);
  const chartFrameRef = useRef<HTMLDivElement>(null);
  const modelRef = useRef(model);
  const onLatestRef = useRef(onLatest);
  const onSnapshotRef = useRef(onSnapshot);
  modelRef.current = model;
  onLatestRef.current = onLatest;
  onSnapshotRef.current = onSnapshot;

  const payload = candleState?.key === selectionKey ? candleState.value : null;
  const latest = latestState?.key === identity ? latestState.value : null;
  const historyError = historyErrorState?.key === selectionKey ? historyErrorState.value : "";

  useEffect(() => {
    if (!initialLatest || !identity) return;
    if (initialLatest.gpu_model !== model?.gpu_model || initialLatest.gpu_variant !== model?.gpu_variant) return;
    setLatestState({ key: identity, value: initialLatest });
  }, [identity, initialLatest, model?.gpu_model, model?.gpu_variant]);

  const refreshHistory = useCallback(async (showLoading = false) => {
    const activeModel = modelRef.current;
    if (!activeModel) return;
    const requestKey = `${modelIdentity(activeModel)}|${range}`;
    if (historyInFlight.current === requestKey) return;
    historyInFlight.current = requestKey;
    const sequence = ++historyRequest.current;
    if (showLoading) setHistoryLoading(true);
    try {
      const value = await getMobileMarketCandles(activeModel, range);
      if (sequence !== historyRequest.current || requestKey !== `${modelIdentity(modelRef.current)}|${range}`) return;
      if (!matchesMarketCandleSelection(
        value,
        activeModel.gpu_model,
        activeModel.gpu_variant,
        range,
      )) throw new Error("K 线响应与当前选择不一致");
      setCandleState({ key: requestKey, value });
      setHistoryErrorState(null);
    } catch (error) {
      if (sequence !== historyRequest.current) return;
      setHistoryErrorState({
        key: requestKey,
        value: error instanceof Error ? error.message : "K 线读取失败",
      });
    } finally {
      if (historyInFlight.current === requestKey) historyInFlight.current = null;
      if (sequence === historyRequest.current) setHistoryLoading(false);
    }
  }, [identity, range]);

  const refreshLatest = useCallback(async () => {
    const activeModel = modelRef.current;
    if (!activeModel) return;
    const requestKey = modelIdentity(activeModel);
    if (latestInFlight.current === requestKey) return;
    latestInFlight.current = requestKey;
    const sequence = ++latestRequest.current;
    try {
      const value = await getMobileLatestMarket(activeModel);
      if (sequence !== latestRequest.current || requestKey !== modelIdentity(modelRef.current)) return;
      setLatestState({ key: requestKey, value });
      onLatestRef.current?.(value);
    } catch {
      // Keep the last verified quote when a transient polling request fails.
    } finally {
      if (latestInFlight.current === requestKey) latestInFlight.current = null;
    }
  }, [identity]);

  useEffect(() => {
    historyRequest.current += 1;
    if (latestIdentity.current !== identity) {
      latestRequest.current += 1;
      latestInFlight.current = null;
      latestIdentity.current = identity;
    }
    setSelectedRelativeIndex(0);
    setCursorVisible(false);
    if (!modelRef.current) {
      historyInFlight.current = null;
      latestInFlight.current = null;
      setHistoryLoading(false);
      setHistoryErrorState(null);
      return;
    }
    void refreshHistory(true);
    void refreshLatest();
    const latestTimer = window.setInterval(() => {
      if (!document.hidden) void refreshLatest();
    }, LATEST_REFRESH_MS);
    const historyTimer = window.setInterval(() => {
      if (!document.hidden) void refreshHistory(false);
    }, HISTORY_REFRESH_MS[range]);
    return () => {
      window.clearInterval(latestTimer);
      window.clearInterval(historyTimer);
    };
  }, [identity, range, refreshHistory, refreshLatest]);

  useEffect(() => () => {
    historyRequest.current += 1;
    latestRequest.current += 1;
    historyInFlight.current = null;
    latestInFlight.current = null;
  }, []);

  const payloadReference = useMemo(() => {
    const payloadPrice = payload?.latest_live_price_card_hours;
    const payloadHasLiveQuote = payloadPrice != null && Number.isFinite(payloadPrice) && payloadPrice > 0;
    return {
      price: payloadHasLiveQuote ? payloadPrice : null,
      observedAt: payload?.latest_live_observed_at ?? null,
      comparable: payload?.latest_live_comparable_to_history === true,
    };
  }, [payload]);

  const polledReference = useMemo(() => {
    const price = latest?.summary.median_price_card_hours;
    return {
      price: price != null && Number.isFinite(price) && price > 0 ? price : null,
      observedAt: latestObservationAt(latest),
      comparable: false,
    };
  }, [latest]);

  const historicalCandles = useMemo(
    () => normalizeMarketCandles(payload?.candles ?? []),
    [payload],
  );
  const comparableLiveMerged = useMemo(
    () => canMergeLiveReference(historicalCandles, payloadReference),
    [historicalCandles, payloadReference],
  );

  // The independently polled endpoint owns the page-level 10-second quote,
  // but may become this chart's display baseline only when OHLC is absent.
  // Comparability never transfers between the two responses.
  const references = useMemo(
    () => resolveMarketChartReferences(
      payloadReference,
      polledReference,
      historicalCandles.length > 0,
    ),
    [historicalCandles.length, payloadReference, polledReference],
  );
  const reference = references.display;
  const candleReference = references.candle;

  const normalized = useMemo(
    () => mergeLiveReference(historicalCandles, candleReference),
    [candleReference, historicalCandles],
  );
  const summary = useMemo(() => marketChartSummary(normalized), [normalized]);
  useEffect(() => {
    if (!model || !identity) return;
    onSnapshotRef.current?.({
      identity,
      gpuModel: model.gpu_model,
      gpuVariant: model.gpu_variant,
      range,
      summary,
    });
  }, [identity, model, range, summary]);
  const latestReadout = useMemo(
    () => resolveMarketChartLatestReadout(normalized, reference, comparableLiveMerged),
    [comparableLiveMerged, normalized, reference],
  );
  const bucketSeconds = payload?.bucket_seconds ?? 0;
  const bucketMilliseconds = Math.max(bucketSeconds, 1) * 1000;
  const payloadServerTime = Date.parse(payload?.server_time ?? "");
  const latestHistoricalEnd = Date.parse(normalized.at(-1)?.endTime ?? "");
  const viewportEnd = Number.isFinite(payloadServerTime)
    ? payloadServerTime
    : Number.isFinite(latestHistoricalEnd)
      ? latestHistoricalEnd
      : Date.now();
  const viewportStart = viewportEnd - requestedVisibleCount * bucketMilliseconds;
  const firstVisibleIndex = normalized.findIndex((item) => (
    Date.parse(item.endTime) > viewportStart && item.time < viewportEnd
  ));
  const visibleStartIndex = firstVisibleIndex < 0 ? normalized.length : firstVisibleIndex;
  const visible = normalized.slice(visibleStartIndex).filter((item) => item.time < viewportEnd);
  const times = visible.map((item) => item.time);
  const coverage = useMemo(
    () => marketChartCoverage(
      normalized,
      bucketSeconds,
      range,
      payload?.history_coverage_status ?? payload?.coverage_class ?? payload?.curve_status ?? payload?.history_state,
    ),
    [bucketSeconds, normalized, payload, range],
  );
  const bucketLabel = marketCandleBucketLabel(bucketSeconds);
  const observedRangeLabel = coverage.observedHours >= 48
    ? `${Math.max(1, Math.round(coverage.observedHours / 24))} 天`
    : `${Math.max(1, Math.round(coverage.observedHours))} 小时`;
  const historyLabel = normalized.length <= 1
    ? "当前报价基线"
    : coverage.full
      ? `完整区间 · ${bucketLabel}`
      : coverage.expectedBucketCount > 0
        ? `已覆盖 ${normalized.length}/${coverage.expectedBucketCount} 根 · ${bucketLabel}`
        : `已观测 ${observedRangeLabel}`;
  const quarantineNotice = useMemo(() => marketChartQuarantineNotice(payload), [payload]);
  const hasRenderableData = normalized.length > 0 || reference.price != null;
  const historyPending = Boolean(model && !payload && !historyError);
  const viewState = !model
    ? "empty"
    : !payload && (historyLoading || historyPending)
      ? "loading"
      : hasRenderableData
        ? "chart"
        : "empty";

  useLayoutEffect(() => {
    const chartFrame = chartFrameRef.current;
    if (!chartFrame) return;
    const updateWidth = () => {
      const nextWidth = Math.round(chartFrame.getBoundingClientRect().width || MOBILE_WIDTH);
      setRenderedChartWidth((current) => current === nextWidth ? current : nextWidth);
    };
    updateWidth();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", updateWidth);
      return () => window.removeEventListener("resize", updateWidth);
    }
    const observer = new ResizeObserver(updateWidth);
    observer.observe(chartFrame);
    return () => observer.disconnect();
  }, [viewState]);

  const compactViewport = renderedChartWidth <= 700;
  useLayoutEffect(() => {
    if (zoomSelection.current !== selectionKey) {
      zoomSelection.current = selectionKey;
      zoomTouched.current = false;
    }
    if (zoomTouched.current) return;
    setRequestedVisibleCount(defaultCandleZoomLimit(range, renderedChartWidth, bucketSeconds));
  }, [bucketSeconds, range, renderedChartWidth, selectionKey]);

  useEffect(() => {
    setSelectedRelativeIndex(Math.max(0, visible.length - 1));
    setCursorVisible(false);
  }, [normalized.length, range, requestedVisibleCount, visible.length]);

  const fullAverages = useMemo(() => {
    const closes = normalized.map((item) => item.close);
    const allTimes = normalized.map((item) => item.time);
    return MA_SERIES.map((item) => ({
      ...item,
      // A real price move is still market data, not a missing bucket. Moving
      // averages restart only at an actual time gap.
      values: movingAverageByTime(closes, allTimes, item.period, bucketSeconds),
    }));
  }, [bucketSeconds, normalized]);
  const visibleAverages = fullAverages.map((item) => ({
    ...item,
    values: item.values.slice(visibleStartIndex),
  }));
  const drawableAverages = visibleAverages.filter((item) => item.values.filter((value) => value != null).length >= 2);
  const focusedRelativeIndex = Math.max(0, Math.min(selectedRelativeIndex, Math.max(visible.length - 1, 0)));
  const focused = visible[focusedRelativeIndex];
  const focusedAbsoluteIndex = visibleStartIndex + focusedRelativeIndex;
  const focusedChange = candleChange(focused);
  const layout = chartCanvasLayout(renderedChartWidth);
  const plotWidth = layout.width - layout.plot.left - layout.plot.right;
  const plotHeight = layout.height - layout.plot.top - layout.plot.bottom;
  const geometry = candleTimeGeometry(
    times,
    layout.plot.left,
    plotWidth,
    bucketSeconds,
    viewportStart,
    viewportEnd,
  );
  const x = (index: number) => geometry.centers[index] ?? layout.plot.left + plotWidth / 2;
  const baselineOnly = visible.length === 0;
  // The ten-second quote and stored official OHLC can use different regional
  // populations. With history present, every plotted/readout value comes from
  // OHLC; the independent quote is used only for an empty-chart baseline.
  const latestCandle = visible.at(-1);
  const plotReferencePrice = latestCandle
    ? latestCandle.close
    : baselineOnly
      ? reference.price
      : null;
  const marketValues = visible.flatMap((item) => [item.low, item.high]);
  // MA values and the independently polled display quote never expand the
  // historical y-domain. Both can describe a different population and used
  // to compress otherwise healthy candles into a nearly flat line.
  const domain = paddedPriceDomain(
    marketValues.length ? marketValues : plotReferencePrice != null ? [plotReferencePrice] : [],
  );
  const valueRange = Math.max(domain.max - domain.min, 0.000001);
  const y = (value: number) => layout.plot.top + (1 - (value - domain.min) / valueRange) * plotHeight;
  const bodyWidth = candleBodyWidth(geometry.equivalentSlotCount, plotWidth, compactViewport);
  const points: ChartPoint[] = visible.map((item, index) => ({
    ...item,
    x: x(index),
    openY: y(item.open),
    highY: y(item.high),
    lowY: y(item.low),
    closeY: y(item.close),
  }));
  const referenceValue = latestCandle?.close ?? (normalized.length === 0 ? reference.price : null);
  const latestValue = latestCandle?.close ?? (normalized.length === 0 && baselineOnly ? reference.price : null);
  const displayedLatestValue = latestReadout.price;
  const displayedLatestIsCurrent = latestReadout.isCurrent;
  const latestColor = latestCandle && latestValue != null
    ? latestValue > latestCandle.open ? "var(--kline-rise)" : latestValue < latestCandle.open ? "var(--kline-fall)" : "var(--kline-brand)"
    : "var(--kline-brand)";
  const latestY = latestValue == null ? null : y(latestValue);
  const latestChipY = latestY == null ? null : Math.max(layout.plot.top, Math.min(layout.plot.top + plotHeight - 14, latestY - 7));
  const timeTicks = chartTimeTicks(
    viewportStart,
    viewportEnd,
    compactViewport ? 3 : range === "24h" ? 5 : 7,
  );
  const highIndex = visible.length ? visible.reduce((best, item, index) => item.high > visible[best].high ? index : best, 0) : -1;
  const lowIndex = visible.length ? visible.reduce((best, item, index) => item.low < visible[best].low ? index : best, 0) : -1;
  const activePoint = points[focusedRelativeIndex];
  const activeMaReadout = fullAverages.flatMap((item) => {
    const value = item.values[focusedAbsoluteIndex];
    return value == null ? [] : [{ period: item.period, color: item.color, value }];
  });
  const maximumVisibleCount = coverage.expectedBucketCount || expectedCandleCount(range, bucketSeconds);
  const accessibleReadout = cursorVisible && focused
    ? `${formatDateTime(focused.time)}，开 ${formatPrice(focused.open)}，高 ${formatPrice(focused.high)}，低 ${formatPrice(focused.low)}，收 ${formatPrice(focused.close)}`
    : `${latestReadout.label} ${formatPrice(latestReadout.price)}，${historyLabel}`;

  const selectPoint = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!visible.length) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const index = chartPointerIndex(
      event.clientX,
      rect.left,
      rect.width,
      visible.length,
      layout.width,
      layout.plot.left,
      plotWidth,
      geometry.centers,
    );
    if (index == null) return;
    setSelectedRelativeIndex(index);
    setCursorVisible(true);
  };

  const zoom = (direction: "in" | "out") => {
    const next = nextCandleZoomLimit(
      range,
      requestedVisibleCount,
      maximumVisibleCount,
      direction,
      bucketSeconds,
    );
    if (next === requestedVisibleCount) return false;
    zoomTouched.current = true;
    setRequestedVisibleCount(next);
    return true;
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!visible.length) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const offset = event.key === "ArrowLeft" ? -1 : 1;
      setSelectedRelativeIndex((current) => Math.max(0, Math.min(visible.length - 1, current + offset)));
      setCursorVisible(true);
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoom("in");
    } else if (event.key === "-") {
      event.preventDefault();
      zoom("out");
    }
  };

  const extremeMark = (index: number, value: number, high: boolean) => {
    const center = x(index);
    const vertical = y(value);
    const toRight = center < layout.plot.left + plotWidth * 0.62;
    const lineEnd = center + (toRight ? 10 : -10);
    return <g className={styles.extremeMark} key={`${high ? "high" : "low"}-${index}`}>
      <line x1={center} y1={vertical} x2={lineEnd} y2={vertical}/>
      <text x={lineEnd + (toRight ? 2 : -2)} y={vertical + (high ? -2.5 : 8)} textAnchor={toRight ? "start" : "end"}>
        {formatAxis(value, valueRange)}
      </text>
    </g>;
  };

  return <section className={styles.shell} aria-label={`${model?.gpu_model ?? "GPU"} 算力 K 线`} aria-busy={viewState === "loading"}>
    <nav className={styles.rangeTabs} aria-label="K 线周期">
      {RANGE_OPTIONS.map((option) => <button
        className={range === option.value ? styles.rangeActive : ""}
        type="button"
        aria-pressed={range === option.value}
        onClick={() => {
          if (option.value === range) return;
          if (model && identity) {
            onSnapshotRef.current?.({
              identity,
              gpuModel: model.gpu_model,
              gpuVariant: model.gpu_variant,
              range: option.value,
              summary: null,
            });
          }
          setRange(option.value);
        }}
        key={option.value}
      >{option.label}</button>)}
    </nav>

    {viewState === "loading" && <div className={styles.loading} role="status" aria-live="polite">
      <span className={styles.loadingShort}/><span/><i/>
      <b className={styles.srOnly}>正在读取真实 K 线</b>
    </div>}

    {viewState === "empty" && <div className={styles.empty} role="status">
      <strong>{!model ? "请选择 GPU 型号" : historyError ? "K 线读取失败" : "暂无已核验行情"}</strong>
      <p>{!model ? "选择型号后即可读取对应的真实 OHLC 数据。" : historyError || "该型号当前没有可展示的真实 OHLC 数据。"}</p>
      {model && <button type="button" onClick={() => void refreshHistory(true)}>重新读取</button>}
    </div>}

    {viewState === "chart" && <>
      <p className={styles.srOnly} id={chartStatusId} aria-live="polite" aria-atomic="true">{accessibleReadout}</p>
      <div className={styles.toolbar}>
        <div>
          <p><strong>K线</strong><em>{historyLabel}</em></p>
          <small>卡时 / GPU·小时</small>
        </div>
        <div className={styles.latestReadout}>
          <small>{cursorVisible ? "收" : displayedLatestIsCurrent ? "当前价" : "最新收盘"}</small>
          <strong className={focusedChange == null ? styles.neutral : focusedChange > 0 ? styles.riseText : focusedChange < 0 ? styles.fallText : styles.neutral}>
            {formatPrice(cursorVisible ? focused?.close : displayedLatestValue)}
          </strong>
        </div>
      </div>

      <div className={styles.readout}>
        <div className={styles.readoutHead}>
          <strong>{formatDateTime(focused?.time ?? latestReadout.observedAt)}</strong>
          <span className={focusedChange == null ? styles.neutral : focusedChange > 0 ? styles.riseText : focusedChange < 0 ? styles.fallText : styles.neutral}>
            涨跌幅 {signedPercent(focusedChange)}
          </span>
        </div>
        <div className={styles.ohlcGrid}>
          {focused ? [
            ["开", focused.open, styles.neutral],
            ["高", focused.high, styles.riseText],
            ["低", focused.low, styles.fallText],
            ["收", focused.close, focused.close > focused.open ? styles.riseText : focused.close < focused.open ? styles.fallText : styles.neutral],
          ].map(([label, value, tone]) => <span key={String(label)}><small>{label}</small><strong className={String(tone)}>{formatPrice(Number(value))}</strong></span>)
            : <span><small>{latestReadout.label}</small><strong>{formatPrice(latestReadout.price)}</strong></span>}
        </div>
      </div>

      {activeMaReadout.length > 0 && <div className={styles.maRow} aria-label="移动平均线">
        {activeMaReadout.map((item) => <span style={{ color: item.color }} key={item.period}><strong>MA{item.period}</strong>{formatPrice(item.value)}</span>)}
      </div>}

      {normalized.length > 1 && <div className={styles.viewportToolbar}>
        <div className={styles.viewportControls}>
          <button type="button" disabled={nextCandleZoomLimit(range, requestedVisibleCount, maximumVisibleCount, "out", bucketSeconds) === requestedVisibleCount} onClick={() => zoom("out")} aria-label="缩小 K 线">
            <Minus size={15}/>
          </button>
          <span>视窗 {requestedVisibleCount} 根 · 已有 {visible.length}/{maximumVisibleCount} · {bucketLabel}</span>
          <button type="button" disabled={nextCandleZoomLimit(range, requestedVisibleCount, maximumVisibleCount, "in", bucketSeconds) === requestedVisibleCount} onClick={() => zoom("in")} aria-label="放大 K 线">
            <Plus size={15}/>
          </button>
        </div>
      </div>}

      <div
        className={styles.chartFrame}
        ref={chartFrameRef}
        style={{ aspectRatio: `${layout.width} / ${layout.height}` }}
        role="region"
        tabIndex={0}
        aria-describedby={chartStatusId}
        aria-label={`${model?.gpu_model ?? "GPU"} ${RANGE_OPTIONS.find((item) => item.value === range)?.label}真实 K 线，可使用左右方向键查看，加号和减号缩放`}
        onPointerDown={selectPoint}
        onPointerMove={(event) => { if (event.pointerType === "mouse") selectPoint(event); }}
        onPointerLeave={() => setCursorVisible(false)}
        onKeyDown={handleKeyDown}
      >
        <svg viewBox={`0 0 ${layout.width} ${layout.height}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
          <g className={styles.grid}>
            {Array.from({ length: 5 }, (_, index) => {
              const ratio = index / 4;
              const gridY = layout.plot.top + ratio * plotHeight;
              return <g key={`grid-${index}`}>
                <line x1={layout.plot.left} y1={gridY} x2={layout.plot.left + plotWidth} y2={gridY}/>
                {(latestY == null || Math.abs(gridY - latestY) >= 16) && <text x={layout.plot.left + plotWidth + 4} y={gridY + 3}>{formatAxis(domain.max - ratio * valueRange, valueRange)}</text>}
              </g>;
            })}
            {[1 / 3, 2 / 3].map((ratio) => {
              const gridX = layout.plot.left + ratio * plotWidth;
              return <line className={styles.verticalGrid} x1={gridX} y1={layout.plot.top} x2={gridX} y2={layout.plot.top + plotHeight} key={ratio}/>;
            })}
          </g>

          {latestY != null && latestChipY != null && latestValue != null && <g className={styles.latestLine} style={{ color: latestColor }}>
            <line x1={layout.plot.left} y1={latestY} x2={layout.plot.left + plotWidth} y2={latestY}/>
            <rect x={layout.plot.left + plotWidth + 2} y={latestChipY} width={layout.plot.right - 4} height="14" rx="2.5"/>
            <text x={layout.plot.left + plotWidth + 5} y={latestChipY + 10}>{formatAxis(latestValue, valueRange)}</text>
          </g>}

          {baselineOnly && referenceValue != null
            ? <circle className={styles.singlePoint} cx={layout.plot.left + plotWidth / 2} cy={y(referenceValue)} r="2.5"/>
            : <g className={styles.candles}>{points.map((point) => {
              const rising = point.close > point.open;
              const falling = point.close < point.open;
              const bodyTop = Math.min(point.openY, point.closeY);
              const bodyHeight = Math.abs(point.closeY - point.openY);
              const renderedBodyHeight = Math.max(bodyHeight, 1.3);
              const renderedBodyTop = bodyTop - (renderedBodyHeight - bodyHeight) / 2;
              const tone = rising ? styles.candleRise : falling ? styles.candleFall : styles.candleFlat;
              return <g className={tone} key={point.startTime}>
                <title>{`${formatDateTime(point.time)} 开 ${formatPrice(point.open)} 高 ${formatPrice(point.high)} 低 ${formatPrice(point.low)} 收 ${formatPrice(point.close)}`}</title>
                <line x1={point.x} y1={point.highY} x2={point.x} y2={point.lowY}/>
                {rising || falling
                  ? <rect x={point.x - bodyWidth / 2} y={renderedBodyTop} width={bodyWidth} height={renderedBodyHeight} rx=".4"/>
                  : <line className={styles.flatBody} x1={point.x - bodyWidth / 2} y1={point.openY} x2={point.x + bodyWidth / 2} y2={point.openY}/>}
              </g>;
            })}</g>}

          {!baselineOnly && drawableAverages.map((series) => contiguousValueSegments(series.values, times, bucketSeconds).map((segment, index) => (
            <path
              className={styles.maLine}
              d={linePath(segment.map((entry) => ({ x: x(entry.index), y: y(entry.value) })))}
              style={{ stroke: series.color }}
              key={`${series.period}-${index}`}
            />
          )))}

          {visible.length > 1 && highIndex >= 0 && extremeMark(highIndex, visible[highIndex].high, true)}
          {visible.length > 1 && lowIndex >= 0 && extremeMark(lowIndex, visible[lowIndex].low, false)}

          {cursorVisible && activePoint && <g className={styles.cursor}>
            <line x1={activePoint.x} y1={layout.plot.top} x2={activePoint.x} y2={layout.plot.top + plotHeight}/>
            <line x1={layout.plot.left} y1={activePoint.closeY} x2={layout.plot.left + plotWidth} y2={activePoint.closeY}/>
            <circle cx={activePoint.x} cy={activePoint.closeY} r="2.2"/>
          </g>}

          <g className={styles.timeAxis}>
            {timeTicks.map((tick, labelIndex) => <text
              x={layout.plot.left + (labelIndex / Math.max(timeTicks.length - 1, 1)) * plotWidth}
              y={layout.height - 6}
              textAnchor={labelIndex === 0 ? "start" : labelIndex === timeTicks.length - 1 ? "end" : "middle"}
              key={tick}
            >{formatTimeLabel(tick, range)}</text>)}
          </g>
        </svg>
      </div>

      <footer className={styles.sourceNote}>
        <span>KAI 算力价格历史数据</span>
        <span title={quarantineNotice?.reason ?? undefined}>{quarantineNotice
          ? quarantineNotice.label
          : !coverage.full && coverage.latestEndTime
          ? `历史截至 ${formatDateTime(coverage.latestEndTime)}`
          : !coverage.full
            ? "真实历史仍在积累，缺失时段保留为空白"
            : "按原始报价绘制"}</span>
        <span>{historyLoading
          ? "正在同步"
          : normalized.length > 0 && !comparableLiveMerged
            ? "图内显示最新历史收盘"
            : "当前价每 10 秒检查"}</span>
      </footer>
      {historyError && <p className={styles.staleNotice} role="status">{historyError}，已保留上次成功数据。</p>}
    </>}
  </section>;
}
