import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download publishes the verified 1.2.1 APK", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.2\.1"/);
  assert.match(page, /\|\| "\/download\/wod\.apk"/);
  assert.match(page, /34\.2 MB/);
  assert.match(page, /461D0E5F4D3A4D421F9A2C9ECB7B5FDDE72CD5ED7A0E2250CD852BA0D555DE3C/);
  assert.match(header, /\|\| "\/download\/wod\.apk"/);
  assert.doesNotMatch(page, /APK 正在准备|MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
