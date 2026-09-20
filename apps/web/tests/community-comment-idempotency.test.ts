import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  communityCommentIntentSignature,
  ensureCommunityCommentIntent,
} from "../lib/web-business-contract.ts";

test("Web comment retries reuse one request id until the post or trimmed content changes", () => {
  let sequence = 0;
  const createUuid = () => `12345678-1234-1234-1234-${String(++sequence).padStart(12, "0")}`;
  const signature = communityCommentIntentSignature(7, "same comment");
  const first = ensureCommunityCommentIntent(null, signature, createUuid);
  const retry = ensureCommunityCommentIntent(first, signature, createUuid);

  assert.equal(retry.requestId, first.requestId);
  assert.match(first.requestId, /^web-comment-/);
  assert.equal(sequence, 1);

  const changedContent = ensureCommunityCommentIntent(
    retry,
    communityCommentIntentSignature(7, "edited comment"),
    createUuid,
  );
  assert.notEqual(changedContent.requestId, first.requestId);

  const changedPost = ensureCommunityCommentIntent(
    changedContent,
    communityCommentIntentSignature(8, "edited comment"),
    createUuid,
  );
  assert.notEqual(changedPost.requestId, changedContent.requestId);

  const afterSuccess = ensureCommunityCommentIntent(null, signature, createUuid);
  assert.notEqual(afterSuccess.requestId, first.requestId);
  assert.equal(sequence, 4);

  const editedWhileInFlight = communityCommentIntentSignature(7, "edited while in flight");
  assert.notEqual(editedWhileInFlight, first.signature);
  const restoredWhileInFlight = communityCommentIntentSignature(7, "same comment");
  assert.equal(restoredWhileInFlight, first.signature);
  const afterRestoredSuccess = ensureCommunityCommentIntent(null, restoredWhileInFlight, createUuid);
  assert.notEqual(afterRestoredSuccess.requestId, first.requestId);
});

test("Web comment API sends one stable request id and opts into one uncertain retry", () => {
  const api = fs.readFileSync(new URL("../lib/mobile-community-api.ts", import.meta.url), "utf8");
  const start = api.indexOf("export function createCommunityComment");
  const flow = api.slice(start);

  assert.ok(start >= 0);
  assert.match(flow, /createCommunityComment\(id: number, content: string, clientRequestId: string\)/);
  assert.match(flow, /JSON\.stringify\(\{ content, client_request_id: clientRequestId \}\)/);
  assert.match(flow, /return retryIdempotentMutationOnce\(submit\)/);
  assert.match(api, /post_comments\?: number/);
});

test("Web comment submission preserves changed drafts and upserts the authoritative response", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  const start = feed.indexOf("async function submitComment");
  const end = feed.indexOf("function submitSearch", start);
  const flow = feed.slice(start, end);

  assert.ok(start >= 0 && end > start);
  assert.match(flow, /const value = \(commentDrafts\[id\] \|\| ""\)\.trim\(\)/);
  assert.match(flow, /if \(!beginAction\(action\)\) return/);
  assert.match(flow, /pendingCommentIntents\.current\.set\(id, intent\)/);
  assert.match(flow, /await createCommunityComment\(id, value, intent\.requestId\)/);
  assert.match(flow, /pendingCommentIntents\.current\.get\(id\) === intent[\s\S]*pendingCommentIntents\.current\.delete\(id\)[\s\S]*if \(draftStillMatches\)/);
  assert.match(flow, /currentComments\.filter\(\(item\) => item\.id !== result\.id\)/);
  assert.match(flow, /typeof result\.post_comments === "number"/);
  assert.match(flow, /postComments \?\? item\.comments \+ \(knownComment \? 0 : 1\)/);
  assert.match(flow, /finally \{ finishAction\(action\); \}/);
  assert.equal(flow.match(/pendingCommentIntents\.current\.delete\(id\)/g)?.length, 1);
  assert.doesNotMatch(flow, /await getCommunityComments|comments: next\.length/);
  const updateStart = feed.indexOf("function updateCommentDraft");
  const updateEnd = feed.indexOf("async function publish", updateStart);
  assert.doesNotMatch(feed.slice(updateStart, updateEnd), /pendingCommentIntents/);
});
