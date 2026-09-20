import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("Web sends an explicit like state and safely retries only the identical operation", () => {
  const api = fs.readFileSync(new URL("../lib/mobile-community-api.ts", import.meta.url), "utf8");
  const start = api.indexOf("export function setCommunityLike");
  const end = api.indexOf("export function setCommunityFollow", start);
  const flow = api.slice(start, end);

  assert.ok(start >= 0 && end > start);
  assert.match(flow, /setCommunityLike\(id: number, liked: boolean\)/);
  assert.match(flow, /body: JSON\.stringify\(\{ liked \}\)/);
  assert.match(flow, /return retryIdempotentMutationOnce\(submit\)/);
  assert.doesNotMatch(api, /toggleCommunityLike/);
});

test("Web snapshots the requested state and adopts only the server response", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  const start = feed.indexOf("async function like");
  const end = feed.indexOf("async function follow", start);
  const flow = feed.slice(start, end);
  const target = flow.indexOf("const targetLiked = !row.is_liked");
  const request = flow.indexOf("await setCommunityLike(row.id, targetLiked)");
  const apply = flow.indexOf("likes: result.likes, is_liked: result.liked");

  assert.ok(start >= 0);
  assert.match(flow, /if \(!beginAction\(action\)\) return/);
  assert.ok(target >= 0 && target < request);
  assert.ok(request < apply);
  assert.match(flow, /finally \{ finishAction\(action\); \}/);
});
