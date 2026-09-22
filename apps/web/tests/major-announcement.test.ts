import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function read(path: string) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("administrator can select a homepage major announcement", () => {
  const api = read("../lib/admin-audit-api.ts");
  const workspace = read("../components/admin-notification-workspace.tsx");

  assert.match(api, /"major_announcement" \| "system"/);
  assert.match(workspace, /major_announcement: "重大公告（首页展示）"/);
  assert.match(workspace, /公开显示在 Web 首页/);
});

test("public home renders the latest major announcement in an accessible modal", () => {
  const api = read("../lib/internal-api.ts");
  const banner = read("../components/major-announcement-banner.tsx");
  const home = read("../components/home-page-content.tsx");

  assert.match(api, /\/api\/v1\/canonical\/notifications\/major-announcement/);
  assert.ok(home.indexOf("<MajorAnnouncementBanner />") < home.indexOf('className="home-v2-hero"'));
  assert.match(banner, /getMajorAnnouncement\(\)/);
  assert.match(banner, /kai-major-announcement-dismissed:v2/);
  assert.match(banner, /notificationActionPath\(announcement\?\.action_url\)/);
  assert.match(banner, /role="dialog"/);
  assert.match(banner, /aria-modal="true"/);
  assert.match(banner, /majorAnnouncement\.acknowledge/);
  assert.match(banner, /document\.body\.style\.overflow = "hidden"/);
  assert.match(banner, /\.catch\(\(\) => \{/);
});
