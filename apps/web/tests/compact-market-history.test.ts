import assert from "node:assert/strict";
import test from "node:test";

import { compactMarketHistories, expandMarketHistory, type MarketHistoryPoint } from "../lib/compact-market-history.ts";

test("compact market histories preserve every real point and missing date", () => {
  const histories: MarketHistoryPoint[][] = [
    [
      { date: "2026-03-10", median: 5.12 },
      { date: "2026-03-09", median: 5.08 },
      { date: "2026-03-07", median: 5.01 },
    ],
    [
      { date: "2026-03-09", median: 24.75 },
      { date: "2024-02-29", median: 23.9 },
    ],
    [],
  ];

  const compact = compactMarketHistories(histories);
  assert.deepEqual(compact.historyDates, ["2026-03-10", "2026-03-09", "2026-03-07", "2024-02-29"]);
  assert.deepEqual(
    compact.historyValues.map((values) => expandMarketHistory(compact.historyDates, values)),
    histories,
  );
});

test("compact market histories reject duplicate dates instead of silently overwriting prices", () => {
  assert.throws(() => compactMarketHistories([[
    { date: "2026-09-10", median: 5.1 },
    { date: "2026-09-10", median: 5.2 },
  ]]), /market_dashboard_duplicate_history_date/);
});

test("compact market histories keep the initial payload within its regression budget", () => {
  const histories = Array.from({ length: 72 }, (_, modelIndex) => Array.from({ length: 90 }, (_, dayIndex) => ({
    date: new Date(Date.UTC(2026, 8, 10 - dayIndex)).toISOString().slice(0, 10),
    median: 4 + modelIndex / 10 + dayIndex / 1000,
  })));
  const objectBytes = Buffer.byteLength(JSON.stringify(histories));
  const compact = compactMarketHistories(histories);
  const compactBytes = Buffer.byteLength(JSON.stringify(compact));

  assert.ok(compactBytes < 100_000, `compact history payload grew to ${compactBytes} bytes`);
  assert.ok(compactBytes < objectBytes * 0.45, `compact payload ${compactBytes} is too close to ${objectBytes}`);
  assert.equal(compact.historyValues.length, 72);
  assert.equal(compact.historyDates.length, 90);
});
