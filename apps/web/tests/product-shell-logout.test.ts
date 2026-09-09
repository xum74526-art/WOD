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
  assert.match(flow, /catch \{[\s\S]*setLogoutFailed\(true\)/);
  assert.doesNotMatch(shell, /<Link href="\/login"><SignOut/);
  assert.equal((shell.match(/onClick=\{\(\) => void logout\(\)\}/g) || []).length, 2);
  assert.equal((shell.match(/disabled=\{loggingOut\}/g) || []).length, 2);
});
