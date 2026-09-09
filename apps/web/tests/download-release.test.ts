import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download publishes the verified 1.1.7 APK", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.1\.7"/);
  assert.match(page, /\|\| "\/download\/wod\.apk"/);
  assert.match(page, /27\.6 MB/);
  assert.match(page, /4A1AF160E41D477FB6733475C1F30387148EEA072DE1B2AD8A08F91A3ED417D4/);
  assert.doesNotMatch(page, /APK 正在准备|MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
