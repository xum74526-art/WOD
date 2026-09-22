import assert from "node:assert/strict";
import test from "node:test";
import { assetStatusLabel } from "../lib/asset-status.ts";

const translate = (key: string, fallback: string) => ({
  "asset.status.holding": "Holding",
  "asset.status.running": "Running",
  "asset.status.expired": "Expired",
  "asset.status.sold": "Sold",
  "asset.status.used": "In use",
  "asset.status.completed": "Completed",
  "asset.status.canceled": "Canceled",
  "asset.status.pending": "Pending",
} as Record<string, string>)[key] || fallback;

test("active assets distinguish holding ownership from usage", () => {
  assert.equal(assetStatusLabel("active", "holding", translate), "Holding");
  assert.equal(assetStatusLabel("active", "usage", translate), "Running");
  assert.equal(assetStatusLabel("running", null, translate), "Running");
});

test("asset status codes are converted to user-facing labels", () => {
  assert.equal(assetStatusLabel("expired", null, translate), "Expired");
  assert.equal(assetStatusLabel("sold", "holding", translate), "Sold");
  assert.equal(assetStatusLabel("used", null, translate), "In use");
  assert.equal(assetStatusLabel("done", null, translate), "Completed");
  assert.equal(assetStatusLabel("canceled", null, translate), "Canceled");
  assert.equal(assetStatusLabel("unexpected_status", null, translate), "Pending");
});
