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

test("web community uploads expose transfer progress and server processing separately", () => {
  const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
  const adapter = readFileSync(new URL("../lib/mobile-community-api.ts", import.meta.url), "utf8");
  const composer = readFileSync(new URL("../components/community-feed.tsx", import.meta.url), "utf8");

  assert.match(api, /request\.upload\.onprogress/);
  assert.match(api, /phase: "processing"/);
  assert.match(adapter, /apiUploadRequest/);
  assert.match(composer, /正在上传第 \$\{progress\.current\}\/\$\{progress\.total\} 个文件/);
  assert.match(composer, /服务器正在\$\{progress\.video \? "转换兼容视频" : "处理文件"\}/);
  assert.match(composer, /community-upload-progress/);
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
  assert.equal(communityShareText({ content: "WOD 算力行情", source_key: "wod-market" }), "ZTW 算力行情");
  assert.equal(communityShareText({ content: "WOD 算力行情", source_key: "user-post" }), "WOD 算力行情");
  assert.equal(communityShareText({ content: "x".repeat(120) }).length, 100);
});
