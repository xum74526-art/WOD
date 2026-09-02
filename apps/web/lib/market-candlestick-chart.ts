import type { MobileMarketCandle, MobileMarketCandles } from "@/lib/mobile-market-api";

export type MarketChartRange = "24h" | "7d" | "30d" | "90d";

export type MarketChartCandle = {
  startTime: string;
  endTime: string;
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  sampleCount: number;
  observationCount: number;
};

export type MarketChartReference = {
  price: number | null;
  observedAt: string | null;
  comparable: boolean;
};

export type MarketChartReferences = {
  display: MarketChartReference;
  candle: MarketChartReference;
};

export type MarketChartLatestReadout = {
  price: number | null;
  observedAt: string | null;
  label: "当前价" | "最新收盘";
  isCurrent: boolean;
};

export type MarketChartSummary = {
  candleCount: number;
  high: number;
  low: number;
  median: number;
  change: number;
  changePct: number;
};

export type MarketChartSnapshot = {
  identity: string;
  gpuModel: string;
  gpuVariant: string;
  range: MarketChartRange;
  summary: MarketChartSummary | null;
};

export type MarketChartQuarantineNotice = {
  count: number;
  label: string;
  reason: string | null;
};

export type MarketChartLayout = {
  width: number;
  height: number;
  plot: { left: number; right: number; top: number; bottom: number };
};

export type MarketChartCoverage = {
  observedHours: number;
  expectedBucketCount: number;
  ratio: number;
  full: boolean;
  latestEndTime: string | null;
};

const RANGE_DURATION_MS: Record<MarketChartRange, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
  "90d": 90 * 24 * 60 * 60 * 1000,
};

const DEFAULT_BUCKET_SECONDS: Record<MarketChartRange, number> = {
  "24h": 60 * 60,
  "7d": 60 * 60,
  "30d": 4 * 60 * 60,
  "90d": 24 * 60 * 60,
};

const MOBILE_VISIBLE_TARGET: Record<MarketChartRange, number> = {
  "24h": 24,
  "7d": 42,
  "30d": 60,
  "90d": 45,
};

export function chartCanvasLayout(renderedWidth: number): MarketChartLayout {
  const mobileWidth = 360;
  const width = Math.round(Math.max(280, renderedWidth || mobileWidth));
  if (width <= 420) {
    const scale = width / mobileWidth;
    return {
      width,
      height: Math.round(236 * scale),
      plot: {
        left: 4 * scale,
        right: 47 * scale,
        top: 12 * scale,
        bottom: 23 * scale,
      },
    };
  }
  return {
    width,
    height: Math.round(Math.max(270, Math.min(310, width * 0.25))),
    plot: { left: 18, right: 72, top: 14, bottom: 27 },
  };
}

export function marketChartCoverage(
  candles: MarketChartCandle[],
  bucketSeconds: number,
  range: MarketChartRange,
  serverCoverageState?: string | null,
): MarketChartCoverage {
  if (!candles.length) {
    return { observedHours: 0, expectedBucketCount: 0, ratio: 0, full: false, latestEndTime: null };
  }
  const bucketMs = candleBucketMilliseconds(candles.map((item) => item.time), bucketSeconds);
  const durationMs = RANGE_DURATION_MS[range];
  const expectedBucketCount = bucketMs > 0 ? Math.ceil(durationMs / bucketMs) : candles.length;
  const countRatio = expectedBucketCount > 0 ? candles.length / expectedBucketCount : 0;
  const firstTime = candles[0].time;
  const latestEnd = Date.parse(candles.at(-1)!.endTime);
  const spanRatio = Number.isFinite(latestEnd) && latestEnd > firstTime
    ? (latestEnd - firstTime) / durationMs
    : countRatio;
  const ratio = Math.max(0, Math.min(1, countRatio, spanRatio));
  const contiguous = bucketMs > 0 && candles.every((item, index) => (
    index === 0 || item.time - candles[index - 1].time <= bucketMs * 1.05
  ));
  const serverConfirmsFull = ["complete", "full"].includes((serverCoverageState ?? "").toLowerCase());
  const observedHours = bucketMs > 0
    ? candles.length * bucketMs / (60 * 60 * 1000)
    : Math.max(0, (latestEnd - firstTime) / (60 * 60 * 1000));
  return {
    observedHours,
    expectedBucketCount,
    ratio,
    full: serverConfirmsFull && contiguous && countRatio >= 1 && spanRatio >= 1,
    latestEndTime: Number.isFinite(latestEnd) ? new Date(latestEnd).toISOString() : null,
  };
}

export function marketCandleBucketLabel(bucketSeconds: number): string {
  if (!Number.isFinite(bucketSeconds) || bucketSeconds <= 0) return "原始周期";
  if (bucketSeconds % (24 * 60 * 60) === 0) {
    const days = bucketSeconds / (24 * 60 * 60);
    return days === 1 ? "日 K" : `${days} 日 K`;
  }
  if (bucketSeconds % (60 * 60) === 0) return `${bucketSeconds / (60 * 60)} 小时 K`;
  if (bucketSeconds % 60 === 0) return `${bucketSeconds / 60} 分钟 K`;
  return `${Math.round(bucketSeconds)} 秒 K`;
}

export function expectedCandleCount(range: MarketChartRange, bucketSeconds = 0): number {
  const bucket = Math.max(bucketSeconds || DEFAULT_BUCKET_SECONDS[range], 1);
  return Math.max(1, Math.ceil(RANGE_DURATION_MS[range] / (bucket * 1000)));
}

export function movingAverage(values: number[], period: number): Array<number | null> {
  if (!Number.isInteger(period) || period <= 0) return values.map(() => null);
  let running = 0;
  return values.map((value, index) => {
    running += value;
    if (index >= period) running -= values[index - period];
    return index + 1 >= period ? running / period : null;
  });
}

export function movingAverageByTime(
  values: number[],
  times: number[],
  period: number,
  bucketSeconds = 0,
  resetBeforeIndexes: Iterable<number> = [],
): Array<number | null> {
  if (!Number.isInteger(period) || period <= 0) return values.map(() => null);
  const bucket = candleBucketMilliseconds(times, bucketSeconds);
  const resets = new Set(resetBeforeIndexes);
  const window: number[] = [];
  let running = 0;

  return values.map((value, index) => {
    const hasMissingBucket = bucket > 0
      && index > 0
      && times[index] - times[index - 1] > bucket * 1.5;
    if (hasMissingBucket || resets.has(index)) {
      window.length = 0;
      running = 0;
    }
    window.push(value);
    running += value;
    if (window.length > period) running -= window.shift()!;
    return window.length === period ? running / period : null;
  });
}

export function normalizeMarketCandles(input: MobileMarketCandle[]): MarketChartCandle[] {
  const unique = new Map<number, MarketChartCandle>();
  for (const item of input) {
    const time = Date.parse(item.start_time);
    const endTime = Date.parse(item.end_time);
    const open = Number(item.open_price_card_hours);
    const high = Number(item.high_price_card_hours);
    const low = Number(item.low_price_card_hours);
    const close = Number(item.close_price_card_hours);
    if (
      !Number.isFinite(time)
      || !Number.isFinite(endTime)
      || endTime <= time
      || ![open, high, low, close].every((value) => Number.isFinite(value) && value > 0)
      || high < Math.max(open, close)
      || low > Math.min(open, close)
    ) continue;
    unique.set(time, {
      startTime: new Date(time).toISOString(),
      endTime: new Date(endTime).toISOString(),
      time,
      open,
      high,
      low,
      close,
      sampleCount: Math.max(0, Math.trunc(item.sample_count || 0)),
      observationCount: Math.max(0, Math.trunc(item.observation_count || 0)),
    });
  }
  return [...unique.values()].sort((a, b) => a.time - b.time);
}

export function marketChartSummary(candles: MarketChartCandle[]): MarketChartSummary | null {
  if (!candles.length) return null;
  const first = candles[0];
  const latest = candles.at(-1)!;
  const closes = candles.map((item) => item.close).sort((left, right) => left - right);
  const middle = Math.floor(closes.length / 2);
  const median = closes.length % 2
    ? closes[middle]
    : (closes[middle - 1] + closes[middle]) / 2;
  const change = latest.close - first.open;
  return {
    candleCount: candles.length,
    high: Math.max(...candles.map((item) => item.high)),
    low: Math.min(...candles.map((item) => item.low)),
    median,
    change,
    changePct: first.open ? (change / first.open) * 100 : 0,
  };
}

export function matchesMarketCandleSelection(
  payload: Pick<MobileMarketCandles, "gpu_model" | "gpu_variant" | "range">,
  gpuModel: string,
  gpuVariant: string,
  range: MarketChartRange,
): boolean {
  return payload.gpu_model === gpuModel
    && payload.gpu_variant === gpuVariant
    && payload.range === range;
}

export function canMergeLiveReference(
  candles: MarketChartCandle[],
  reference: MarketChartReference,
): boolean {
  if (
    !candles.length
    || !reference.comparable
    || reference.price == null
    || !Number.isFinite(reference.price)
    || reference.price <= 0
  ) return false;
  const observedAt = reference.observedAt ? Date.parse(reference.observedAt) : Number.NaN;
  const latest = candles.at(-1)!;
  const latestEnd = Date.parse(latest.endTime);
  return Number.isFinite(observedAt)
    && Number.isFinite(latestEnd)
    && observedAt >= latest.time
    && observedAt < latestEnd;
}

export function mergeLiveReference(
  candles: MarketChartCandle[],
  reference: MarketChartReference,
): MarketChartCandle[] {
  if (!canMergeLiveReference(candles, reference)) return candles;
  const livePrice = reference.price;
  if (livePrice == null) return candles;
  const latest = candles.at(-1)!;
  const merged = [...candles];
  merged[merged.length - 1] = {
    ...latest,
    close: livePrice,
    high: Math.max(latest.high, livePrice),
    low: Math.min(latest.low, livePrice),
  };
  return merged;
}

export function resolveMarketChartReferences(
  payloadReference: MarketChartReference,
  polledReference: MarketChartReference,
  hasHistoricalCandles = false,
): MarketChartReferences {
  const emptyReference: MarketChartReference = {
    price: null,
    observedAt: null,
    comparable: false,
  };
  return {
    // An independently polled offer-pool median is useful as a baseline only
    // when no historical index exists. Once OHLC exists, the chart readout may
    // use only its own explicitly comparable payload reference; otherwise the
    // last historical close remains the chart's latest value.
    display: hasHistoricalCandles
      ? payloadReference.comparable && payloadReference.price != null
        ? payloadReference
        : emptyReference
      : polledReference.price != null
        ? polledReference
        : payloadReference,
    // The independently polled endpoint does not expose the provider and
    // aggregation scope required to prove comparability with stored OHLC.
    // Only the candle payload's own reference may update an open candle.
    candle: payloadReference,
  };
}

export function resolveMarketChartLatestReadout(
  candles: MarketChartCandle[],
  baselineReference: MarketChartReference,
  comparableLiveMerged: boolean,
): MarketChartLatestReadout {
  const latest = candles.at(-1);
  if (latest) {
    return {
      price: latest.close,
      observedAt: latest.endTime,
      label: comparableLiveMerged ? "当前价" : "最新收盘",
      isCurrent: comparableLiveMerged,
    };
  }
  const price = baselineReference.price != null
    && Number.isFinite(baselineReference.price)
    && baselineReference.price > 0
    ? baselineReference.price
    : null;
  return {
    price,
    observedAt: price == null ? null : baselineReference.observedAt,
    label: "当前价",
    isCurrent: price != null,
  };
}

export function marketChartQuarantineNotice(
  payload: Pick<MobileMarketCandles,
    | "quarantined_candle_count"
    | "quarantined_prefix_count"
    | "quarantined_tail_count"
    | "quarantine_reason"
  > | null | undefined,
): MarketChartQuarantineNotice | null {
  const safeCount = (value: number | null | undefined) => (
    Number.isFinite(value) ? Math.max(0, Math.trunc(value ?? 0)) : 0
  );
  const prefixCount = safeCount(payload?.quarantined_prefix_count);
  const tailCount = safeCount(payload?.quarantined_tail_count);
  const count = Math.max(safeCount(payload?.quarantined_candle_count), prefixCount + tailCount);
  if (count <= 0) return null;
  const reasonCode = payload?.quarantine_reason?.trim() || null;
  const reason = reasonCode === "superseded_partial_edge_batch"
    ? "该报价来自较早且未完成的上游批次"
    : null;
  return {
    count,
    label: `已隔离 ${count} 根旧批次异常报价`,
    reason,
  };
}

export function candleSlotCenter(index: number, count: number, left: number, plotWidth: number): number {
  if (count <= 0) return left + plotWidth / 2;
  return left + ((Math.max(0, Math.min(index, count - 1)) + 0.5) / count) * plotWidth;
}

export function candleBucketMilliseconds(times: number[], bucketSeconds = 0): number {
  if (bucketSeconds > 0) return bucketSeconds * 1000;
  const gaps = times.slice(1)
    .map((value, index) => value - times[index])
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((a, b) => a - b);
  if (!gaps.length) return 0;
  // Use the lower median. With a sparse pair such as [1 minute, 1 day], the
  // larger gap is missing history, not evidence of a twelve-hour candle.
  return gaps[Math.floor((gaps.length - 1) / 2)];
}

export function significantPriceJumpIndexes(
  candles: MarketChartCandle[],
  minimumChange = 0.05,
): number[] {
  const indexes: number[] = [];
  for (let index = 1; index < candles.length; index += 1) {
    const previous = candles[index - 1];
    const current = candles[index];
    if (previous.close <= 0 || current.open <= 0) continue;
    const openGapChange = Math.abs(current.open - previous.close) / previous.close;
    const closeChange = Math.abs(current.close - previous.close) / previous.close;
    const bodyChange = Math.abs(current.close - current.open) / current.open;
    // A repricing can arrive as either a full candle move or a gap between two
    // adjacent official buckets. Segment the MA at both boundaries so the line
    // never implies a price path which was not observed.
    if (openGapChange >= minimumChange || (closeChange >= minimumChange && bodyChange >= minimumChange)) {
      indexes.push(index);
    }
  }
  return indexes;
}

export function candleTimeGeometry(
  times: number[],
  left: number,
  plotWidth: number,
  bucketSeconds = 0,
  viewportStart?: number,
  viewportEnd?: number,
): { centers: number[]; equivalentSlotCount: number } {
  if (!times.length) return { centers: [], equivalentSlotCount: 1 };
  const bucket = candleBucketMilliseconds(times, bucketSeconds);
  const hasFixedViewport = Number.isFinite(viewportStart)
    && Number.isFinite(viewportEnd)
    && Number(viewportEnd) > Number(viewportStart)
    && bucket > 0;
  if (hasFixedViewport) {
    const start = Number(viewportStart);
    const end = Number(viewportEnd);
    const span = end - start;
    return {
      centers: times.map((value) => left + ((value - start + bucket / 2) / span) * plotWidth),
      equivalentSlotCount: Math.max(1, span / bucket),
    };
  }
  if (times.length === 1) return { centers: [left + plotWidth / 2], equivalentSlotCount: 1 };
  const gaps = times.slice(1).map((value, index) => value - times[index]).filter((value) => value > 0);
  if (!gaps.length) {
    return {
      centers: times.map((_, index) => candleSlotCenter(index, times.length, left, plotWidth)),
      equivalentSlotCount: times.length,
    };
  }
  const first = times[0];
  const span = Math.max(times.at(-1)! - first + bucket, bucket);
  return {
    centers: times.map((value) => left + ((value - first + bucket / 2) / span) * plotWidth),
    equivalentSlotCount: Math.max(times.length, span / bucket),
  };
}

export function chartTimeTicks(start: number, end: number, maximumLabels: number): number[] {
  if (
    !Number.isFinite(start)
    || !Number.isFinite(end)
    || end <= start
    || !Number.isInteger(maximumLabels)
    || maximumLabels <= 0
  ) return [];
  const count = Math.max(2, maximumLabels);
  return Array.from({ length: count }, (_, index) => (
    start + ((end - start) * index) / (count - 1)
  ));
}

export function candleBodyWidth(count: number, plotWidth: number, compact = false): number {
  const slotWidth = plotWidth / Math.max(count, 1);
  const maximum = compact ? 8 : 16;
  const ratio = compact ? 0.48 : 0.56;
  // Dense mobile ranges can contain 168 or 180 genuine buckets. Never apply
  // a fixed minimum that makes adjacent candle bodies overlap their slots.
  const preferred = Math.max(0.35, Math.min(maximum, slotWidth * ratio));
  return Math.min(preferred, slotWidth * 0.82);
}

export function chartLabelIndexes(count: number, maximumLabels: number): number[] {
  if (!Number.isInteger(count) || count <= 0 || !Number.isInteger(maximumLabels) || maximumLabels <= 0) return [];
  const labelCount = Math.min(count, maximumLabels);
  if (labelCount === 1) return [0];
  return [...new Set(Array.from({ length: labelCount }, (_, index) => (
    Math.round((index / (labelCount - 1)) * (count - 1))
  )))];
}

export function chartPointerIndex(
  clientX: number,
  rectLeft: number,
  rectWidth: number,
  candleCount: number,
  viewBoxWidth: number,
  plotLeft: number,
  plotWidth: number,
  candleCenters: number[] = [],
): number | null {
  if (!Number.isFinite(clientX) || !Number.isFinite(rectLeft) || rectWidth <= 0 || candleCount <= 0) return null;
  const localX = ((clientX - rectLeft) / rectWidth) * viewBoxWidth;
  if (localX < plotLeft || localX > plotLeft + plotWidth) return null;
  if (candleCenters.length === candleCount) {
    return candleCenters.reduce((best, value, index) => (
      Math.abs(value - localX) < Math.abs(candleCenters[best] - localX) ? index : best
    ), 0);
  }
  if (candleCount === 1) return 0;
  const ratio = Math.max(0, Math.min(0.999999, (localX - plotLeft) / plotWidth));
  return Math.max(0, Math.min(candleCount - 1, Math.floor(ratio * candleCount)));
}

export function paddedPriceDomain(values: number[]): { min: number; max: number } {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return { min: 0, max: 1 };
  const rawMin = Math.min(...finite);
  const rawMax = Math.max(...finite);
  const span = rawMax - rawMin;
  const scale = Math.max(Math.abs(rawMin), Math.abs(rawMax), 1);
  // A nearly flat market should not suddenly occupy the whole canvas merely
  // because its span changed from exactly zero to one last decimal place.
  // Keep a continuous minimum 0.3% price window, then add normal chart air.
  const effectiveSpan = Math.max(span, scale * 0.003, 0.01);
  const extra = (effectiveSpan - span) / 2;
  const padding = effectiveSpan * 0.12;
  return {
    min: Math.max(0, rawMin - extra - padding),
    max: rawMax + extra + padding,
  };
}

export type MarketLineSegment = Array<{ index: number; value: number }>;

export function contiguousValueSegments(
  values: Array<number | null>,
  times: number[],
  bucketSeconds = 0,
): MarketLineSegment[] {
  const bucket = candleBucketMilliseconds(times, bucketSeconds);
  const segments: MarketLineSegment[] = [];
  let current: MarketLineSegment = [];
  values.forEach((value, index) => {
    const hasGap = bucket > 0 && index > 0 && times[index] - times[index - 1] > bucket * 1.5;
    if (value == null || !Number.isFinite(value) || hasGap) {
      if (current.length > 1) segments.push(current);
      current = [];
      if (value == null || !Number.isFinite(value)) return;
    }
    current.push({ index, value });
  });
  if (current.length > 1) segments.push(current);
  return segments;
}

const CANDLE_ZOOM_FRACTIONS: Record<MarketChartRange, number[]> = {
  "24h": [0.5, 0.75, 1],
  "7d": [0.25, 0.5, 0.75, 1],
  "30d": [1 / 6, 1 / 3, 0.5, 2 / 3, 1],
  "90d": [1 / 6, 1 / 3, 0.5, 2 / 3, 1],
};

function candleZoomSteps(range: MarketChartRange, available: number): number[] {
  if (available <= 1) return [Math.max(0, available)];
  return [...new Set(CANDLE_ZOOM_FRACTIONS[range]
    .map((fraction) => Math.max(2, Math.min(available, Math.round(available * fraction))))
    .concat(available))]
    .sort((a, b) => a - b);
}

export function defaultCandleZoomLimit(
  range: MarketChartRange,
  renderedWidth = Number.POSITIVE_INFINITY,
  bucketSeconds = 0,
): number {
  const available = expectedCandleCount(range, bucketSeconds);
  if (renderedWidth <= 420) return Math.min(available, MOBILE_VISIBLE_TARGET[range]);
  if (renderedWidth <= 700) return Math.min(available, Math.max(MOBILE_VISIBLE_TARGET[range], Math.round(available / 2)));
  return available;
}

export function nextCandleZoomLimit(
  range: MarketChartRange,
  currentVisible: number,
  total: number,
  direction: "in" | "out",
  bucketSeconds = 0,
): number {
  const available = Math.max(0, Math.min(Math.floor(total), expectedCandleCount(range, bucketSeconds)));
  if (available <= 1) return available;
  const steps = candleZoomSteps(range, available);
  const current = Math.max(1, Math.min(Math.floor(currentVisible), available));
  if (direction === "in") {
    const next = [...steps].reverse().find((value) => value < current);
    return Math.min(next ?? current, available);
  }
  const next = steps.find((value) => value > current);
  return Math.min(next ?? available, available);
}
