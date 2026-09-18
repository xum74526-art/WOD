import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("first-review web composer has no usable media picker or media payload", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(feed, /type="file"|accept="[^\"]*(?:image|video)/);
  assert.doesNotMatch(feed, /uploadCommunityMedia|uploadCommunityMediaBatch/);
  const publishStart = feed.indexOf("async function publish(");
  const publishEnd = feed.indexOf("\n  async function like", publishStart);
  const publish = feed.slice(publishStart, publishEnd);
  assert.match(publish, /createCommunityPost\(\{/);
  assert.doesNotMatch(publish, /images:|video:|video_duration:/);
});
