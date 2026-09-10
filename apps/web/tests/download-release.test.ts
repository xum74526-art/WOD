import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download publishes the verified 1.2.0 APK", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.2\.0"/);
  assert.match(page, /\|\| "\/download\/wod\.apk"/);
  assert.match(page, /28\.1 MB/);
  assert.match(page, /F8F04512D5EE1B4FA72ED47C96EAF336104B2957D472FF75CE1DA498066AC085/);
  assert.match(header, /\|\| "\/download\/wod\.apk"/);
  assert.doesNotMatch(page, /APK 正在准备|MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
