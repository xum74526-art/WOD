import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  readBoundedJsonBody,
  REGISTRATION_BODY_MAX_BYTES,
  RequestBodyTooLargeError,
} from "../lib/server/bounded-json-body.ts";

function jsonAtSize(bytes: number) {
  const prefix = '{"padding":"';
  const suffix = '"}';
  return `${prefix}${"x".repeat(bytes - prefix.length - suffix.length)}${suffix}`;
}

function streamedRequest(chunks: string[], headers: Record<string, string> = {}) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Request("https://wod.kai.com/api/v1/auth/password/register", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
    duplex: "half",
  } as RequestInit & { duplex: "half" });
}

test("bounded Web JSON reader accepts the exact registration ceiling", async () => {
  const raw = jsonAtSize(REGISTRATION_BODY_MAX_BYTES);
  const parsed = await readBoundedJsonBody(streamedRequest([raw.slice(0, 8_000), raw.slice(8_000)]), REGISTRATION_BODY_MAX_BYTES);
  assert.equal((parsed as { padding: string }).padding.length, REGISTRATION_BODY_MAX_BYTES - 14);
});

test("bounded Web JSON reader rejects a declared oversized request before reading", async () => {
  const request = streamedRequest(["{}"], { "Content-Length": String(REGISTRATION_BODY_MAX_BYTES + 1) });
  await assert.rejects(
    readBoundedJsonBody(request, REGISTRATION_BODY_MAX_BYTES),
    RequestBodyTooLargeError,
  );
  assert.equal(request.bodyUsed, false);
});

test("bounded Web JSON reader counts streamed bytes when Content-Length is absent", async () => {
  const request = streamedRequest(["x".repeat(8_000), "y".repeat(8_500)]);
  await assert.rejects(
    readBoundedJsonBody(request, REGISTRATION_BODY_MAX_BYTES),
    RequestBodyTooLargeError,
  );
});

test("Web BFF applies the bounded reader before adapting password registration", () => {
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  assert.match(adapter, /path === "auth\/password\/register"/);
  assert.match(adapter, /requestBody\(request, isRegistrationRequest \? REGISTRATION_BODY_MAX_BYTES : undefined\)/);
  assert.match(adapter, /apiError\(REGISTRATION_BODY_TOO_LARGE_MESSAGE, 413, "payload_too_large"\)/);
});
