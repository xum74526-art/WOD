import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download stays closed until the new KAI星算 APK metadata is complete", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.2\.7"/);
  assert.match(page, /configuredAndroidApkUrl/);
  assert.match(page, /\/download\\\/suanlixingtu\\\.apk/);
  assert.match(page, /NEXT_PUBLIC_KAI_ANDROID_APK_SIZE\?\.trim\(\) \|\| ""/);
  assert.match(page, /NEXT_PUBLIC_KAI_ANDROID_APK_SHA256\?\.trim\(\)\.toUpperCase\(\) \|\| ""/);
  assert.match(page, /\^\[A-F0-9\]\{64\}\$/);
  assert.match(page, /androidReleaseReady \? configuredAndroidApkUrl : ""/);
  assert.match(page, /APK 正在准备/);
  assert.match(page, /androidApkSha256 \? <code>SHA-256:/);
  assert.doesNotMatch(page, /34\.2 MB|461D0E5F4D3A4D421F9A2C9ECB7B5FDDE72CD5ED7A0E2250CD852BA0D555DE3C/);
  assert.match(header, /configuredAndroidApkUrl/);
  assert.match(header, /mobileDownloadUrl = "https:\/\/wod\.kai\.com\/download"/);
  assert.match(header, /configuredAndroidApkSize/);
  assert.match(header, /configuredAndroidApkSha256/);
  assert.doesNotMatch(page, /MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
