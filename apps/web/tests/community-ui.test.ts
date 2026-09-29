import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  COMMUNITY_IMAGE_MAX_BYTES,
  COMMUNITY_MEDIA_LIMIT_TEXT,
  COMMUNITY_MEDIA_MAX_FILES,
  COMMUNITY_POST_MAX_LENGTH,
  COMMUNITY_VIDEO_MAX_BYTES,
  COMMUNITY_VIDEO_MAX_DURATION_SECONDS,
  communityMediaUploadError,
  communityPostContent,
  communityPostTopic,
  communityShareText,
  isCommunityImageFile,
  isCommunityVideoFile,
  uploadCommunityMediaBatch,
} from "../lib/community-ui.ts";

test("community composer uses the same 500 character limit as the apps", () => {
  assert.equal(COMMUNITY_POST_MAX_LENGTH, 500);
});

test("community composer shows the shared image and video limits", () => {
  assert.equal(COMMUNITY_MEDIA_MAX_FILES, 9);
  assert.equal(COMMUNITY_IMAGE_MAX_BYTES, 5 * 1024 * 1024);
  assert.equal(COMMUNITY_VIDEO_MAX_BYTES, 20 * 1024 * 1024);
  assert.equal(COMMUNITY_VIDEO_MAX_DURATION_SECONDS, 300);
  assert.equal(COMMUNITY_MEDIA_LIMIT_TEXT, "图片最多 9 张且单张最大 5MB；视频最长 5 分钟、最大 20MB，上传后统一转换为兼容 MP4");
});

test("community media selection rejects more than nine files instead of silently truncating", () => {
  const files = Array.from({ length: COMMUNITY_MEDIA_MAX_FILES }, (_, index) => ({
    name: `${index}.jpg`,
    type: "image/jpeg",
    size: 100,
  }));

  assert.equal(communityMediaUploadError(files), "");
  assert.match(communityMediaUploadError([...files, { name: "extra.jpg", type: "image/jpeg", size: 100 }]), /最多选择 9 个文件/);
});

test("community video validation accepts the exact byte limit and detects extension fallback", () => {
  assert.equal(communityMediaUploadError([
    { name: "clip.mp4", type: "video/mp4", size: COMMUNITY_VIDEO_MAX_BYTES },
  ]), "");
  assert.equal(isCommunityVideoFile({ name: "clip.webm", type: "", size: 1 }), true);
  assert.equal(isCommunityVideoFile({ name: "IPHONE.MOV", type: "", size: 1 }), true);
  assert.match(communityMediaUploadError([
    { name: "clip.webm", type: "", size: COMMUNITY_VIDEO_MAX_BYTES + 1 },
  ]), /不能超过 20MB/);
});

test("web video normalization waits longer than the backend transcode ceiling", () => {
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const client = readFileSync(new URL("../lib/server/canonical-api-client.ts", import.meta.url), "utf8");
  assert.match(adapter, /"\/api\/community\/media\/upload",[\s\S]*240_000/);
  assert.match(client, /timeoutMs: number = 60_000/);
  assert.match(client, /AbortSignal\.timeout\(timeoutMs\)/);
});

test("web first-review composer is text-only while the dormant upload adapter remains bounded", () => {
  const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
  const adapter = readFileSync(new URL("../lib/mobile-community-api.ts", import.meta.url), "utf8");
  const composer = readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");

  assert.match(api, /request\.upload\.onprogress/);
  assert.match(api, /phase: "processing"/);
  assert.match(adapter, /apiUploadRequest/);
  assert.doesNotMatch(composer, /apiUploadRequest|uploadCommunityMedia|community-upload-progress/);
  assert.doesNotMatch(composer, /type="file"|accept="[^\"]*(?:image|video)/);
});

test("web comment menus match the apps' comment and author safety controls", () => {
  const feed = readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");
  const locale = readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(feed, /reportCommunityContent\("comment", commentItem\.id\)/);
  assert.match(feed, /reportCommunityContent\("user", commentItem\.user_id\)/);
  assert.match(feed, /setCommunityBlock\(commentItem\.user_id, true\)/);
  assert.match(feed, /onReportCommentUser=\{\(post, item\) => void reportCommentUser\(post, item\)\}/);
  assert.match(feed, /onBlockCommentUser=\{\(post, item\) => void blockCommentUser\(post, item\)\}/);
  assert.match(locale, /"community\.feed\.reportUser": "Report user"/);
  assert.match(locale, /"community\.feed\.reportUserConfirm": "Report this user\?/);
});

test("community image validation accepts the exact byte limit and detects MIME or extension", () => {
  assert.equal(communityMediaUploadError([
    { name: "photo.png", type: "image/png", size: COMMUNITY_IMAGE_MAX_BYTES },
  ]), "");
  assert.equal(isCommunityImageFile({ name: "PHOTO.JPEG", type: "", size: 1 }), true);
  assert.match(communityMediaUploadError([
    { name: "unknown", type: "image/webp", size: COMMUNITY_IMAGE_MAX_BYTES + 1 },
  ]), /不能超过 5MB/);
  assert.match(communityMediaUploadError([
    { name: "photo.jpg", type: "", size: COMMUNITY_IMAGE_MAX_BYTES + 1 },
  ]), /不能超过 5MB/);
});

test("an oversized video aborts the whole media batch before any upload starts", async () => {
  let uploadCalls = 0;
  const files = [
    { name: "photo.png", type: "image/png", size: 100 },
    { name: "large.mp4", type: "video/mp4", size: COMMUNITY_VIDEO_MAX_BYTES + 1 },
  ] as File[];

  await assert.rejects(
    uploadCommunityMediaBatch(files, async () => { uploadCalls += 1; return "uploaded"; }),
    /不能超过 20MB/,
  );
  assert.equal(uploadCalls, 0);
});

test("an oversized image aborts the whole media batch before any upload starts", async () => {
  let uploadCalls = 0;
  const files = [
    { name: "clip.mp4", type: "video/mp4", size: 100 },
    { name: "large.webp", type: "image/webp", size: COMMUNITY_IMAGE_MAX_BYTES + 1 },
  ] as File[];

  await assert.rejects(
    uploadCommunityMediaBatch(files, async () => { uploadCalls += 1; return "uploaded"; }),
    /不能超过 5MB/,
  );
  assert.equal(uploadCalls, 0);
});

test("community share copy matches the app and includes the source", () => {
  assert.equal(
    communityShareText({ content: "  KAI 行情更新  ", source_url: "https://example.com/source" }),
    "KAI 行情更新\nhttps://example.com/source",
  );
  assert.equal(communityShareText({ content: "WOD 算力行情", source_key: "wod-market" }), "KAI星算 算力行情");
  assert.equal(communityShareText({ content: "WOD 算力行情", source_key: "user-post" }), "WOD 算力行情");
  assert.equal(communityShareText({ content: "x".repeat(120) }).length, 100);
});

test("platform-owned community copy uses the selected language without rewriting user posts", () => {
  const currencyConfig = {
    base_currency: "CNY" as const,
    settlement_currency: "CNY" as const,
    fraction_digits: 3 as const,
    card_hour_cny_rate: 1,
    rates: { CNY: 1, HKD: 1.08, USD: 0.14 },
    rate_mode: "daily_reference" as const,
    rate_source: "TEST",
    rate_date: "2026-09-28",
    rates_stale: false,
    conversion_scope: "display_only" as const,
  };
  const internal = {
    content: "RTX4090 今日算力观察\n\n北美当前参考价为 ¥5.04/GPU小时。",
    content_en: "RTX4090 Daily Compute Snapshot\n\nThe current reference price in 北美 is CNY ¥5.04 per GPU-hour. KAI星算 market data.",
    topic: "算力行情",
    topic_en: "Compute Market",
    origin: "internal",
    source_key: "wod-market",
  };
  assert.equal(
    communityPostContent(internal, "en", currencyConfig),
    "RTX4090 Daily Compute Snapshot\n\nThe current reference price in North America is US$0.706/GPU-hour. KAI Star Market data.",
  );
  assert.equal(
    communityPostContent(internal, "zh-Hans", currencyConfig),
    "RTX4090 今日算力观察\n\n北美当前参考价为 ¥5.040/GPU小时。",
  );
  assert.equal(
    communityPostContent(internal, "zh-Hant", currencyConfig),
    "RTX4090 今日算力觀察\n\n北美當前參考價為 HK$5.443/GPU小時。",
  );
  assert.equal(communityPostTopic(internal, "en"), "Compute Market");
  assert.equal(
    communityShareText({ ...internal, source_url: "https://example.com/source" }, "en", currencyConfig),
    "RTX4090 Daily Compute Snapshot\n\nThe current reference price in North America is US$0.706/GPU-hour. K\nhttps://example.com/source",
  );

  const userPost = { content: "北美用戶原文", origin: "user", source_key: null };
  assert.equal(communityPostContent(userPost, "en"), "北美用戶原文");
  assert.equal(communityPostContent(userPost, "zh-Hant"), "北美用戶原文");

  const legacy = { ...internal, content: "北美参考价为 5.04 卡时/h。", content_en: "North America is 5.04 CH/h." };
  assert.equal(communityPostContent(legacy, "en", currencyConfig), "North America is US$0.707/GPU-hour.");
});
