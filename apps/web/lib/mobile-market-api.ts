import { apiRequest } from "@/lib/api";

const mobilePath = (path: string) => `/api/v1/mobile${path}`;

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
  sample_count: number;
  observation_count: number;
  sources: string[];
};

export type MobileMarketCandles = {
  server_time: string;
  gpu_model: string;
  gpu_variant: string;
  range: string;
  method: "observed_source_median_ohlc";
  is_interpolated: false;
  history_status?: string;
  latest_live_price_cny?: number | null;
  latest_live_observed_at?: string | null;
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
    sample_count: number;
    available_gpu_count: number;
    source_count: number;
  };
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

function query(input: Record<string, string>) {
  return new URLSearchParams(input).toString();
}

export function getMobileMarketModels() {
  return apiRequest<{ server_time: string; items: MobileMarketModel[] }>(mobilePath("/market/models"));
}

export function getMobileLatestMarket(model: MobileMarketModel) {
  return apiRequest<MobileLatestMarket>(mobilePath(`/market/prices/latest?${query({
    model: model.gpu_model,
    variant: model.gpu_variant,
    sources: model.sources.join(","),
  })}`));
}

export function getMobileMarketCandles(model: MobileMarketModel, range: "7d" | "30d") {
  return apiRequest<MobileMarketCandles>(mobilePath(`/market/prices/candles?${query({
    model: model.gpu_model,
    variant: model.gpu_variant,
    range,
    sources: model.sources.join(","),
    billing_mode: "ondemand",
  })}`));
}

export function getMobileMarketSources() {
  return apiRequest<{ server_time: string; items: MobileMarketSource[] }>(mobilePath("/market/sources/status"));
}
