import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("workspace authentication failures stop loading and offer a forced retry", () => {
  const shell = fs.readFileSync(new URL("../components/product-shell.tsx", import.meta.url), "utf8");
  const loadStart = shell.indexOf("getCurrentUser(loadAttempt > 0)");
  const loadEnd = shell.indexOf("return () => { active = false; };", loadStart);
  const loadFlow = shell.slice(loadStart, loadEnd);

  assert.ok(loadStart >= 0);
  assert.match(loadFlow, /reason instanceof ApiError && reason\.status === 401[\s\S]*window\.location\.replace\(loginHref\(locationReturnPath\(window\.location\)\)\)[\s\S]*return/);
  assert.doesNotMatch(loadFlow, /loginHref\(pathname\)/);
  assert.match(loadFlow, /setGateFailed\(true\)[\s\S]*setReady\(true\)/);
  const errorStart = shell.indexOf("if (gateFailed)");
  const errorEnd = shell.indexOf("if (!ready || !user)", errorStart);
  const errorState = shell.slice(errorStart, errorEnd);

  assert.match(errorState, /工作台暂时无法加载/);
  assert.match(errorState, /setLoadAttempt/);
  assert.match(errorState, /重新加载/);
  assert.ok(shell.indexOf("if (gateFailed)") < shell.indexOf("if (!ready || !user)"));
});
