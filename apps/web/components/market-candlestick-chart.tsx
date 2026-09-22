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
import { formatFinancialAmount } from "@/lib/financial-format";
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
import { useI18n } from "./locale-root";
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
const RANGE_OPTIONS: Array<{ value: MarketChartRange }> = [
  { value: "7d" },
  { value: "30d" },
  { value: "90d" },
];
const LATEST_REFRESH_MS = 300_000;
const HISTORY_REFRESH_MS: Record<MarketChartRange, number> = {
  "24h": 300_000,
  "7d": 300_000,
  "30d": 300_000,
  "90d": 300_000,
};
const MA_SERIES = [
  { period: 5, color: "var(--kline-ma-5)" },
  { period: 10, color: "var(--kline-ma-10)" },
  { period: 20, color: "var(--kline-ma-20)" },
] as const;

type Translate = (key: string, fallback: string, values?: Record<string, string | number>) => string;

function modelIdentity(model: MobileMarketModel | null) {
  return model ? `${model.gpu_model}|${model.gpu_variant}` : "";
}

function formatPrice(value: number | null | undefined, dateLocale: string) {
  if (value == null || !Number.isFinite(value)) return "--";
  return formatFinancialAmount(value, dateLocale, false);
}

function formatAxis(value: number, span: number, dateLocale: string) {
  void span;
  return formatFinancialAmount(value, dateLocale, false);
}

function formatInteger(value: number, dateLocale: string) {
  return value.toLocaleString(dateLocale, { maximumFractionDigits: 0 });
}

function formatDateTime(value: number | string | null | undefined, dateLocale: string, currentQuoteLabel: string) {
  const timestamp = typeof value === "number" ? value : value ? Date.parse(value) : Number.NaN;
  if (!Number.isFinite(timestamp)) return currentQuoteLabel;
  return new Date(timestamp).toLocaleString(dateLocale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatTimeLabel(time: number, range: MarketChartRange, dateLocale: string) {
  return new Date(time).toLocaleString(dateLocale, {
    month: "2-digit",
    day: "2-digit",
    ...(range === "24h" ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  });
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

function signedPercent(value: number | null, dateLocale: string) {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${value > 0 ? "+" : ""}${value.toLocaleString(dateLocale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: false,
  })}%`;
}

function rangeLabel(range: MarketChartRange, t: Translate) {
  if (range === "24h") return t("trends.chartRange.24Hours", "24小时");
  if (range === "7d") return t("trends.chartRange.7Days", "7天");
  if (range === "30d") return t("trends.chartRange.30Days", "30天");
  return t("trends.chartRange.90Days", "90天");
}

function bucketPeriodLabel(bucketSeconds: number, t: Translate, dateLocale: string) {
  if (!Number.isFinite(bucketSeconds) || bucketSeconds <= 0) {
    return t("trends.candles.bucket.raw", "原始周期");
  }
  if (bucketSeconds % (24 * 60 * 60) === 0) {
    const days = bucketSeconds / (24 * 60 * 60);
    return days === 1
      ? t("trends.candles.bucket.daily", "日 K")
      : t("trends.candles.bucket.days", "{count} 日 K", { count: formatInteger(days, dateLocale) });
  }
  if (bucketSeconds % (60 * 60) === 0) {
    return t("trends.candles.bucket.hours", "{count} 小时 K", {
      count: formatInteger(bucketSeconds / (60 * 60), dateLocale),
    });
  }
  if (bucketSeconds % 60 === 0) {
    return t("trends.candles.bucket.minutes", "{count} 分钟 K", {
      count: formatInteger(bucketSeconds / 60, dateLocale),
    });
  }
  return t("trends.candles.bucket.seconds", "{count} 秒 K", {
    count: formatInteger(Math.round(bucketSeconds), dateLocale),
  });
}

function linePath(points: Array<{ x: number; y: number }>) {
  return points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}

export function MarketCandlestickChart({ model, initialLatest = null, onLatest, onSnapshot }: MarketCandlestickChartProps) {
  const { t, dateLocale } = useI18n();
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

  // The independently polled endpoint owns the current publication quote,
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
  const bucketLabel = bucketPeriodLabel(bucketSeconds, t, dateLocale);
  const observedRangeLabel = coverage.observedHours >= 48
    ? t("trends.candles.observedDays", "{count} 天", {
      count: formatInteger(Math.max(1, Math.round(coverage.observedHours / 24)), dateLocale),
    })
    : t("trends.candles.observedHours", "{count} 小时", {
      count: formatInteger(Math.max(1, Math.round(coverage.observedHours)), dateLocale),
    });
  const historyLabel = normalized.length <= 1
    ? t("trends.candles.history.baseline", "当前报价基线")
    : coverage.full
      ? t("trends.candles.history.complete", "完整区间 · {bucket}", { bucket: bucketLabel })
      : coverage.expectedBucketCount > 0
        ? t("trends.candles.history.coverage", "已覆盖 {current}/{expected} 根 · {bucket}", {
          current: formatInteger(normalized.length, dateLocale),
          expected: formatInteger(coverage.expectedBucketCount, dateLocale),
          bucket: bucketLabel,
        })
        : t("trends.candles.history.observed", "已观测 {range}", { range: observedRangeLabel });
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
  const currentQuoteLabel = t("trends.candles.currentQuote", "当前报价");
  const latestReadoutLabel = latestReadout.label === "当前价"
    ? t("trends.candles.currentPrice", "当前价")
    : t("trends.candles.latestClose", "最新收盘");
  const accessibleReadout = cursorVisible && focused
    ? t("trends.candles.accessibility.ohlc", "{date}，开 {open}，高 {high}，低 {low}，收 {close}", {
      date: formatDateTime(focused.time, dateLocale, currentQuoteLabel),
      open: formatPrice(focused.open, dateLocale),
      high: formatPrice(focused.high, dateLocale),
      low: formatPrice(focused.low, dateLocale),
      close: formatPrice(focused.close, dateLocale),
    })
    : t("trends.candles.accessibility.summary", "{label} {price}，{history}", {
      label: latestReadoutLabel,
      price: formatPrice(latestReadout.price, dateLocale),
      history: historyLabel,
    });

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
        {formatAxis(value, valueRange, dateLocale)}
      </text>
    </g>;
  };

  const historyErrorMessage = t("trends.candles.state.errorDescription", "暂时无法读取真实 K 线，请稍后重试。");
  const quarantineLabel = quarantineNotice
    ? t("trends.candles.quarantine.label", quarantineNotice.label, {
      count: formatInteger(quarantineNotice.count, dateLocale),
    })
    : null;
  const quarantineReason = quarantineNotice?.reason
    ? t("trends.candles.quarantine.reason", quarantineNotice.reason)
    : undefined;
  const selectedRangeLabel = rangeLabel(range, t);

  return <section className={styles.shell} aria-label={t("trends.candles.sectionAria", "{model} 算力 K 线", { model: model?.gpu_model ?? "GPU" })} aria-busy={viewState === "loading"}>
    <nav className={styles.rangeTabs} aria-label={t("trends.candles.rangeAria", "K 线周期")}>
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
      >{rangeLabel(option.value, t)}</button>)}
    </nav>

    {viewState === "loading" && <div className={styles.loading} role="status" aria-live="polite">
      <span className={styles.loadingShort}/><span/><i/>
      <b className={styles.srOnly}>{t("trends.candles.state.loading", "正在读取真实 K 线")}</b>
    </div>}

    {viewState === "empty" && <div className={styles.empty} role="status">
      <strong>{!model
        ? t("trends.candles.state.selectModel", "请选择 GPU 型号")
        : historyError
          ? t("trends.candles.state.error", "K 线读取失败")
          : t("trends.candles.state.empty", "暂无已核验行情")}</strong>
      <p>{!model
        ? t("trends.candles.state.selectModelDescription", "选择型号后即可读取对应的真实 OHLC 数据。")
        : historyError
          ? historyErrorMessage
          : t("trends.candles.state.emptyDescription", "该型号当前没有可展示的真实 OHLC 数据。")}</p>
      {model && <button type="button" onClick={() => void refreshHistory(true)}>{t("trends.candles.state.retry", "重新读取")}</button>}
    </div>}

    {viewState === "chart" && <>
      <p className={styles.srOnly} id={chartStatusId} aria-live="polite" aria-atomic="true">{accessibleReadout}</p>
      <div className={styles.toolbar}>
        <div>
          <p><strong>{t("trends.candles.title", "K线")}</strong><em>{historyLabel}</em></p>
          <small>{t("trends.candles.unit", "卡时 / GPU·小时")}</small>
        </div>
        <div className={styles.latestReadout}>
          <small>{cursorVisible
            ? t("trends.candles.ohlc.close", "收")
            : displayedLatestIsCurrent
              ? t("trends.candles.currentPrice", "当前价")
              : t("trends.candles.latestClose", "最新收盘")}</small>
          <strong className={focusedChange == null ? styles.neutral : focusedChange > 0 ? styles.riseText : focusedChange < 0 ? styles.fallText : styles.neutral}>
            {formatPrice(cursorVisible ? focused?.close : displayedLatestValue, dateLocale)}
          </strong>
        </div>
      </div>

      <div className={styles.readout}>
        <div className={styles.readoutHead}>
          <strong>{formatDateTime(focused?.time ?? latestReadout.observedAt, dateLocale, currentQuoteLabel)}</strong>
          <span className={focusedChange == null ? styles.neutral : focusedChange > 0 ? styles.riseText : focusedChange < 0 ? styles.fallText : styles.neutral}>
            {t("trends.candles.change", "涨跌幅 {value}", { value: signedPercent(focusedChange, dateLocale) })}
          </span>
        </div>
        <div className={styles.ohlcGrid}>
          {focused ? [
            [t("trends.candles.ohlc.open", "开"), focused.open, styles.neutral],
            [t("trends.candles.ohlc.high", "高"), focused.high, styles.riseText],
            [t("trends.candles.ohlc.low", "低"), focused.low, styles.fallText],
            [t("trends.candles.ohlc.close", "收"), focused.close, focused.close > focused.open ? styles.riseText : focused.close < focused.open ? styles.fallText : styles.neutral],
          ].map(([label, value, tone]) => <span key={String(label)}><small>{label}</small><strong className={String(tone)}>{formatPrice(Number(value), dateLocale)}</strong></span>)
            : <span><small>{latestReadoutLabel}</small><strong>{formatPrice(latestReadout.price, dateLocale)}</strong></span>}
        </div>
      </div>

      {activeMaReadout.length > 0 && <div className={styles.maRow} aria-label={t("trends.candles.maAria", "移动平均线")}>
        {activeMaReadout.map((item) => <span style={{ color: item.color }} key={item.period}><strong>MA{item.period}</strong>{formatPrice(item.value, dateLocale)}</span>)}
      </div>}

      {normalized.length > 1 && <div className={styles.viewportToolbar}>
        <div className={styles.viewportControls}>
          <button type="button" disabled={nextCandleZoomLimit(range, requestedVisibleCount, maximumVisibleCount, "out", bucketSeconds) === requestedVisibleCount} onClick={() => zoom("out")} aria-label={t("trends.candles.zoomOut", "缩小 K 线")}>
            <Minus size={15}/>
          </button>
          <span>{t("trends.candles.viewport", "视窗 {visible} 根 · 已有 {current}/{total} · {bucket}", {
            visible: formatInteger(requestedVisibleCount, dateLocale),
            current: formatInteger(visible.length, dateLocale),
            total: formatInteger(maximumVisibleCount, dateLocale),
            bucket: bucketLabel,
          })}</span>
          <button type="button" disabled={nextCandleZoomLimit(range, requestedVisibleCount, maximumVisibleCount, "in", bucketSeconds) === requestedVisibleCount} onClick={() => zoom("in")} aria-label={t("trends.candles.zoomIn", "放大 K 线")}>
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
        aria-label={t("trends.candles.chartAria", "{model} {range}真实 K 线，可使用左右方向键查看，加号和减号缩放", {
          model: model?.gpu_model ?? "GPU",
          range: selectedRangeLabel,
        })}
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
                {(latestY == null || Math.abs(gridY - latestY) >= 16) && <text x={layout.plot.left + plotWidth + 4} y={gridY + 3}>{formatAxis(domain.max - ratio * valueRange, valueRange, dateLocale)}</text>}
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
            <text x={layout.plot.left + plotWidth + 5} y={latestChipY + 10}>{formatAxis(latestValue, valueRange, dateLocale)}</text>
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
                <title>{t("trends.candles.accessibility.ohlc", "{date}，开 {open}，高 {high}，低 {low}，收 {close}", {
                  date: formatDateTime(point.time, dateLocale, currentQuoteLabel),
                  open: formatPrice(point.open, dateLocale),
                  high: formatPrice(point.high, dateLocale),
                  low: formatPrice(point.low, dateLocale),
                  close: formatPrice(point.close, dateLocale),
                })}</title>
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
            >{formatTimeLabel(tick, range, dateLocale)}</text>)}
          </g>
        </svg>
      </div>

      <footer className={styles.sourceNote}>
        <span>{t("trends.candles.source", "KAI 算力价格历史数据")}</span>
        <span title={quarantineReason}>{quarantineNotice
          ? quarantineLabel
          : !coverage.full && coverage.latestEndTime
          ? t("trends.candles.historyUntil", "历史截至 {date}", {
            date: formatDateTime(coverage.latestEndTime, dateLocale, currentQuoteLabel),
          })
          : !coverage.full
            ? t("trends.candles.historyAccumulating", "真实历史仍在积累，缺失时段保留为空白")
            : t("trends.candles.rawQuotes", "按原始报价绘制")}</span>
        <span>{historyLoading
          ? t("trends.candles.syncing", "正在同步")
          : normalized.length > 0 && !comparableLiveMerged
            ? t("trends.candles.latestHistoricalClose", "图内显示最新历史收盘")
            : t("trends.candles.liveRefresh", "当前价每 {seconds} 秒检查", { seconds: formatInteger(10, dateLocale) })}</span>
      </footer>
      {historyError && <p className={styles.staleNotice} role="status">{t("trends.candles.stale", "{error} 已保留上次成功数据。", { error: historyErrorMessage })}</p>}
    </>}
  </section>;
}
