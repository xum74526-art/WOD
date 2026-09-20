import "server-only";

import { unstable_cache } from "next/cache";
import type { InitialMarketDashboard, InitialMarketSummary, MarketSummary } from "@/components/live-market-panel";
import { compactMarketHistories, type MarketHistoryPoint } from "@/lib/compact-market-history";
import type { PublicProduct } from "@/lib/commerce-api";
import type { InitialGpuTrend, PublicMarketRanking, PublicMarketRankingItem } from "@/lib/public-data";
import { resolveApiOrigin } from "@/lib/server/api-origin";
import { createStaleTtlCache } from "@/lib/stale-ttl-cache";

type JsonObject = Record<string, unknown>;
type CanonicalEnvelope = { code?: number; msg?: string; data?: unknown };

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function array(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(object) : [];
}

async function mapWithConcurrency<T, R>(items: T[], concurrency: number, mapper: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await mapper(items[index]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, worker));
  return results;
}

function text(value: unknown, fallback = "") {
  return typeof value === "string" ? value : value == null ? fallback : String(value);
}

function number(value: unknown, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

async function canonicalResponseData(response: Response) {
  const payload = await response.json() as CanonicalEnvelope;
  if (!response.ok || payload.code === 1) throw new Error(payload.msg || `业务服务请求失败 (${response.status})`);
  return payload.data;
}

async function cachedCanonicalData(path: string, revalidate: number, apiOrigin = resolveApiOrigin()) {
  const response = await fetch(`${apiOrigin}${path}`, {
    headers: { Accept: "application/json" },
    cache: "force-cache",
    next: { revalidate },
    signal: AbortSignal.timeout(15_000),
  });
  return canonicalResponseData(response);
}

async function uncachedCanonicalData(path: string, apiOrigin: string) {
  const response = await fetch(`${apiOrigin}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: AbortSignal.timeout(15_000),
  });
  return canonicalResponseData(response);
}

function rankingItem(value: unknown): PublicMarketRankingItem {
  const item = object(value);
  return {
    gpu_model: text(item.gpu_model),
    gpu_variant: text(item.gpu_variant),
    median_price_cny: number(item.median_price_cny),
    median_price_card_hours: number(item.median_price_card_hours),
    change_24h: number(item.change_24h),
    available_gpu_count: number(item.available_gpu_count),
    source_count: number(item.source_count),
    sources: Array.isArray(item.sources) ? item.sources.map((source) => text(source)).filter(Boolean) : [],
    history_day_count: number(item.history_day_count),
    history_point_count: number(item.history_point_count),
    market_status: text(item.market_status),
  };
}

function publicProduct(value: unknown): PublicProduct {
  const item = object(value);
  const rawSupplierId = item.supplier_id == null ? null : number(item.supplier_id);
  const rawMarketSource = text(item.market_source).toLowerCase();
  const rawSellerType = text(item.seller_type).toLowerCase();
  const legacyMerchant = rawSellerType === "merchant"
    || text(item.fulfillment_mode).toLowerCase() === "merchant_manual"
    || text(item.resource_claim_source).toLowerCase() === "merchant_declared"
    || (rawSupplierId != null && rawSupplierId > 0);
  const marketSource = rawMarketSource === "kai" || rawMarketSource === "wod"
    ? rawMarketSource
    : legacyMerchant ? "wod" : "kai";
  const sellerType = rawSellerType === "merchant" || (rawSellerType !== "kai_self_operated" && marketSource === "wod")
    ? "merchant"
    : "kai_self_operated";
  const supplierId = sellerType === "merchant" && rawSupplierId != null && rawSupplierId > 0 ? rawSupplierId : null;
  const supplierName = text(item.supplier_name) || null;
  const sellerName = text(item.seller_name) || supplierName || (sellerType === "kai_self_operated" ? "算力星图自营" : "第三方商家");
  const fulfillmentMode = text(item.fulfillment_mode, sellerType === "kai_self_operated" ? "platform_manual" : "merchant_manual") === "merchant_manual"
    ? "merchant_manual"
    : "platform_manual";
  const resourceClaimSource = text(
    item.resource_claim_source,
    sellerType === "kai_self_operated" ? "kai_published" : "merchant_declared",
  ) === "merchant_declared" ? "merchant_declared" : "kai_published";
  const memory = text(item.memory);
  const price = number(item.price_cny_per_gpu_hour, number(item.price));
  const stock = number(item.stock);
  const purchaseUnit = text(item.purchase_unit, "hour");
  return {
    id: number(item.id),
    supplier_id: supplierId,
    supplier_name: supplierName,
    supplier_rating: item.supplier_rating == null ? null : number(item.supplier_rating),
    supplier_order_count: item.supplier_order_count == null ? null : number(item.supplier_order_count),
    seller_type: sellerType,
    seller_name: sellerName,
    fulfillment_mode: fulfillmentMode,
    resource_claim_source: resourceClaimSource,
    assurance_label: text(item.assurance_label, sellerType === "kai_self_operated" ? "算力星图自营 · 平台人工交付" : "商家发布 · 商家人工交付"),
    assurance_description: text(
      item.assurance_description,
      sellerType === "kai_self_operated"
        ? "价格与商品由算力星图发布，平台安排人工交付。"
        : "商品配置与库存由商家自行申报，并由该商家负责人工交付；平台记录订单、验收与争议状态。",
    ),
    name: text(item.name),
    gpu_model: text(item.gpu_model),
    memory,
    gpu_memory_gb: number(memory.match(/\d+(?:\.\d+)?/)?.[0]),
    region: text(item.region_name, text(item.region_code, text(item.city, "地区待确认"))),
    description: text(item.desc),
    cpu_cores: null,
    ram_gb: null,
    disk_gb: null,
    bandwidth_mbps: null,
    unit_price_ch: number(item.price_card_hours_per_gpu_hour, price),
    price: { amount: price.toFixed(4), currency: "CNY", unit: "GPU·小时" },
    total_quantity: item.reported_stock == null ? stock : number(item.reported_stock, stock),
    available_quantity: stock,
    source_name: supplierName || (sellerType === "kai_self_operated" ? "KAI Pricing" : sellerName),
    source_observed_at: text(item.price_updated_at) || null,
    inquiry_available: item.inquiry_available !== false,
    interaction_mode: ["direct_trade", "matchmaking", "history_only"].includes(text(item.interaction_mode))
      ? text(item.interaction_mode) as PublicProduct["interaction_mode"]
      : Boolean(item.purchasable) ? "direct_trade" : "matchmaking",
    purchasable: Boolean(item.purchasable),
    purchase_unavailable_reason: text(item.purchase_unavailable_reason) || null,
    cycle: Array.isArray(item.cycle) ? item.cycle.map((entry) => number(entry)).filter(Boolean) : [],
    purchase_unit: purchaseUnit,
    purchase_hour_options: Array.isArray(item.purchase_hour_options) ? item.purchase_hour_options.map((entry) => number(entry)).filter((entry) => Number.isInteger(entry) && entry > 0) : [],
    billing_unit: text(item.billing_unit, "GPU_HOUR"),
    image_url: text(item.image_url) || null,
    market_source: marketSource,
  };
}

function dashboardModelMemory(model: string, variant: string) {
  const matched = `${variant} ${model}`.match(/(?:^|\D)(\d{2,3})\s*(?:GB|G)(?:\D|$)/i);
  return matched ? number(matched[1]) : undefined;
}

function dashboardModel(value: unknown) {
  const item = object(value);
  return {
    gpu_model: text(item.gpu_model),
    gpu_variant: text(item.gpu_variant),
    sources: Array.isArray(item.sources) ? item.sources.map((source) => text(source)).filter(Boolean) : [],
    sample_count: number(item.sample_count),
    available_gpu_count: number(item.available_gpu_count),
    market_status: text(item.market_status),
  };
}

function dashboardSource(value: unknown) {
  const item = object(value);
  return {
    source: text(item.source),
    source_name: text(item.source_name),
    enabled: Boolean(item.enabled),
    status: text(item.status),
    sample_count: number(item.sample_count),
    last_success_at: text(item.last_success_at) || null,
    has_error: Boolean(item.has_error),
    error_code: text(item.error_code) || null,
  };
}

export async function getInitialMarketRanking(): Promise<PublicMarketRanking | null> {
  try {
    const raw = object(await cachedCanonicalData("/api/market/ranking", 300));
    const data = array(raw.items).map(rankingItem);
    return { data, meta: { observed_at: text(raw.server_time), count: data.length, source: "canonical-api" } };
  } catch {
    return null;
  }
}

export async function getInitialPublicProducts(): Promise<PublicProduct[] | null> {
  const results = await Promise.allSettled([
    cachedCanonicalData("/api/products?page=1&page_size=100&market_source=kai&representative=true", 300),
    cachedCanonicalData("/api/products?page=1&page_size=100&market_source=wod", 15),
  ]);
  const available = results
    .filter((result): result is PromiseFulfilledResult<unknown> => result.status === "fulfilled")
    .flatMap((result) => array(object(result.value).items).map(publicProduct));
  return results.every((result) => result.status === "rejected") ? null : available;
}

export async function getInitialGpuTrend(ranking: PublicMarketRanking | null): Promise<InitialGpuTrend | null> {
  const candidates = (ranking?.data ?? []).filter((item) => item.median_price_card_hours > 0);
  const withHistory = candidates.filter((item) => item.history_point_count >= 2 || item.history_day_count >= 2);
  const selected = withHistory.find((item) => item.gpu_model.toUpperCase().includes("H100")) ?? withHistory[0] ?? candidates[0];
  if (!selected) return null;
  try {
    const query = new URLSearchParams({
      model: selected.gpu_model,
      variant: selected.gpu_variant,
      range: "90d",
      billing_mode: "ondemand",
      sources: "kai",
    });
    const raw = object(await cachedCanonicalData(`/api/market/prices/candles?${query}`, 300));
    const history = array(raw.candles).map((point) => ({
      date: text(point.start_time),
      median: number(point.close_price_card_hours),
      open: number(point.open_price_card_hours),
      high: number(point.high_price_card_hours),
      low: number(point.low_price_card_hours),
      close: number(point.close_price_card_hours),
    })).filter((point) => point.date && point.median > 0);
    if (history.length < 2) return null;
    return {
      market: {
        gpu_model: `${selected.gpu_model} ${selected.gpu_variant}`.trim(),
        gpu_slug: `${selected.gpu_model}-${selected.gpu_variant}`.toLowerCase(),
        provider_count: selected.source_count,
        history,
      },
      updated_at: text(raw.server_time, ranking?.meta.observed_at),
    };
  } catch {
    return null;
  }
}

async function loadInitialMarketHistory(
  apiOrigin: string,
  model: string,
  variant: string,
): Promise<MarketHistoryPoint[]> {
  const query = new URLSearchParams({ model, range: "90d", sources: "kai", billing_mode: "ondemand" });
  if (variant) query.set("variant", variant);
  const candleValue = await uncachedCanonicalData(`/api/market/prices/candles?${query}`, apiOrigin);
  const candleData = object(candleValue);
  if (
    text(candleData.gpu_model) !== model
    || text(candleData.gpu_variant) !== variant
    || text(candleData.range) !== "90d"
  ) {
    throw new Error("market_dashboard_history_identity_mismatch");
  }
  if (!Array.isArray(candleData.candles)) throw new Error("market_dashboard_history_candles_invalid");
  const candleRows = array(candleData.candles);
  const history = candleRows
    .map((candle) => ({
      date: text(candle.start_time).slice(0, 10),
      median: number(candle.close_price_card_hours, NaN),
    }))
    .filter((point) => point.date && Number.isFinite(point.median) && point.median > 0)
    .sort((a, b) => b.date.localeCompare(a.date));
  if (history.length !== candleRows.length) throw new Error("market_dashboard_history_candles_invalid");
  return history;
}

const INITIAL_MARKET_HISTORY_TTL_MS = 300_000;
const INITIAL_MARKET_HISTORY_STALE_MS = 600_000;
const INITIAL_MARKET_HISTORY_RETRY_DELAY_MS = 5_000;
const INITIAL_MARKET_HISTORY_CACHE_LIMIT = 256;
const readInitialMarketHistory = createStaleTtlCache<[string, string, string], MarketHistoryPoint[]>({
  key: (apiOrigin, model, variant) => JSON.stringify([apiOrigin, "90d", "kai", "ondemand", model, variant]),
  load: loadInitialMarketHistory,
  ttlMs: INITIAL_MARKET_HISTORY_TTL_MS,
  staleMs: INITIAL_MARKET_HISTORY_STALE_MS,
  retryDelayMs: INITIAL_MARKET_HISTORY_RETRY_DELAY_MS,
  maxEntries: INITIAL_MARKET_HISTORY_CACHE_LIMIT,
});

async function buildInitialMarketDashboard(apiOrigin: string): Promise<InitialMarketDashboard> {
  const [rankingValue, modelsValue, sourcesValue] = await Promise.all([
    cachedCanonicalData("/api/market/ranking", 300, apiOrigin),
    cachedCanonicalData("/api/market/models", 300, apiOrigin),
    cachedCanonicalData("/api/market/sources/status", 30, apiOrigin).catch(() => ({ items: [] })),
  ]);
  const ranking = object(rankingValue);
  const entries = array(ranking.items);
  const models = array(object(modelsValue).items).map(dashboardModel);
  if (!models.length) throw new Error("market_dashboard_models_empty");
  const data = (await mapWithConcurrency(entries, 8, async (entry): Promise<MarketSummary> => {
    const model = text(entry.gpu_model);
    const variant = text(entry.gpu_variant);
    const history = await readInitialMarketHistory(apiOrigin, model, variant);
    const current = number(entry.median_price_card_hours);
    return {
      gpu_model: variant ? `${model} ${variant}`.trim() : model,
      tier: text(entry.market_status),
      vram_gb: dashboardModelMemory(model, variant),
      min_price: current,
      median_price: current,
      official_min_price: current,
      official_median_price: current,
      history,
    };
  })).filter((item) => item.median_price > 0 || item.history.length > 0);
  if (!data.length) throw new Error("market_dashboard_empty");
  const compactHistories = compactMarketHistories(data.map((item) => item.history));
  const compactData = data.map(({ history: _history, ...item }, index): InitialMarketSummary => ({
    ...item,
    history_values: compactHistories.historyValues[index],
  }));
  return {
    data: compactData,
    history_dates: compactHistories.historyDates,
    meta: {
      observed_at: text(ranking.server_time),
      history_updated_at: text(ranking.server_time),
    },
    models,
    sources: array(object(sourcesValue).items).map(dashboardSource),
  };
}

const initialMarketDashboardBuildsInFlight = new Map<string, Promise<InitialMarketDashboard>>();

async function buildInitialMarketDashboardSingleFlight(apiOrigin: string): Promise<InitialMarketDashboard> {
  const activeBuild = initialMarketDashboardBuildsInFlight.get(apiOrigin);
  if (activeBuild) return activeBuild;
  const pendingBuild = buildInitialMarketDashboard(apiOrigin);
  initialMarketDashboardBuildsInFlight.set(apiOrigin, pendingBuild);
  try {
    return await pendingBuild;
  } finally {
    if (initialMarketDashboardBuildsInFlight.get(apiOrigin) === pendingBuild) {
      initialMarketDashboardBuildsInFlight.delete(apiOrigin);
    }
  }
}

const readCachedInitialMarketDashboard = unstable_cache(
  buildInitialMarketDashboardSingleFlight,
  ["ztw-public-market-dashboard-v4"],
  { revalidate: 300, tags: ["public-market-dashboard"] },
);

export async function getInitialMarketDashboard(): Promise<InitialMarketDashboard | null> {
  try {
    return await readCachedInitialMarketDashboard(resolveApiOrigin());
  } catch {
    return null;
  }
}
