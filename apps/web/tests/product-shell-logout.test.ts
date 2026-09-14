import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("workspace sign-out clears the server session before replacing the page", () => {
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const logoutStart = shell.indexOf("async function logout() {");
  const logoutEnd = shell.indexOf("\n  }", logoutStart);
  const flow = shell.slice(logoutStart, logoutEnd);

  assert.ok(logoutStart >= 0);
  assert.match(flow, /await logoutCurrentUser\(\)/);
  assert.ok(flow.indexOf("await logoutCurrentUser()") < flow.indexOf('window.location.replace("/login")'));
  assert.match(flow, /catch \{[\s\S]*finally \{[\s\S]*window\.location\.replace\("\/login"\)/);
  assert.doesNotMatch(shell, /logoutFailed|Sign-out failed|退出失败/);
  assert.doesNotMatch(shell, /<Link href="\/login"><SignOut/);
  assert.equal((shell.match(/onClick=\{\(\) => void logout\(\)\}/g) || []).length, 2);
  assert.equal((shell.match(/disabled=\{loggingOut\}/g) || []).length, 2);
});

test("logout adapter revokes the canonical session before clearing its HttpOnly cookie", () => {
  const adapter = fs.readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");
  const logoutStart = adapter.indexOf('if (path === "auth/logout" && request.method === "POST")');
  const logoutEnd = adapter.indexOf('if (path === "auth/kai/config"', logoutStart);
  const flow = adapter.slice(logoutStart, logoutEnd);

  assert.ok(logoutStart >= 0 && logoutEnd > logoutStart);
  assert.match(flow, /await upstream\(request, "\/api\/auth\/logout", \{ method: "POST" \}\)/);
  assert.match(flow, /result\.ok \|\| result\.status === 401/);
  assert.ok(flow.indexOf("await upstream") < flow.indexOf("clearAuthCookie(request, response)"));
  assert.ok(flow.indexOf("upstreamFailure(result)") < flow.indexOf("clearAuthCookie(request, response)"));
  assert.ok(flow.indexOf("clearAuthCookie(request, response)") < flow.indexOf("return response"));
  assert.match(adapter, /\^auth\\\/\(\?:login\|logout\|register/);
});

test("public header also completes local sign-out when revocation cannot be confirmed", () => {
  const header = fs.readFileSync(new URL("../components/site-header.tsx", import.meta.url), "utf8");
  const logoutStart = header.indexOf("async function logout() {");
  const logoutEnd = header.indexOf("\n  }", logoutStart);
  const flow = header.slice(logoutStart, logoutEnd);

  assert.match(flow, /try \{\s+await logoutCurrentUser\(\);\s+\} catch \{[\s\S]*\} finally \{/);
  assert.match(flow, /setUser\(null\)[\s\S]*window\.location\.assign\("\/"\)/);
  assert.doesNotMatch(flow, /account\/settings/);
});
