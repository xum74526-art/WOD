import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("the public image attribution page exposes all Commons works and direct-rights notice", () => {
  const page = read("../app/image-attributions/page.tsx");
  const content = read("../app/image-attributions/image-attributions-content.tsx");
  const footer = read("../components/site-footer.tsx");

  for (const asset of ["RTX2060.jpg", "RTX3070.jpg", "RTX4070.jpg", "RTX5060Ti.jpg", "RTX5070.jpg", "RTX5080.jpg"]) {
    assert.match(content, new RegExp(asset.replace(".", "\\.")));
  }
  for (const author of ["Mr ATM", "TheStriker", "Jacek Halicki", "FreeMediaKid!", "Striker9498", "XD7006"]) {
    assert.match(content, new RegExp(author.replace("!", "\\!")));
  }
  assert.equal((content.match(/sourceUrl: "https:/g) || []).length, 6);
  assert.equal((content.match(/licenseUrl: "https:/g) || []).length, 6);
  assert.match(content, /直接使用授权/);
  assert.match(content, /directly licensed for use/);
  assert.match(content, /B100 当前复用 H200/);
  assert.match(content, /B100 currently reuses the H200/);
  assert.doesNotMatch(content, /B100、B200/);
  assert.doesNotMatch(content, /B100, B200/);
  assert.match(content, /toTraditionalChinese/);
  assert.match(page, /"zh-Hant"/);
  assert.match(page, /"zh-Hans"/);
  assert.match(page, /en:/);
  assert.match(footer, /href="\/image-attributions"/);
});
