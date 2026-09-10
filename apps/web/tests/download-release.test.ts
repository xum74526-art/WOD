import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download publishes the verified 1.1.9 APK", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.1\.9"/);
  assert.match(page, /\|\| "\/download\/wod\.apk"/);
  assert.match(page, /28\.1 MB/);
  assert.match(page, /93BE2E80135BCCF6E084CBFEF5D76ECA30A135059F2AAB3B0A2FE32D750EBB0A/);
  assert.match(header, /\|\| "\/download\/wod\.apk"/);
  assert.doesNotMatch(page, /APK 正在准备|MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
