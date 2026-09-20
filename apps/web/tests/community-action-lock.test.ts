import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { acquireCommunityAction, releaseCommunityAction } from "../lib/community-action-lock.ts";

test("community actions reject duplicate acquisition without blocking unrelated work", () => {
  const active = new Set<string>();

  assert.equal(acquireCommunityAction(active, "publish"), true);
  assert.equal(acquireCommunityAction(active, "publish"), false);
  assert.equal(acquireCommunityAction(active, "comment-7"), true);

  releaseCommunityAction(active, "publish");
  assert.equal(active.has("publish"), false);
  assert.equal(active.has("comment-7"), true);
  assert.equal(acquireCommunityAction(active, "publish"), true);
});

test("every asynchronous community action acquires and releases its own lock", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  const functionNames = ["publish", "like", "follow", "share", "submitComment"];

  functionNames.forEach((name, index) => {
    const start = feed.indexOf(`async function ${name}`);
    const end = index + 1 < functionNames.length ? feed.indexOf(`async function ${functionNames[index + 1]}`, start) : feed.indexOf("function submitSearch", start);
    const body = feed.slice(start, end);
    assert.ok(start >= 0);
    assert.match(body, /if \(!beginAction\(action\)\) return/);
    assert.match(body, /finally \{ finishAction\(action\); \}/);
  });

  assert.doesNotMatch(feed, /setBusy\(""\)|busy ===/);
  assert.match(feed, /busy\.has\("publish"\)/);
});
