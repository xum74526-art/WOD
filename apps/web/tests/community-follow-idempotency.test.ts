import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("Web sends an explicit follow state and safely retries the identical operation", () => {
  const api = fs.readFileSync(new URL("../lib/mobile-community-api.ts", import.meta.url), "utf8");
  const start = api.indexOf("export function setCommunityFollow");
  const end = api.indexOf("export function getCommunityComments", start);
  const flow = api.slice(start, end);

  assert.ok(start >= 0);
  assert.match(flow, /setCommunityFollow\(id: number, following: boolean\)/);
  assert.match(flow, /body: JSON\.stringify\(\{ following \}\)/);
  assert.match(flow, /return retryIdempotentMutationOnce\(submit\)/);
  assert.doesNotMatch(api, /toggleCommunityFollow/);
});

test("Web locks follows by user and applies the server state to every matching post", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  const start = feed.indexOf("async function follow");
  const end = feed.indexOf("async function share", start);
  const flow = feed.slice(start, end);
  const target = flow.indexOf("const targetFollowing = !row.is_following");
  const request = flow.indexOf("await setCommunityFollow(row.user_id, targetFollowing)");
  const apply = flow.indexOf("item.user_id === row.user_id ? { ...item, is_following: result.following }");

  assert.ok(start >= 0);
  assert.match(flow, /const action = `follow-\$\{row\.user_id\}`/);
  assert.match(flow, /if \(!beginAction\(action\)\) return/);
  assert.ok(target >= 0 && target < request);
  assert.ok(request < apply);
  assert.match(flow, /finally \{ finishAction\(action\); \}/);
  assert.match(feed, /disabled=\{busy\.has\(`follow-\$\{row\.user_id\}`\)\}/);
});
