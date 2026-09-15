import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  ApiError,
  isUncertainApiFailure,
  retryIdempotentMutationOnce,
} from "../lib/api.ts";

test("only transport and gateway failures are classified as uncertain", () => {
  assert.equal(isUncertainApiFailure(new Error("network")), true);
  for (const status of [408, 502, 503, 504]) {
    assert.equal(isUncertainApiFailure(new ApiError("temporary", undefined, status)), true);
  }
  for (const status of [400, 401, 403, 404, 409, 422, 429, 500]) {
    assert.equal(isUncertainApiFailure(new ApiError("final", undefined, status)), false);
  }
});

test("an idempotent mutation retries one uncertain failure with the same operation", async () => {
  let calls = 0;
  const result = await retryIdempotentMutationOnce(async () => {
    calls += 1;
    if (calls === 1) throw new ApiError("gateway timeout", undefined, 504);
    return { id: 17 };
  });

  assert.deepEqual(result, { id: 17 });
  assert.equal(calls, 2);
});

test("a deterministic API error is not retried", async () => {
  const expected = new ApiError("conflict", "QUOTE_CONFLICT", 409);
  let calls = 0;

  await assert.rejects(
    retryIdempotentMutationOnce(async () => {
      calls += 1;
      throw expected;
    }),
    (reason) => reason === expected,
  );
  assert.equal(calls, 1);
});

test("two uncertain failures stop after the single recovery attempt", async () => {
  const finalFailure = new Error("connection lost again");
  let calls = 0;

  await assert.rejects(
    retryIdempotentMutationOnce(async () => {
      calls += 1;
      if (calls === 1) throw new Error("connection lost");
      throw finalFailure;
    }),
    (reason) => reason === finalFailure,
  );
  assert.equal(calls, 2);
});

test("Web retries only new quote creation and snapshots the submitted terms", () => {
  const workspace = fs.readFileSync(new URL("../components/mobile-buy-request-workspace.tsx", import.meta.url), "utf8");
  const flow = workspace.slice(workspace.indexOf("async function submitQuote"), workspace.indexOf("async function selectQuote"));

  assert.match(flow, /const requestId = detail\.request\.id;/);
  assert.match(flow, /const input = quoteInput\(\);/);
  assert.match(flow, /const quoteId = editingQuoteId;/);
  assert.match(flow, /if \(quoteId !== null\) await counterMobileBuyQuote\(requestId, quoteId, input\);/);
  assert.match(flow, /else await retryIdempotentMutationOnce\(\(\) => createMobileBuyQuote\(requestId, input\)\);/);
  assert.doesNotMatch(flow, /retryIdempotentMutationOnce\([^\n]*counterMobileBuyQuote/);
});
