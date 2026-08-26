import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const html = read("./index.html");
const script = read("./app.js");
const styles = read("./styles.css");
const showcaseStyles = read("./showcase.css");
const manifest = JSON.parse(read("./review-manifest.json"));

test("package is explicitly marked for static review", () => {
  assert.equal(manifest.label, "静态审核");
  assert.equal(manifest.type, "static");
  assert.equal(manifest.backendRequired, false);
  assert.equal(manifest.externalNetworkAccess, false);
  assert.match(html, /<meta name="review-mode" content="static-review" \/>/);
});

test("standalone entry uses only relative local assets", () => {
  assert.match(html, /href="\.\/styles\.css"/);
  assert.match(html, /href="\.\/showcase\.css"/);
  assert.match(html, /src="\.\/app\.js"/);
  assert.match(html, /src="\.\/assets\/kai-logo\.svg"/);
  assert.doesNotMatch(html, /(?:href|src)="\/info\//);
  assert.ok(fs.existsSync(new URL("./assets/kai-logo.svg", import.meta.url)));
  assert.ok(fs.existsSync(new URL("./.nojekyll", import.meta.url)));
  assert.ok(styles.length > 10_000);
  assert.ok(showcaseStyles.length > 5_000);
});

test("static review package never contacts a backend or external service", () => {
  const combined = html + script;
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /form-action 'none'/);
  assert.doesNotMatch(combined, /\bfetch\s*\(|XMLHttpRequest|axios|WebSocket|EventSource|sendBeacon/);
  assert.doesNotMatch(html, /<form[^>]+action=/);
});

test("approved production layout and safe copy are fixed in the package", () => {
  const combined = html + script + styles + showcaseStyles;
  assert.match(script, /^const showcaseMode = true;/);
  assert.match(html, /备案信息将在核准后公示/);
  assert.doesNotMatch(combined, /9103|noindex|XXXXXXXX|KAI Pricing|订购|订单|购买|供应商|结算/);
  assert.equal((html.match(/id="view-/g) ?? []).length, 6);
  assert.equal((script.match(/^    id: "/gm) ?? []).length, 6);
});
