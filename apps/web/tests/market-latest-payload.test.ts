import assert from "node:assert/strict";
import test from "node:test";

import { isValidMarketLatestPayload } from "../lib/market-latest-payload.ts";

function payload(overrides: Record<string, unknown> = {}) {
  return {
    server_time: "2026-09-11T09:00:00Z",
    next_refresh_in: 300,
    gpu_model: "H100",
    gpu_variant: "80GB",
    summary: {
      median_price_card_hours: 24.8,
      sample_count: 38,
      card_hour_rmb_rate: 1.002,
    },
    items: [],
    requested_source_states: { kai: "live" },
    excluded_sources: [],
    ...overrides,
  };
}

const h100 = { model: "H100", variant: "80GB" };

test("latest payload accepts a valid quote, an empty quote, and future fields", () => {
  assert.equal(isValidMarketLatestPayload(payload({ future_field: true }), h100), true);
  assert.equal(isValidMarketLatestPayload(payload({
    summary: {
      median_price_card_hours: null,
      sample_count: 0,
      card_hour_rmb_rate: 1.002,
    },
  }), h100), true);
});

test("latest payload rejects missing, non-object, and malformed quote structures", () => {
  for (const value of [undefined, null, [], "not-json", {}, payload({ summary: null }), payload({ items: null })]) {
    assert.equal(isValidMarketLatestPayload(value, h100), false);
  }
  for (const price of [undefined, "24.8", 0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(isValidMarketLatestPayload(payload({
      summary: { median_price_card_hours: price, sample_count: 1, card_hour_rmb_rate: 1.002 },
    }), h100), false);
  }
  assert.equal(isValidMarketLatestPayload(payload({
    summary: { median_price_card_hours: 24.8, sample_count: -1, card_hour_rmb_rate: 1.002 },
  }), h100), false);
  assert.equal(isValidMarketLatestPayload(payload({
    summary: { median_price_card_hours: 24.8, sample_count: 1, card_hour_rmb_rate: 0 },
  }), h100), false);
});

test("latest payload validates semantic GPU identity without rejecting backend aliases", () => {
  assert.equal(isValidMarketLatestPayload(payload({ gpu_model: "RTX4090", gpu_variant: "24GB" }), {
    model: "NVIDIA GeForce RTX 4090",
    variant: "24 GB",
  }), true);
  assert.equal(isValidMarketLatestPayload(payload({ gpu_model: "H200", gpu_variant: "141GB" }), {
    model: "H200",
    variant: "140GB",
  }), true);
  assert.equal(isValidMarketLatestPayload(payload({ gpu_model: "H100", gpu_variant: "24GB" }), {
    model: "H100",
    variant: "24.5GB",
  }), true);
  assert.equal(isValidMarketLatestPayload(payload({ gpu_model: "A100", gpu_variant: "80GB" }), h100), false);
  assert.equal(isValidMarketLatestPayload(payload({ gpu_variant: "94GB" }), h100), false);
  assert.equal(isValidMarketLatestPayload(payload({ gpu_variant: "94GB" }), {
    model: "H100",
    variant: null,
  }), true);
  assert.equal(isValidMarketLatestPayload(payload({
    gpu_model: "Future GPU",
    gpu_variant: "",
    summary: { median_price_card_hours: null, sample_count: 0, card_hour_rmb_rate: 1.002 },
  }), {
    model: "future_gpu",
    variant: "not-a-memory-variant",
  }), true);
});
