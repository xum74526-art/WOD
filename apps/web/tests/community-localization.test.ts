import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const componentNames = ["community-feed.tsx", "article-comments.tsx", "community-video.tsx", "news-detail.tsx"];
const components = new Map(componentNames.map((name) => [name, readFileSync(new URL(`../components/${name}`, import.meta.url), "utf8")]));
const localeRoot = readFileSync(new URL("../components/locale-root.tsx", import.meta.url), "utf8");

test("community and news UI uses explicit translations and locale-aware dates", () => {
  for (const [name, source] of components) {
    assert.match(source, /useI18n\(\)/, `${name} should use the locale context`);
    assert.match(source, /dateLocale/, `${name} should format dates or numbers for the active locale`);
    assert.doesNotMatch(source, /toLocale(?:Date)?String\("zh-CN"/, `${name} should not force Simplified Chinese formatting`);
  }
});

test("every explicit community translation key has an English entry", () => {
  const keys = [...components.values()].flatMap((source) => [...source.matchAll(/\bt\("(community\.[^"]+)"/g)].map((match) => match[1]));
  assert.ok(keys.length > 0);
  for (const key of new Set(keys)) assert.match(localeRoot, new RegExp(`"${key.replaceAll(".", "\\.")}"\\s*:`), `missing English translation for ${key}`);
});

test("community service content is excluded from the legacy DOM translation bridge", () => {
  const feed = components.get("community-feed.tsx")!;
  const comments = components.get("article-comments.tsx")!;
  const video = components.get("community-video.tsx")!;
  const news = components.get("news-detail.tsx")!;

  assert.match(feed, /<p data-i18n-skip>\{content\}<\/p>/);
  assert.match(feed, /<span data-i18n-skip>\{row\.topic\}<\/span>/);
  assert.match(comments, /<p data-i18n-skip>\{comment\.content\}<\/p>/);
  assert.match(video, /<h1 data-i18n-skip>\{video\.title\}<\/h1><p data-i18n-skip>\{video\.summary\}<\/p>/);
  assert.match(news, /<h1 data-i18n-skip>\{article\.title\}<\/h1>/);
  assert.match(news, /data-i18n-skip dangerouslySetInnerHTML=\{\{ __html: article\.content \}\}/);
});
