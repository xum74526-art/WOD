import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("official Android download publishes the verified 1.0.5 APK", () => {
  const page = fs.readFileSync(new URL("../app/download/page.tsx", import.meta.url), "utf8");
  const locale = fs.readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

  assert.match(page, /const androidVersion = "1\.0\.5"/);
  assert.match(page, /\|\| "\/download\/wod\.apk"/);
  assert.match(page, /27\.7 MB/);
  assert.match(page, /005B06BBC520F6FDFCE2FEF912009FFB1E177ABB1AF0728140744B7A5B869B7E/);
  assert.doesNotMatch(page, /APK 正在准备|MOBILE \/ 1\.0\.3/);
  assert.match(locale, /"大小": "Size"/);
  assert.match(locale, /"待发布": "Pending release"/);
});
