import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("community picker validates the complete browser selection before storing it", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  const selectionStart = feed.indexOf("const selected = Array.from(event.currentTarget.files || [])");
  const validationStart = feed.indexOf("communityMediaUploadError(selected)", selectionStart);
  const storeStart = feed.indexOf("setFiles(selected)", validationStart);

  assert.ok(selectionStart >= 0);
  assert.ok(validationStart > selectionStart);
  assert.ok(storeStart > validationStart);
  assert.doesNotMatch(feed.slice(selectionStart, storeStart), /\.slice\(0, 9\)/);
});
