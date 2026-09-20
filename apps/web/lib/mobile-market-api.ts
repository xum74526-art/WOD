import { apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";
import { kaiPricingQuery } from "@/lib/web-business-contract";


export type MobileMarketModel = {
  gpu_model: string;
  gpu_variant: string;
  sources: string[];
  sample_count: number;
  available_gpu_count: number;
  market_status: string;
};

export type MobileMarketCandle = {
  start_time: string;
  end_time: string;
  open_price_cny: number;
  high_price_cny: number;
  low_price_cny: number;
  close_price_cny: number;
  open_price_card_hours: number;
  high_price_card_hours: number;
  low_price_card_hours: number;
  close_price_card_hours: number;
  sample_count: number;
  observation_count: number;
  sources: string[];
};

export type MobileMarketCandles = {
  server_time: string;
  gpu_model: string;
  gpu_variant: string;
  range: string;
  bucket_seconds?: number;
  tick_seconds?: number;
  method:
    | "observed_source_median_ohlc"
    | "observed_source_robust_median_ohlc"
    | "official_hourly"
    | "official_daily"
    | string;
  is_interpolated: false;
  history_status?: string;
  history_coverage_status?: "complete" | "full" | "partial" | "single" | "unavailable" | string;
  history_state?: "full" | "partial" | "single";
  curve_status?: "full" | "partial" | "single" | string;
  coverage_class?: "full" | "partial" | "single" | string;
  coverage_day_count?: number;
  latest_live_price_cny?: number | null;
  latest_live_price_card_hours?: number | null;
  latest_live_observed_at?: string | null;
  latest_live_comparable_to_history?: boolean | null;
  quarantined_candle_count?: number | null;
  quarantined_prefix_count?: number | null;
  quarantined_tail_count?: number | null;
  quarantine_reason?: string | null;
  candles: MobileMarketCandle[];
};

export type MobileLatestMarket = {
  server_time: string;
  gpu_model: string;
  gpu_variant: string;
  summary: {
    median_price_cny: number | null;
    min_price_cny: number | null;
    max_price_cny: number | null;
    median_price_card_hours: number | null;
    min_price_card_hours: number | null;
    max_price_card_hours: number | null;
    sample_count: number;
    available_gpu_count: number;
    source_count: number;
    card_hour_rmb_rate: number;
  };
  items?: Array<{
    observed_at?: string | null;
    source_checked_at?: string | null;
  }>;
  requested_source_states: Record<string, string>;
  excluded_sources: string[];
};

export type MobileMarketSource = {
  source: string;
  source_name: string;
  enabled: boolean;
  status: string;
  sample_count: number;
  last_success_at: string | null;
  has_error: boolean;
  error_code: string | null;
};

export type MobileRegionalQuote = {
  region_code: string;
  region: string;
  median_price_cny: number | null;
  min_price_cny: number | null;
  max_price_cny: number | null;
  quote_sample_count: number;
  location_count: number;
  relative_to_lowest_pct: number | null;
  is_lowest: boolean;
  observed_at?: string | null;
};

export type MobileRegionalQuotes = {
  gpu_model: string;
  gpu_variant: string;
  region_count: number;
  source: "kai";
  billing_unit: "GPU_HOUR" | string;
  market_status: string;
  sample_semantics: "current_quote_observations_not_inventory" | string;
  regions: MobileRegionalQuote[];
};

export function getMobileMarketModels() {
  return apiRequest<{ server_time: string; items: MobileMarketModel[] }>(canonicalApiPath("/market/models"));
}

export function getMobileLatestMarket(model: MobileMarketModel) {
  return apiRequest<MobileLatestMarket>(canonicalApiPath(`/market/prices/latest?${kaiPricingQuery({
    model: model.gpu_model,
    variant: model.gpu_variant,
  })}`));
}

export function getMobileMarketCandles(model: MobileMarketModel, range: "24h" | "7d" | "30d" | "90d") {
  return apiRequest<MobileMarketCandles>(canonicalApiPath(`/market/prices/candles?${kaiPricingQuery({
    model: model.gpu_model,
    variant: model.gpu_variant,
    range,
    billing_mode: "ondemand",
  })}`));
}

export function getMobileMarketSources() {
  return apiRequest<{ server_time: string; items: MobileMarketSource[] }>(canonicalApiPath("/market/sources/status"));
}

export function getMobileRegionalQuotes(model: MobileMarketModel) {
  const query = new URLSearchParams({ model: model.gpu_model, variant: model.gpu_variant });
  return apiRequest<MobileRegionalQuotes>(canonicalApiPath(`/products/quote/regional?${query.toString()}`));
}
