import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import {
  canMergeLiveReference,
  candleBucketMilliseconds,
  candleBodyWidth,
  candleTimeGeometry,
  chartCanvasLayout,
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
  significantPriceJumpIndexes,
  type MarketChartCandle,
} from "../lib/market-candlestick-chart.ts";
import type { MobileMarketCandle } from "../lib/mobile-market-api.ts";

function candle(start: string, open: number, high: number, low: number, close: number): MobileMarketCandle {
  return {
    start_time: start,
    end_time: new Date(Date.parse(start) + 60_000).toISOString(),
    open_price_cny: open * 4,
    high_price_cny: high * 4,
    low_price_cny: low * 4,
    close_price_cny: close * 4,
    open_price_card_hours: open,
    high_price_card_hours: high,
    low_price_card_hours: low,
    close_price_card_hours: close,
    sample_count: 2,
    observation_count: 3,
    sources: ["kai"],
  };
}

test("Web chart normalizes only valid real card-hour OHLC rows", () => {
  const normalized = normalizeMarketCandles([
    candle("2026-08-29T01:01:00.000Z", 10, 12, 9, 11),
    candle("2026-08-29T01:00:00.000Z", 9, 11, 8, 10),
    candle("2026-08-29T01:02:00.000Z", 11, 10, 9, 10),
    candle("2026-08-29T01:03:00.000Z", 0, 0, 0, 0),
    candle("2026-08-29T02:00:00.000+01:00", 10, 13, 9, 12),
  ]);

  assert.deepEqual(normalized.map((item) => item.startTime), [
    "2026-08-29T01:00:00.000Z",
    "2026-08-29T01:01:00.000Z",
  ]);
  assert.equal(normalized[0].close, 12);
  assert.equal(normalized[0].sampleCount, 2);
});

test("chart summary is calculated from the same normalized OHLC payload", () => {
  const rows = normalizeMarketCandles([
    candle("2026-08-29T01:00:00.000Z", 10, 13, 9, 12),
    candle("2026-08-29T01:01:00.000Z", 12, 15, 11, 14),
    candle("2026-08-29T01:02:00.000Z", 14, 14, 10, 11),
  ]);

  assert.deepEqual(marketChartSummary(rows), {
    candleCount: 3,
    high: 15,
    low: 9,
    median: 12,
    change: 1,
    changePct: 10,
  });
  assert.equal(marketChartSummary([]), null);
});

test("candle response identity must match model, variant, and range exactly", () => {
  const response = { gpu_model: "H100", gpu_variant: "80GB", range: "7d" };

  assert.equal(matchesMarketCandleSelection(response, "H100", "80GB", "7d"), true);
  assert.equal(matchesMarketCandleSelection(response, "H200", "80GB", "7d"), false);
  assert.equal(matchesMarketCandleSelection(response, "H100", "94GB", "7d"), false);
  assert.equal(matchesMarketCandleSelection(response, "H100", "80GB", "30d"), false);
  assert.equal(matchesMarketCandleSelection(
    { gpu_model: "H100", gpu_variant: "80GB", range: "90d" },
    "H100",
    "80GB",
    "90d",
  ), true);
});

test("Web chart keeps real missing buckets and breaks moving-average segments at gaps", () => {
  const minute = 60_000;
  const times = [0, minute, minute * 4];
  const geometry = candleTimeGeometry(times, 4, 309, 60);
  const segments = contiguousValueSegments([10, 11, 12], times, 60);

  assert.equal(geometry.equivalentSlotCount, 5);
  assert.ok(geometry.centers[2] - geometry.centers[1] > geometry.centers[1] - geometry.centers[0]);
  assert.deepEqual(segments, [[
    { index: 0, value: 10 },
    { index: 1, value: 11 },
  ]]);
  assert.equal(candleBodyWidth(geometry.equivalentSlotCount, 309), 16);
});

test("partial histories keep their real position inside a fixed time viewport", () => {
  const hour = 60 * 60 * 1000;
  const viewportStart = Date.parse("2026-09-01T00:00:00.000Z");
  const viewportEnd = viewportStart + 24 * hour;
  const times = [viewportStart + 20 * hour, viewportStart + 21 * hour, viewportStart + 23 * hour];
  const geometry = candleTimeGeometry(times, 0, 240, 3600, viewportStart, viewportEnd);

  assert.equal(geometry.equivalentSlotCount, 24);
  assert.ok(geometry.centers[0] > 190);
  assert.ok(geometry.centers[2] > geometry.centers[1]);
  assert.deepEqual(chartTimeTicks(viewportStart, viewportEnd, 3), [
    viewportStart,
    viewportStart + 12 * hour,
    viewportEnd,
  ]);
});

test("desktop chart fills the market frame with a compact wide canvas", () => {
  const mobile = chartCanvasLayout(360);
  const desktop = chartCanvasLayout(1280);
  const wideDesktop = chartCanvasLayout(1600);

  assert.deepEqual({ width: mobile.width, height: mobile.height }, { width: 360, height: 236 });
  assert.deepEqual({ width: desktop.width, height: desktop.height }, { width: 1280, height: 310 });
  assert.deepEqual({ width: wideDesktop.width, height: wideDesktop.height }, { width: 1600, height: 310 });
  assert.equal(candleBodyWidth(24, desktop.width - desktop.plot.left - desktop.plot.right), 16);
  assert.equal(candleBodyWidth(24, 320, true), 6.4);
  const denseSlot = 309 / 180;
  assert.ok(candleBodyWidth(180, 309, true) < denseSlot);
  const ultraDenseSlot = 240 / 360;
  assert.ok(candleBodyWidth(360, 240, true) < ultraDenseSlot);
});

test("24-hour coverage is derived from real candle buckets instead of trusting an optimistic status", () => {
  const rows: MarketChartCandle[] = Array.from({ length: 15 }, (_, index) => {
    const time = Date.parse("2026-08-31T02:00:00.000Z") + index * 60 * 60 * 1000;
    return {
      startTime: new Date(time).toISOString(),
      endTime: new Date(time + 60 * 60 * 1000).toISOString(),
      time,
      open: 26.8,
      high: 26.9,
      low: 26.7,
      close: 26.85,
      sampleCount: 2,
      observationCount: 2,
    };
  });
  const coverage = marketChartCoverage(rows, 3600, "24h");

  assert.equal(coverage.observedHours, 15);
  assert.equal(coverage.expectedBucketCount, 24);
  assert.equal(coverage.ratio, 15 / 24);
  assert.equal(coverage.full, false);
});

test("high-density seven, thirty, and ninety day ranges keep their native real bucket counts", () => {
  const series = (count: number, bucketSeconds: number): MarketChartCandle[] => Array.from(
    { length: count },
    (_, index) => {
      const time = Date.parse("2026-07-01T00:00:00.000Z") + index * bucketSeconds * 1000;
      return {
        startTime: new Date(time).toISOString(),
        endTime: new Date(time + bucketSeconds * 1000).toISOString(),
        time,
        open: 26.8,
        high: 26.9,
        low: 26.7,
        close: 26.85,
        sampleCount: 2,
        observationCount: 2,
      };
    },
  );

  const sevenDays = marketChartCoverage(series(168, 3600), 3600, "7d", "complete");
  const thirtyDays = marketChartCoverage(series(180, 4 * 3600), 4 * 3600, "30d", "complete");
  const ninetyDays = marketChartCoverage(series(90, 24 * 3600), 24 * 3600, "90d", "complete");
  assert.deepEqual(
    { expected: sevenDays.expectedBucketCount, full: sevenDays.full },
    { expected: 168, full: true },
  );
  assert.deepEqual(
    { expected: thirtyDays.expectedBucketCount, full: thirtyDays.full },
    { expected: 180, full: true },
  );
  assert.deepEqual(
    { expected: ninetyDays.expectedBucketCount, full: ninetyDays.full },
    { expected: 90, full: true },
  );
});

test("full coverage requires every bucket, a contiguous span, and backend confirmation", () => {
  const bucketSeconds = 3600;
  const rows: MarketChartCandle[] = Array.from({ length: 24 }, (_, index) => {
    const time = Date.parse("2026-08-31T00:00:00.000Z") + index * bucketSeconds * 1000;
    return {
      startTime: new Date(time).toISOString(),
      endTime: new Date(time + bucketSeconds * 1000).toISOString(),
      time,
      open: 26.8,
      high: 26.9,
      low: 26.7,
      close: 26.85,
      sampleCount: 2,
      observationCount: 2,
    };
  });

  assert.equal(marketChartCoverage(rows, bucketSeconds, "24h", "partial").full, false);
  assert.equal(marketChartCoverage(rows.slice(1), bucketSeconds, "24h", "complete").full, false);
  assert.equal(marketChartCoverage(rows, bucketSeconds, "24h", "complete").full, true);

  const withGap = [...rows];
  withGap[12] = { ...withGap[12], time: withGap[12].time + bucketSeconds * 1000 };
  assert.equal(marketChartCoverage(withGap, bucketSeconds, "24h", "complete").full, false);
});

test("bucket-aware labels and responsive zoom limits keep dense mobile candles readable", () => {
  assert.equal(marketCandleBucketLabel(2 * 3600), "2 小时 K");
  assert.equal(marketCandleBucketLabel(4 * 3600), "4 小时 K");
  assert.equal(marketCandleBucketLabel(15 * 60), "15 分钟 K");
  assert.equal(expectedCandleCount("7d", 2 * 3600), 84);
  assert.equal(expectedCandleCount("24h", 4 * 3600), 6);
  assert.equal(expectedCandleCount("7d", 4 * 3600), 42);
  assert.equal(defaultCandleZoomLimit("24h", 390, 4 * 3600), 6);
  assert.equal(defaultCandleZoomLimit("7d", 390, 4 * 3600), 42);
  assert.equal(nextCandleZoomLimit("24h", 6, 6, "in", 4 * 3600), 5);
  assert.equal(nextCandleZoomLimit("7d", 42, 42, "in", 4 * 3600), 32);
  assert.equal(defaultCandleZoomLimit("7d", 390, 2 * 3600), 42);
  assert.equal(defaultCandleZoomLimit("30d", 390, 4 * 3600), 60);
  assert.equal(defaultCandleZoomLimit("30d", 1280, 4 * 3600), 180);
  assert.equal(defaultCandleZoomLimit("90d", 390, 24 * 3600), 45);
  assert.equal(defaultCandleZoomLimit("90d", 1280, 24 * 3600), 90);
  assert.equal(nextCandleZoomLimit("7d", 84, 84, "in", 2 * 3600), 63);
});

test("latest live quote updates only a comparable still-open candle", () => {
  const base: MarketChartCandle[] = normalizeMarketCandles([
    candle("2026-08-29T01:00:00.000Z", 10, 12, 9, 11),
  ]);
  const inside = mergeLiveReference(base, {
    price: 13,
    observedAt: "2026-08-29T01:00:30.000Z",
    comparable: true,
  });
  const outside = mergeLiveReference(base, {
    price: 14,
    observedAt: "2026-08-29T01:01:00.000Z",
    comparable: true,
  });
  const notComparable = mergeLiveReference(base, {
    price: 15,
    observedAt: "2026-08-29T01:00:30.000Z",
    comparable: false,
  });

  assert.deepEqual({ close: inside[0].close, high: inside[0].high, low: inside[0].low }, { close: 13, high: 13, low: 9 });
  assert.equal(outside[0].close, 11);
  assert.equal(notComparable[0].close, 11);
  assert.equal(canMergeLiveReference(base, {
    price: 13,
    observedAt: "2026-08-29T01:00:30.000Z",
    comparable: true,
  }), true);
  assert.equal(canMergeLiveReference(base, {
    price: 13,
    observedAt: null,
    comparable: true,
  }), false);
});

test("non-comparable polled quote cannot become a historical chart readout", () => {
  const base = normalizeMarketCandles([
    candle("2026-08-29T01:00:00.000Z", 72.9, 73.2, 72.8, 73.1),
  ]);
  const payloadReference = {
    price: 73.15,
    observedAt: "2026-08-29T01:00:30.000Z",
    comparable: false,
  };
  const polledReference = {
    price: 84.849,
    observedAt: "2026-08-29T01:00:40.000Z",
    comparable: false,
  };
  const references = resolveMarketChartReferences(payloadReference, polledReference, true);
  const merged = mergeLiveReference(base, references.candle);
  const domain = paddedPriceDomain(merged.flatMap((item) => [item.low, item.high]));
  const readout = resolveMarketChartLatestReadout(merged, references.display, false);

  assert.equal(references.display.price, null);
  assert.equal(references.candle.price, 73.15);
  assert.equal(merged[0].close, 73.1);
  assert.deepEqual(readout, {
    price: 73.1,
    observedAt: "2026-08-29T01:01:00.000Z",
    label: "最新收盘",
    isCurrent: false,
  });
  assert.ok(domain.max < 84.849);
});

test("comparable payload quote may update an open candle and become current", () => {
  const base = normalizeMarketCandles([
    candle("2026-08-29T01:00:00.000Z", 72.9, 73.2, 72.8, 73.1),
  ]);
  const payloadReference = {
    price: 73.25,
    observedAt: "2026-08-29T01:00:30.000Z",
    comparable: true,
  };
  const references = resolveMarketChartReferences(payloadReference, {
    price: 84.849,
    observedAt: "2026-08-29T01:00:40.000Z",
    comparable: false,
  }, true);
  const liveMerged = canMergeLiveReference(base, references.candle);
  const merged = mergeLiveReference(base, references.candle);
  const readout = resolveMarketChartLatestReadout(merged, references.display, liveMerged);

  assert.equal(liveMerged, true);
  assert.equal(merged[0].close, 73.25);
  assert.deepEqual(readout, {
    price: 73.25,
    observedAt: "2026-08-29T01:01:00.000Z",
    label: "当前价",
    isCurrent: true,
  });
});

test("polled quote is a current baseline only when no historical candle exists", () => {
  const polledReference = {
    price: 84.849,
    observedAt: "2026-08-29T01:00:40.000Z",
    comparable: false,
  };
  const references = resolveMarketChartReferences({
    price: null,
    observedAt: null,
    comparable: false,
  }, polledReference, false);

  assert.deepEqual(resolveMarketChartLatestReadout([], references.display, false), {
    price: 84.849,
    observedAt: "2026-08-29T01:00:40.000Z",
    label: "当前价",
    isCurrent: true,
  });
});

test("comparable quote outside the latest open bucket remains latest close", () => {
  const base = normalizeMarketCandles([
    candle("2026-08-29T01:00:00.000Z", 72.9, 73.2, 72.8, 73.1),
  ]);
  const reference = {
    price: 73.25,
    observedAt: "2026-08-29T01:01:00.000Z",
    comparable: true,
  };
  const merged = mergeLiveReference(base, reference);

  assert.equal(canMergeLiveReference(base, reference), false);
  assert.equal(merged[0].close, 73.1);
  assert.equal(resolveMarketChartLatestReadout(merged, reference, false).label, "最新收盘");
});

test("flat and nearly-flat prices use a continuous readable domain", () => {
  const flat = paddedPriceDomain([100, 100]);
  const nearlyFlat = paddedPriceDomain([100, 100.000001]);
  const flatSpan = flat.max - flat.min;
  const nearlyFlatSpan = nearlyFlat.max - nearlyFlat.min;

  assert.ok(flatSpan > 0.3);
  assert.ok(Math.abs(flatSpan - nearlyFlatSpan) / flatSpan < 0.001);
});

test("quarantined candle metadata produces an explicit footer notice", () => {
  assert.deepEqual(marketChartQuarantineNotice({
    quarantined_candle_count: 1,
    quarantined_prefix_count: 0,
    quarantined_tail_count: 1,
    quarantine_reason: "superseded_partial_edge_batch",
  }), {
    count: 1,
    label: "已隔离 1 根旧批次异常报价",
    reason: "该报价来自较早且未完成的上游批次",
  });
  assert.equal(marketChartQuarantineNotice({
    quarantined_prefix_count: 0,
    quarantined_tail_count: 0,
  }), null);
});

test("moving averages restart after missing buckets and material price jumps", () => {
  const minute = 60_000;
  const values = [10, 11, 12, 13, 14, 20, 21, 22, 23, 24, 25];
  const times = values.map((_, index) => index * minute);
  const averages = movingAverageByTime(values, times, 5, 60, [5]);

  assert.deepEqual(averages.slice(0, 6), [null, null, null, null, 12, null]);
  assert.equal(averages[9], 22);

  const withGap = movingAverageByTime([1, 2, 3, 4, 5, 6, 7], [0, minute, 2 * minute, 3 * minute, 4 * minute, 10 * minute, 11 * minute], 3, 60);
  assert.deepEqual(withGap.slice(4), [4, null, null]);
});

test("A30 repricing remains truthful OHLC while MA segmentation detects the jump", () => {
  const rows: MarketChartCandle[] = [
    { startTime: "2026-08-28T00:00:00Z", endTime: "2026-08-29T00:00:00Z", time: Date.parse("2026-08-28T00:00:00Z"), open: 3.91, high: 3.92, low: 3.90, close: 3.914673, sampleCount: 2, observationCount: 2 },
    { startTime: "2026-08-29T00:00:00Z", endTime: "2026-08-30T00:00:00Z", time: Date.parse("2026-08-29T00:00:00Z"), open: 3.910686, high: 4.182035, low: 3.90, close: 4.182035, sampleCount: 2, observationCount: 2 },
    { startTime: "2026-08-30T00:00:00Z", endTime: "2026-08-31T00:00:00Z", time: Date.parse("2026-08-30T00:00:00Z"), open: 4.182, high: 4.19, low: 4.18, close: 4.184147, sampleCount: 2, observationCount: 2 },
  ];

  assert.deepEqual(significantPriceJumpIndexes(rows), [1]);
  assert.equal(rows[1].close, 4.182035);
});

test("MA segmentation detects a large opening gap without rewriting a small candle body", () => {
  const rows: MarketChartCandle[] = [
    { startTime: "2026-08-30T00:00:00Z", endTime: "2026-08-30T01:00:00Z", time: Date.parse("2026-08-30T00:00:00Z"), open: 29.02, high: 29.08, low: 28.98, close: 29.04, sampleCount: 3, observationCount: 3 },
    { startTime: "2026-08-31T00:00:00Z", endTime: "2026-08-31T01:00:00Z", time: Date.parse("2026-08-31T00:00:00Z"), open: 26.92, high: 26.98, low: 26.88, close: 26.95, sampleCount: 3, observationCount: 3 },
  ];

  assert.deepEqual(significantPriceJumpIndexes(rows), [1]);
  assert.equal(rows[1].open, 26.92);
  assert.equal(rows[1].close, 26.95);
});

test("bucket inference treats a large interval as missing history", () => {
  assert.equal(candleBucketMilliseconds([0, 60_000, 86_460_000]), 60_000);
});

test("Web chart exposes all high-density desktop ranges through discrete zoom limits", () => {
  assert.equal(defaultCandleZoomLimit("24h"), 24);
  assert.equal(defaultCandleZoomLimit("7d"), 168);
  assert.equal(defaultCandleZoomLimit("30d"), 180);
  assert.equal(defaultCandleZoomLimit("90d"), 90);
  assert.equal(nextCandleZoomLimit("30d", 180, 180, "in"), 120);
  assert.equal(nextCandleZoomLimit("30d", 120, 180, "out"), 180);
  assert.equal(nextCandleZoomLimit("90d", 90, 90, "in"), 60);
  assert.equal(nextCandleZoomLimit("90d", 45, 90, "out"), 60);
  assert.equal(nextCandleZoomLimit("7d", 168, 168, "in"), 126);
});

test("Web K-line renderer follows the App visual and refresh contract", () => {
  const chart = fs.readFileSync(new URL("../components/market-candlestick-chart.tsx", import.meta.url), "utf8");
  const styles = fs.readFileSync(new URL("../components/market-candlestick-chart.module.css", import.meta.url), "utf8");

  assert.match(chart, /useState<MarketChartRange>\("30d"\)/);
  assert.match(chart, /LATEST_REFRESH_MS = 300_000/);
  assert.match(chart, /"24h": 300_000/);
  assert.match(chart, /"7d": 300_000/);
  assert.match(chart, /"90d": 300_000/);
  assert.match(chart, /value: "90d"/);
  assert.match(chart, />\{rangeLabel\(option\.value, t\)\}<\/button>/);
  assert.match(chart, /preserveAspectRatio="xMidYMid meet"/);
  assert.match(chart, /period: 5/);
  assert.match(chart, /period: 10/);
  assert.match(chart, /period: 20/);
  assert.doesNotMatch(chart, /period: 30|MA30|closeLine/);
  assert.match(chart, /mergeLiveReference/);
  assert.match(chart, /marketChartSummary\(normalized\)/);
  assert.match(chart, /matchesMarketCandleSelection\(/);
  assert.match(chart, /requestKey !== `\$\{modelIdentity\(modelRef\.current\)\}\|\$\{range\}`/);
  assert.match(chart, /onSnapshotRef\.current\?\.\(\{/);
  assert.match(chart, /resolveMarketChartReferences\(/);
  assert.doesNotMatch(chart, /comparable: payloadReference\.comparable/);
  assert.match(chart, /const plotReferencePrice = latestCandle/);
  assert.match(chart, /const latestValue = latestCandle\?\.close/);
  assert.match(chart, /const displayedLatestValue = latestReadout\.price/);
  assert.match(chart, /最新收盘/);
  assert.match(chart, /const latestReadoutLabel = latestReadout\.label/);
  assert.match(chart, /accessibleReadout[\s\S]*latestReadoutLabel/);
  assert.doesNotMatch(chart, /`当前报价 \$\{formatPrice\(reference\.price/);
  assert.match(chart, /viewportStart/);
  assert.match(chart, /chartTimeTicks/);
  assert.match(chart, /真实历史仍在积累/);
  assert.match(chart, /movingAverageByTime/);
  assert.match(chart, /payloadHasLiveQuote/);
  assert.doesNotMatch(chart, /return value\?\.server_time/);
  assert.match(chart, /ResizeObserver/);
  assert.match(chart, /useLayoutEffect/);
  assert.match(chart, /\}, \[viewState\]\);/);
  assert.match(chart, /chartCanvasLayout/);
  assert.match(chart, /已观测/);
  assert.match(chart, /已覆盖/);
  assert.match(chart, /history_coverage_status/);
  assert.match(chart, /quarantineNotice\.label/);
  assert.match(chart, /historyInFlight/);
  assert.match(chart, /latestInFlight/);
  assert.match(chart, /if \(historyInFlight\.current === requestKey\) return/);
  assert.match(chart, /if \(latestInFlight\.current === requestKey\) return/);
  assert.match(chart, /const historyPending = Boolean\(model && !payload && !historyError\)/);
  assert.match(chart, /viewState === "loading"/);
  assert.match(chart, /viewState === "empty"/);
  assert.match(chart, /viewState === "chart"/);
  assert.doesNotMatch(chart, /onWheel=/);
  assert.doesNotMatch(chart, /type WheelEvent/);
  assert.match(chart, /aria-hidden="true" focusable="false"/);
  assert.match(chart, /aria-live="polite" aria-atomic="true"/);
  assert.doesNotMatch(chart, /chartTargetWidth/);
  assert.match(chart, /renderedBodyTop = bodyTop - \(renderedBodyHeight - bodyHeight\) \/ 2/);
  assert.match(chart, /contiguousValueSegments/);
  assert.doesNotMatch(styles, /aspect-ratio: 360 \/ 236/);
  assert.match(styles, /--kline-rise: #c9323c/);
  assert.match(styles, /--kline-fall: #08784e/);
  assert.match(styles, /--kline-ma-5: #9a5c09/);
  assert.equal(styles.match(/grid-template-columns: repeat\(3,/g)?.length, 2);
  assert.match(styles, /@media \(prefers-color-scheme: dark\)/);
  assert.match(styles, /touch-action: pan-y pinch-zoom/);
  assert.match(styles, /\.candleRise rect[\s\S]*?fill: var\(--kline-card\)/);
  assert.match(styles, /\.candleFall rect[\s\S]*?fill: var\(--kline-fall\)/);
});

test("Web K-line renderer localizes chart copy, accessibility text, and formatting", () => {
  const chart = fs.readFileSync(new URL("../components/market-candlestick-chart.tsx", import.meta.url), "utf8");
  const localeRoot = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(chart, /const \{ locale, t, dateLocale \} = useI18n\(\)/);
  assert.doesNotMatch(chart, /toLocale(?:Date|Time)?String\("zh-CN"/);
  assert.match(chart, /formatDateTime\([\s\S]*dateLocale/);
  assert.match(chart, /formatTimeLabel\([\s\S]*dateLocale/);
  assert.match(chart, /formatPrice\([\s\S]*dateLocale/);
  assert.match(chart, /trends\.chartRange\.90Days/);
  assert.match(chart, /trends\.candles\.history\.coverage/);
  assert.match(chart, /trends\.candles\.state\.errorDescription/);
  assert.match(chart, /trends\.candles\.accessibility\.ohlc/);
  assert.match(chart, /trends\.candles\.ohlc\.open/);
  assert.match(chart, /trends\.candles\.maAria/);
  assert.match(chart, /trends\.candles\.viewport/);
  assert.match(chart, /trends\.candles\.chartAria/);
  assert.match(chart, /trends\.candles\.historyAccumulating/);
  assert.match(chart, /trends\.candles\.stale/);

  for (const key of [
    "trends.candles.bucket.hours",
    "trends.candles.history.complete",
    "trends.candles.state.loading",
    "trends.candles.state.emptyDescription",
    "trends.candles.accessibility.summary",
    "trends.candles.ohlc.close",
    "trends.candles.zoomOut",
    "trends.candles.chartAria",
    "trends.candles.quarantine.label",
    "trends.candles.liveRefresh",
  ]) {
    assert.match(localeRoot, new RegExp(`"${key.replaceAll(".", "\\.")}"\\s*:`));
  }
});
