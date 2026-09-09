import assert from "node:assert/strict";
import test from "node:test";

import { COMMUNITY_POST_MAX_LENGTH, communityShareText } from "../lib/community-ui.ts";

test("community composer uses the same 500 character limit as the apps", () => {
  assert.equal(COMMUNITY_POST_MAX_LENGTH, 500);
});

test("community share copy matches the app and includes the source", () => {
  assert.equal(
    communityShareText({ content: "  KAI 行情更新  ", source_url: "https://example.com/source" }),
    "KAI 行情更新\nhttps://example.com/source",
  );
  assert.equal(communityShareText({ content: "WOD 算力行情", source_key: "wod-market" }), "ZTW 算力行情");
  assert.equal(communityShareText({ content: "WOD 算力行情", source_key: "user-post" }), "WOD 算力行情");
  assert.equal(communityShareText({ content: "x".repeat(120) }).length, 100);
});
