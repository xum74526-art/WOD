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

test("trend dashboard renders server data without an immediate duplicate catalogue request", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");

  assert.match(panel, /initialData \? "ready" : "loading"/);
  assert.match(panel, /if \(!initialData\) void load\(false, true\)/);
  assert.match(panel, /MARKET_CATALOG_REFRESH_MS = 300_000/);
  assert.match(panel, /if \(showLoading\) setStatus\("loading"\)/);
  assert.match(serverData, /export async function getInitialMarketDashboard/);
  assert.match(serverData, /unstable_cache\(/);
  assert.match(serverData, /"ztw-public-market-dashboard-v4"/);
  assert.match(serverData, /revalidate: 300/);
  assert.match(serverData, /tags: \["public-market-dashboard"\]/);
  assert.match(serverData, /initialMarketDashboardBuildsInFlight/);
  assert.match(serverData, /buildInitialMarketDashboardSingleFlight/);
  assert.match(serverData, /if \(activeBuild\) return activeBuild/);
  assert.match(serverData, /initialMarketDashboardBuildsInFlight\.delete\(apiOrigin\)/);
  assert.match(serverData, /unstable_cache\(\s*buildInitialMarketDashboardSingleFlight/);
  assert.match(serverData, /readCachedInitialMarketDashboard\(resolveApiOrigin\(\)\)/);
  assert.match(serverData, /INITIAL_MARKET_HISTORY_TTL_MS = 300_000/);
  assert.match(serverData, /INITIAL_MARKET_HISTORY_STALE_MS = 600_000/);
  assert.match(serverData, /INITIAL_MARKET_HISTORY_RETRY_DELAY_MS = 5_000/);
  assert.match(serverData, /INITIAL_MARKET_HISTORY_CACHE_LIMIT = 256/);
  assert.match(serverData, /createStaleTtlCache<\[string, string, string\], MarketHistoryPoint\[]>/);
  assert.match(serverData, /JSON\.stringify\(\[apiOrigin, "90d", "kai", "ondemand", model, variant\]\)/);
  assert.match(serverData, /staleMs: INITIAL_MARKET_HISTORY_STALE_MS/);
  assert.match(serverData, /retryDelayMs: INITIAL_MARKET_HISTORY_RETRY_DELAY_MS/);
  assert.match(serverData, /const history = await readInitialMarketHistory\(apiOrigin, model, variant\)/);
  assert.doesNotMatch(serverData, /readInitialMarketHistory\(apiOrigin, model, variant\)\.catch\(\(\) => \[\]\)/);
  assert.match(serverData, /cache: "no-store"/);
  assert.doesNotMatch(serverData, /ztw-public-market-history-v/);
  assert.match(serverData, /text\(candleData\.gpu_model\) !== model/);
  assert.match(serverData, /text\(candleData\.gpu_variant\) !== variant/);
  assert.match(serverData, /text\(candleData\.range\) !== "90d"/);
  assert.match(serverData, /Array\.isArray\(candleData\.candles\)/);
  assert.match(serverData, /if \(history\.length !== candleRows\.length\) throw new Error\("market_dashboard_history_candles_invalid"\)/);
  assert.match(serverData, /if \(!data\.length\) throw new Error\("market_dashboard_empty"\)/);
  assert.match(serverData, /if \(!models\.length\) throw new Error\("market_dashboard_models_empty"\)/);
  assert.match(serverData, /compactMarketHistories\(data\.map\(\(item\) => item\.history\)\)/);
  assert.match(serverData, /history_dates: compactHistories\.historyDates/);
  assert.match(panel, /expandMarketHistory\(initialData\?\.history_dates \?\? \[\], historyValues\)/);
  assert.match(serverData, /cachedCanonicalData\("\/api\/market\/ranking", 300, apiOrigin\)/);
  assert.match(serverData, /uncachedCanonicalData\(`\/api\/market\/prices\/candles\?\$\{query\}`, apiOrigin\)/);
});

test("market summary is built from official OHLC candles", () => {
  const source = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const summary = source.slice(source.indexOf("async function buildMarketSummary"), source.indexOf("function orderStatus"));

  assert.match(summary, /\/api\/market\/prices\/candles/);
  assert.match(summary, /close_price_card_hours/);
  assert.match(summary, /median_price_card_hours/);
  assert.doesNotMatch(summary, /\/api\/market\/prices\/history/);
});

test("public market summary coalesces refreshes without caching incomplete history", () => {
  const source = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const summaryBuilder = source.slice(source.indexOf("async function buildMarketSummary"), source.indexOf("const readPublicMarketSummary"));

  assert.match(source, /PUBLIC_MARKET_SUMMARY_TTL_MS = 300_000/);
  assert.match(source, /PUBLIC_MARKET_SUMMARY_STALE_MS = 600_000/);
  assert.match(source, /PUBLIC_MARKET_SUMMARY_RETRY_DELAY_MS = 5_000/);
  assert.match(source, /createStaleTtlCache<\s*\[NextRequest, string, string\]/);
  assert.match(source, /JSON\.stringify\(\[apiOrigin, locale\]\)/);
  assert.match(source, /normalizeStoredLocale\(request\.cookies\.get\("kai\.locale"\)\?\.value\)/);
  assert.match(source, /!candleResult\.ok/);
  assert.match(source, /!Array\.isArray\(candleData\.candles\)/);
  assert.match(source, /text\(candleData\.gpu_model\) !== model/);
  assert.match(source, /text\(candleData\.gpu_variant\) !== variant/);
  assert.match(source, /text\(candleData\.range\) !== "90d"/);
  assert.match(source, /if \(history\.length !== candleRows\.length\) complete = false/);
  assert.match(source, /shouldStore: \(payload\) => payload\.complete/);
  assert.match(source, /return publicApiSuccess\(payload\.data, payload\.meta, 300\)/);
  assert.match(summaryBuilder, /upstream\(request, "\/api\/market\/ranking", \{ auth: false \}\)/);
  assert.match(summaryBuilder, /upstream\(request, "\/api\/market\/prices\/candles", \{ query, auth: false \}\)/);
  assert.doesNotMatch(summaryBuilder, /revalidate:/);
});

test("market ranking and trend dashboard keep the complete KAI catalogue", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const serverData = fs.readFileSync(new URL("../lib/server/public-page-data.ts", import.meta.url), "utf8");

  assert.doesNotMatch(adapter, /rankingData\.items\)\.slice\(0,\s*12\)/);
  assert.doesNotMatch(serverData, /ranking\.items\)\.slice\(0,\s*12\)/);
  assert.doesNotMatch(serverData, /raw\.items\)\.slice\(0,\s*12\)/);
  assert.match(adapter, /mapWithConcurrency\(entries, 8/);
  assert.match(serverData, /mapWithConcurrency\(entries, 8/);
});

test("trend panel keeps current quotes and matches a model by model plus variant", () => {
  const source = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");

  assert.match(source, /item\.median_price > 0 \|\| validHistory\(item\)\.length > 0/);
  assert.match(source, /`\$\{item\.gpu_model\} \$\{item\.gpu_variant\}`/);
  assert.match(source, /function preferredMarketModel/);
  assert.match(source, /aSevenDayCoverage/);
  assert.match(source, /\^RTX\\s\*4090/);
  assert.match(source, /findMobileModel\(models, a\.gpu_model\)\?\.sample_count/);
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

  assert.match(panel, /placeholder=\{t\("trends\.table\.search", "搜索完整行情"\)\}/);
  assert.match(panel, /<option value="all">\{t\("trends\.table\.allVram", "全部显存"\)\}<\/option>/);
  assert.match(panel, /\["up", "trends\.table\.directionUp", "只看上涨"\]/);
  assert.match(panel, /\["down", "trends\.table\.directionDown", "只看下跌"\]/);
  assert.match(styles, /\.trend-table-filters \{[^}]*flex-wrap: nowrap/);
  assert.match(styles, /\.trend-search input:focus-visible \{[^}]*outline: 0/);
  assert.doesNotMatch(styles, /\.trend-table-filters \{[^}]*grid-template-columns/);
});

test("trend ranges use real calendar windows and peak-preserving full-width sparklines", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const chart = fs.readFileSync(new URL("../components/market-candlestick-chart.tsx", import.meta.url), "utf8");
  const api = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(panel, /value: 28, key: "trends\.range\.4Weeks", label: "4周"/);
  assert.match(panel, /value: 56, key: "trends\.range\.8Weeks", label: "8周"/);
  assert.match(panel, /value: 90, key: "trends\.range\.3Months", label: "3个月"/);
  assert.match(panel, /86_400_000/);
  assert.match(panel, /function visualTrendPoints/);
  assert.match(panel, /targetCount = 36/);
  assert.match(panel, /function monotonePath/);
  assert.match(panel, /trend-mini-area/);
  assert.doesNotMatch(panel, /trend-mini-glow/);
  assert.doesNotMatch(panel, /pathLength="1"/);
  assert.match(panel, /MarketCandlestickChart/);
  assert.match(panel, /长期排行周期/);
  assert.match(panel, /trends\.focus\.longRangeChange/);
  assert.match(panel, /onSnapshot=\{setChartSnapshot\}/);
  assert.match(panel, /activeChartSnapshot\?\.range === "90d"/);
  assert.match(panel, /trends\.chartRange\.90Days/);
  assert.match(panel, /trends\.chartStats\.high/);
  assert.match(panel, /trends\.chartStats\.low/);
  assert.match(panel, /trends\.chartStats\.median/);
  assert.match(panel, /chartSummary\.changePct/);
  assert.doesNotMatch(panel, /selectedStatsRangeLabel/);
  assert.doesNotMatch(chart, /value: "24h", label: "24小时"/);
  assert.match(chart, /\{ value: "7d" \}/);
  assert.match(chart, /\{ value: "30d" \}/);
  assert.match(chart, /\{ value: "90d" \}/);
  assert.match(chart, /rangeLabel\(option\.value, t\)/);
  assert.match(chart, /preserveAspectRatio="xMidYMid meet"/);
  assert.doesNotMatch(chart, /preserveAspectRatio="none"/);
  assert.match(api, /range: "90d"/);
  assert.doesNotMatch(panel, /slice\(0, weeks\)/);
});

test("trend panel explicitly localizes controls, states, and locale-sensitive values", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const localeRoot = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(panel, /const \{ t, dateLocale \} = useI18n\(\)/);
  assert.match(panel, /new Intl\.NumberFormat\(dateLocale/);
  assert.match(panel, /new Intl\.DateTimeFormat\(dateLocale/);
  assert.match(panel, /trends\.state\.loading/);
  assert.match(panel, /trends\.table\.searchAria/);
  assert.match(panel, /trends\.pagination\.aria/);
  assert.doesNotMatch(panel, /toLocale(?:Date|Time)String\("zh-CN"/);
  assert.match(localeRoot, /"trends\.state\.loading": "Loading compute market"/);
  assert.match(localeRoot, /"trends\.pagination\.next": "Next"/);
});

test("trend selection and candle statistics reject stale cross-identity state", () => {
  const panel = fs.readFileSync(new URL("../components/live-market-panel.tsx", import.meta.url), "utf8");
  const chart = fs.readFileSync(new URL("../components/market-candlestick-chart.tsx", import.meta.url), "utf8");

  assert.match(panel, /const catalogRequest = useRef\(0\)/);
  assert.match(panel, /const request = \+\+catalogRequest\.current/);
  assert.match(panel, /if \(request !== catalogRequest\.current\) return/);
  assert.match(panel, /selectedModelRef\.current = nextSelectedModel/);
  assert.match(panel, /const activeChartSnapshot = chartSnapshot\?\.identity === selectedChartIdentity/);
  assert.doesNotMatch(panel, /markets\.find\(\(item\) => item\.gpu_model === selectedModel\) \?\? markets\[0\]/);
  assert.match(chart, /sequence !== historyRequest\.current/);
  assert.match(chart, /matchesMarketCandleSelection[\s\S]*activeModel\.gpu_model[\s\S]*activeModel\.gpu_variant[\s\S]*range/);
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
