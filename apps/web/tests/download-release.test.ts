import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download publishes the verified 1.0.16 APK", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.0\.16"/);
  assert.match(page, /\|\| "\/download\/wod\.apk"/);
  assert.match(page, /27\.8 MB/);
  assert.match(page, /2592356B0028479EB0C9579E2990ACE6E68CDF8BF4BD6EEF4A7CAD1BC2EEE45B/);
  assert.doesNotMatch(page, /APK 正在准备|MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
