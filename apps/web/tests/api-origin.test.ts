import assert from "node:assert/strict";
import test from "node:test";

import { resolveApiOrigin } from "../lib/server/api-origin.ts";
import { canonicalApiPath } from "../lib/canonical-api.ts";

test("production requires an explicit canonical API origin", () => {
  assert.throws(() => resolveApiOrigin({ NODE_ENV: "production" }), /API_ORIGIN is required/);
});

test("canonical API origin is normalized and must be HTTPS", () => {
  assert.equal(resolveApiOrigin({ NODE_ENV: "production", API_ORIGIN: "https://wod.kai.com/" }), "https://wod.kai.com");
  assert.throws(
    () => resolveApiOrigin({ NODE_ENV: "production", API_ORIGIN: "http://wod.kai.com" }),
    /must use HTTPS/,
  );
});

test("HTTP is restricted to an explicitly allowed local origin", () => {
  assert.equal(resolveApiOrigin({
    NODE_ENV: "development",
    API_ORIGIN: "http://127.0.0.1:8000",
    API_ALLOW_INSECURE_HTTP: "true",
  }), "http://127.0.0.1:8000");
  assert.throws(() => resolveApiOrigin({
    NODE_ENV: "development",
    API_ORIGIN: "http://example.com",
    API_ALLOW_INSECURE_HTTP: "true",
  }), /must use HTTPS/);
  assert.equal(resolveApiOrigin({
    NODE_ENV: "production",
    API_ORIGIN: "http://127.0.0.1:8000",
    API_ALLOW_INSECURE_HTTP: "true",
  }), "http://127.0.0.1:8000");
});

test("origin rejects credentials, paths, queries, and fragments", () => {
  for (const origin of [
    "https://user:secret@wod.kai.com",
    "https://wod.kai.com/api",
    "https://wod.kai.com?debug=1",
    "https://wod.kai.com#fragment",
  ]) {
    assert.throws(() => resolveApiOrigin({ NODE_ENV: "production", API_ORIGIN: origin }), /only the backend origin/);
  }
});

test("Web canonical paths stay same-origin and reject traversal", () => {
  assert.equal(canonicalApiPath("/market/models"), "/api/v1/canonical/market/models");
  assert.throws(() => canonicalApiPath("market/models"), /safe absolute paths/);
  assert.throws(() => canonicalApiPath("/../admin"), /safe absolute paths/);
  assert.throws(() => canonicalApiPath("//evil.example/api"), /safe absolute paths/);
});
