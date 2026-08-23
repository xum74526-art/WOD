import "server-only";

import type { InitialMarketDashboard, MarketSummary } from "@/components/live-market-panel";
import type { PublicProduct } from "@/lib/commerce-api";
import type { InitialGpuTrend, PublicMarketRanking, PublicMarketRankingItem } from "@/lib/public-data";
import { resolveApiOrigin } from "@/lib/server/api-origin";

type JsonObject = Record<string, unknown>;
type CanonicalEnvelope = { code?: number; msg?: string; data?: unknown };

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function array(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(object) : [];
}

function text(value: unknown, fallback = "") {
  return typeof value === "string" ? value : value == null ? fallback : String(value);
}

function number(value: unknown, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

async function cachedCanonicalData(path: string, revalidate: number) {
  const response = await fetch(`${resolveApiOrigin()}${path}`, {
    headers: { Accept: "application/json" },
    cache: "force-cache",
    next: { revalidate },
    signal: AbortSignal.timeout(15_000),
  });
  const payload = await response.json() as CanonicalEnvelope;
  if (!response.ok || payload.code === 1) throw new Error(payload.msg || `业务服务请求失败 (${response.status})`);
  return payload.data;
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
  const memory = text(item.memory);
  const price = number(item.price_cny_per_gpu_hour, number(item.price));
  const stock = number(item.stock);
  const purchaseUnit = text(item.purchase_unit, text(item.market_source) === "kai" ? "hour" : "day");
  return {
    id: number(item.id),
    supplier_id: number(item.supplier_id),
    name: text(item.name),
    gpu_model: text(item.gpu_model),
    memory,
    gpu_memory_gb: number(memory.match(/\d+(?:\.\d+)?/)?.[0]),
    region: text(item.region_name, text(item.region_code, text(item.city, "未标注"))),
    description: text(item.desc),
    cpu_cores: null,
    ram_gb: null,
    disk_gb: null,
    bandwidth_mbps: null,
    unit_price_ch: number(item.price_card_hours_per_gpu_hour, price),
    price: { amount: price.toFixed(4), currency: "CNY", unit: "GPU·小时" },
    total_quantity: number(item.reported_stock, stock),
    available_quantity: stock,
    source_name: text(item.supplier_name, text(item.market_source) === "kai" ? "KAI Pricing" : "北斗 kai"),
    source_observed_at: text(item.price_updated_at) || null,
    server_online: Boolean(item.purchasable),
    purchasable: Boolean(item.purchasable),
    purchase_unavailable_reason: text(item.purchase_unavailable_reason) || null,
    cycle: Array.isArray(item.cycle) ? item.cycle.map((entry) => number(entry)).filter(Boolean) : [],
    purchase_unit: purchaseUnit,
    purchase_hour_options: Array.isArray(item.purchase_hour_options) ? item.purchase_hour_options.map((entry) => number(entry)).filter((entry) => Number.isInteger(entry) && entry > 0) : [],
    billing_unit: text(item.billing_unit, "GPU_HOUR"),
    image_url: text(item.image_url) || null,
    market_source: text(item.market_source, "kai"),
  };
}

function representativePublicProducts(values: unknown[]) {
  const representatives = new Map<string, PublicProduct>();
  for (const value of values) {
    const item = publicProduct(value);
    const identity = `${item.gpu_model.trim().toLowerCase()}|${item.gpu_memory_gb}`;
    const current = representatives.get(identity);
    if (
      !current
      || (item.purchasable && !current.purchasable)
      || (item.purchasable === current.purchasable && item.unit_price_ch < current.unit_price_ch)
    ) {
      representatives.set(identity, item);
    }
  }
  return [...representatives.values()];
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
    const raw = object(await cachedCanonicalData("/api/market/ranking", 30));
    const data = array(raw.items).slice(0, 12).map(rankingItem);
    return { data, meta: { observed_at: text(raw.server_time), count: data.length, source: "canonical-api" } };
  } catch {
    return null;
  }
}

export async function getInitialPublicProducts(): Promise<PublicProduct[] | null> {
  try {
    const raw = object(await cachedCanonicalData("/api/products?page_size=100", 15));
    return representativePublicProducts(array(raw.items));
  } catch {
    return null;
  }
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
    const raw = object(await cachedCanonicalData(`/api/market/prices/candles?${query}`, 120));
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

export async function getInitialMarketDashboard(): Promise<InitialMarketDashboard | null> {
  try {
    const [rankingValue, modelsValue, sourcesValue] = await Promise.all([
      cachedCanonicalData("/api/market/ranking", 30),
      cachedCanonicalData("/api/market/models", 30).catch(() => ({ items: [] })),
      cachedCanonicalData("/api/market/sources/status", 30).catch(() => ({ items: [] })),
    ]);
    const ranking = object(rankingValue);
    const entries = array(ranking.items).slice(0, 12);
    const data = (await Promise.all(entries.map(async (entry): Promise<MarketSummary> => {
      const model = text(entry.gpu_model);
      const variant = text(entry.gpu_variant);
      const query = new URLSearchParams({ model, range: "90d", sources: "kai", billing_mode: "ondemand" });
      if (variant) query.set("variant", variant);
      const candleValue = await cachedCanonicalData(`/api/market/prices/candles?${query}`, 120).catch(() => ({}));
      const history = array(object(candleValue).candles)
        .map((candle) => ({
          date: text(candle.start_time).slice(0, 10),
          median: number(candle.close_price_card_hours, NaN),
        }))
        .filter((point) => point.date && Number.isFinite(point.median) && point.median > 0)
        .sort((a, b) => b.date.localeCompare(a.date));
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
    }))).filter((item) => item.median_price > 0 || item.history.length > 0);
    if (!data.length) return null;
    return {
      data,
      meta: {
        observed_at: text(ranking.server_time),
        history_updated_at: text(ranking.server_time),
      },
      models: array(object(modelsValue).items).map(dashboardModel),
      sources: array(object(sourcesValue).items).map(dashboardSource),
    };
  } catch {
    return null;
  }
}
