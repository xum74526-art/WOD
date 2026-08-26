import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const html = read("./index.html");
const script = read("./app.js");
const styles = read("./styles.css");
const showcaseStyles = read("./showcase.css");
const manifest = JSON.parse(read("./review-manifest.json"));
const vercelConfig = JSON.parse(read("./vercel.json"));

test("package is explicitly marked for static review", () => {
  assert.equal(manifest.label, "静态审核");
  assert.equal(manifest.type, "static");
  assert.equal(manifest.backendRequired, false);
  assert.equal(manifest.externalNetworkAccess, false);
  assert.equal(manifest.reviewUrl, "https://static-review.vercel.app");
  assert.match(html, /<meta name="review-mode" content="static-review" \/>/);
  assert.equal(vercelConfig.headers[0].headers.find((header) => header.key === "X-Frame-Options")?.value, "DENY");
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
  assert.match(html, /粤ICP备案号待提供/);
  assert.match(html, /粤公网安备号待提供/);
  assert.match(html, /<span aria-hidden="true">\|<\/span>/);
  assert.doesNotMatch(combined, /9103|noindex|XXXXXXXX|备案信息将在核准后公示|KAI Pricing|订购|订单|购买|供应商|结算/);
  assert.equal((html.match(/id="view-/g) ?? []).length, 6);
  assert.equal((script.match(/^    id: "/gm) ?? []).length, 6);
});
