export type PublicMarketRankingItem = {
  gpu_model: string;
  gpu_variant: string;
  median_price_cny: number;
  median_price_card_hours: number;
  change_24h: number;
  available_gpu_count: number;
  source_count: number;
  sources: string[];
  history_day_count: number;
  history_point_count: number;
  market_status: string;
};

export type PublicMarketRanking = {
  data: PublicMarketRankingItem[];
  meta: { observed_at?: string; count?: number; source?: string };
};

export type InitialGpuTrend = {
  market: {
    gpu_model: string;
    gpu_slug: string;
    provider_count: number;
    history: Array<{
      date: string;
      median: number;
      open: number;
      high: number;
      low: number;
      close: number;
    }>;
  };
  updated_at: string;
};
