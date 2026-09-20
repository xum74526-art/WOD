export type MarketHistoryPoint = { date: string; median: number };

export type CompactMarketHistories = {
  historyDates: string[];
  historyValues: Array<Array<number | null>>;
};

export function compactMarketHistories(histories: MarketHistoryPoint[][]): CompactMarketHistories {
  const dateSet = new Set<string>();
  for (const history of histories) {
    const itemDates = new Set<string>();
    for (const point of history) {
      if (!point.date || !Number.isFinite(point.median) || point.median <= 0) {
        throw new Error("market_dashboard_invalid_history_point");
      }
      if (itemDates.has(point.date)) throw new Error("market_dashboard_duplicate_history_date");
      itemDates.add(point.date);
      dateSet.add(point.date);
    }
  }

  const historyDates = [...dateSet].sort((a, b) => b.localeCompare(a));
  const dateIndexes = new Map(historyDates.map((date, index) => [date, index]));
  const historyValues = histories.map((history) => {
    const values = new Array<number | null>(historyDates.length).fill(null);
    for (const point of history) {
      const index = dateIndexes.get(point.date);
      if (index == null) throw new Error("market_dashboard_history_date_missing");
      values[index] = point.median;
    }
    return values;
  });
  return { historyDates, historyValues };
}

export function expandMarketHistory(
  historyDates: string[],
  historyValues: Array<number | null>,
): MarketHistoryPoint[] {
  return historyDates.flatMap((date, index) => {
    const median = historyValues[index];
    return date && typeof median === "number" && Number.isFinite(median) && median > 0
      ? [{ date, median }]
      : [];
  });
}
