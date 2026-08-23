import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("compute trends use /trend as the canonical route", () => {
  const page = fs.readFileSync(new URL("../app/trend/page.tsx", import.meta.url), "utf8");
  const config = fs.readFileSync(new URL("../next.config.ts", import.meta.url), "utf8");
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const footer = fs.readFileSync(new URL("../components/site-footer.tsx", import.meta.url), "utf8");

  assert.match(page, /LiveMarketPanel/);
  assert.match(page, /getInitialMarketDashboard/);
  assert.match(page, /initialData=\{initialData\}/);
  assert.match(config, /source: "\/market\/trends", destination: "\/trend", permanent: true/);
  assert.match(header, /label: "算力行情", href: "\/trend"/);
  assert.match(footer, /href="\/trend"/);
});

test("trend dashboard renders server data before refreshing in the background", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");

  assert.match(panel, /initialData \? "ready" : "loading"/);
  assert.match(panel, /void load\(false, !initialData\)/);
  assert.match(panel, /if \(showLoading\) setStatus\("loading"\)/);
  assert.match(serverData, /export async function getInitialMarketDashboard/);
  assert.match(serverData, /cachedCanonicalData\("\/api\/market\/ranking", 30\)/);
  assert.match(serverData, /cachedCanonicalData\(`\/api\/market\/prices\/candles\?\$\{query\}`, 120\)/);
});

test("market summary is built from official OHLC candles", () => {
  const source = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const summary = source.slice(source.indexOf("async function marketSummary"), source.indexOf("function orderStatus"));

  assert.match(summary, /\/api\/market\/prices\/candles/);
  assert.match(summary, /close_price_card_hours/);
  assert.match(summary, /median_price_card_hours/);
  assert.doesNotMatch(summary, /\/api\/market\/prices\/history/);
});

test("trend panel keeps current quotes and matches a model by model plus variant", () => {
  const source = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");

  assert.match(source, /item\.median_price > 0 \|\| validHistory\(item\)\.length > 0/);
  assert.match(source, /`\$\{item\.gpu_model\} \$\{item\.gpu_variant\}`/);
});

test("GPU chart picker opens the full catalogue, filters after typing, and supports keyboard selection", () => {
  const source = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const styles = fs.readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

  assert.match(source, /gpuPickerOptions/);
  assert.match(source, /gpuPickerDirty/);
  assert.match(source, /if \(!needle\) return markets/);
  assert.match(source, /role="combobox"/);
  assert.match(source, /role="listbox"/);
  assert.match(source, /event\.key === "ArrowDown"/);
  assert.match(source, /event\.key === "Enter"/);
  assert.doesNotMatch(source, /return markets\.slice\(0, 8\)/);
  assert.doesNotMatch(source, /<datalist/);
  assert.match(styles, /\.trend-focus-picker-shell::after \{[^}]*border: 1px solid var\(--line\)/);
  assert.match(styles, /\.trend-focus-gpu-picker input:focus-visible \{[^}]*outline: 0/);
});

test("complete market filters keep the compact original controls", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const styles = fs.readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

  assert.match(panel, /placeholder="搜索完整行情"/);
  assert.match(panel, /<option value="all">全部显存<\/option>/);
  assert.match(panel, /\["up", "只看上涨"\]/);
  assert.match(panel, /\["down", "只看下跌"\]/);
  assert.match(styles, /\.trend-table-filters \{[^}]*flex-wrap: nowrap/);
  assert.match(styles, /\.trend-search input:focus-visible \{[^}]*outline: 0/);
  assert.doesNotMatch(styles, /\.trend-table-filters \{[^}]*grid-template-columns/);
});

test("trend ranges use real calendar windows and peak-preserving full-width sparklines", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(panel, /value: 28, label: "4周"/);
  assert.match(panel, /value: 56, label: "8周"/);
  assert.match(panel, /value: 90, label: "3个月"/);
  assert.match(panel, /86_400_000/);
  assert.match(panel, /function visualTrendPoints/);
  assert.match(panel, /targetCount = 36/);
  assert.match(panel, /function monotonePath/);
  assert.match(panel, /trend-mini-area/);
  assert.doesNotMatch(panel, /trend-mini-glow/);
  assert.doesNotMatch(panel, /pathLength="1"/);
  assert.match(panel, /rawRange \* \.08/);
  assert.match(panel, /rawMax \* \.001/);
  assert.match(panel, /trend-grid-price/);
  assert.match(api, /range: "90d"/);
  assert.doesNotMatch(panel, /slice\(0, weeks\)/);
});

test("home candlestick chart uses stored OHLC and real calendar ranges", () => {
  const chart = fs.readFileSync(new URL("../components/gpu-candlestick-chart.tsx", import.meta.url), "utf8");
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");

  assert.match(chart, /value: 28, label: "4W"/);
  assert.match(chart, /value: 56, label: "8W"/);
  assert.match(chart, /value: 90, label: "3M"/);
  assert.match(chart, /86_400_000/);
  assert.match(chart, /point\.open/);
  assert.match(chart, /point\.high/);
  assert.match(chart, /point\.low/);
  assert.match(chart, /point\.close/);
  assert.match(chart, /rawRange \* \.08/);
  assert.match(serverData, /open_price_card_hours/);
  assert.match(serverData, /high_price_card_hours/);
  assert.match(serverData, /low_price_card_hours/);
  assert.match(serverData, /close_price_card_hours/);
});
