import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("the web media proxy accepts canonical iPhone MOV upload paths", () => {
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const allowlist = "jpg|png|webp|mp4|mov|webm";

  assert.equal(adapter.split(allowlist).length - 1, 2);
});
