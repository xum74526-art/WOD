import assert from "node:assert/strict";
import test from "node:test";

import {
  COMMUNITY_IMAGE_MAX_BYTES,
  COMMUNITY_MEDIA_LIMIT_TEXT,
  COMMUNITY_POST_MAX_LENGTH,
  COMMUNITY_VIDEO_MAX_BYTES,
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
  assert.equal(COMMUNITY_IMAGE_MAX_BYTES, 5 * 1024 * 1024);
  assert.equal(COMMUNITY_VIDEO_MAX_BYTES, 20 * 1024 * 1024);
  assert.equal(COMMUNITY_MEDIA_LIMIT_TEXT, "图片最大 5MB，视频最大 20MB");
});

test("community video validation accepts the exact byte limit and detects extension fallback", () => {
  assert.equal(communityMediaUploadError([
    { name: "clip.mp4", type: "video/mp4", size: COMMUNITY_VIDEO_MAX_BYTES },
  ]), "");
  assert.equal(isCommunityVideoFile({ name: "clip.webm", type: "", size: 1 }), true);
  assert.match(communityMediaUploadError([
    { name: "clip.webm", type: "", size: COMMUNITY_VIDEO_MAX_BYTES + 1 },
  ]), /不能超过 20MB/);
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
