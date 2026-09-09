import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("community comment drafts stay scoped to their own post", () => {
  const feed = fs.readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");

  assert.match(feed, /useState<Record<number, string>>\(\{\}\)/);
  assert.match(feed, /const value = \(commentDrafts\[id\] \|\| ""\)\.trim\(\)/);
  assert.match(feed, /setCommentDrafts\(\(drafts\) => \{[\s\S]*delete next\[id\][\s\S]*return next/);
  assert.match(feed, /comment=\{commentDrafts\[row\.id\] \|\| ""\}/);
  assert.match(feed, /onCommentChange=\{\(value\) => setCommentDrafts\(\(drafts\) => \(\{ \.\.\.drafts, \[row\.id\]: value \}\)\)\}/);
  assert.doesNotMatch(feed, /const \[comment, setComment\]/);
});
