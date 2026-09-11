import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { locationReturnPath, loginHref, safeReturnPath } from "../lib/auth-navigation.ts";

test("Web login return paths preserve valid same-origin destinations", () => {
  assert.equal(safeReturnPath("/"), "/");
  assert.equal(safeReturnPath("/account/settings?tab=security#sessions"), "/account/settings?tab=security#sessions");
  assert.equal(safeReturnPath("/search?q=https%3A%2F%2Fevil.example#results"), "/search?q=https%3A%2F%2Fevil.example#results");
  assert.equal(
    loginHref("/account/settings?tab=security#sessions"),
    "/login?return_to=%2Faccount%2Fsettings%3Ftab%3Dsecurity%23sessions",
  );
});

test("workspace login preserves the current query", () => {
  assert.equal(
    locationReturnPath({
      pathname: "/account/requests",
      search: "?create=1&gpu_model=H100&supplier_id=7",
    }),
    "/account/requests?create=1&gpu_model=H100&supplier_id=7",
  );
  assert.equal(
    loginHref(locationReturnPath({
      pathname: "/account/requests",
      search: "?create=1&gpu_model=H100&supplier_id=7",
    })),
    "/login?return_to=%2Faccount%2Frequests%3Fcreate%3D1%26gpu_model%3DH100%26supplier_id%3D7",
  );
});

test("Web login return paths reject external and browser-normalized destinations", () => {
  for (const value of [
    null,
    "",
    "account",
    "https://evil.example/account",
    "//evil.example/account",
    "///evil.example/account",
    "/\\evil.example/account",
    "/\\\\evil.example/account",
    "\\\\evil.example/account",
    "/\tevil.example/account",
    "/\nevil.example/account",
    "/account\r\nLocation: https://evil.example",
    "/account\u0000settings",
    "/account\u007fsettings",
    "/.//evil.example/account",
    "/%2e//evil.example/account",
    "/%2e%2e//evil.example/account",
    "/account/..//evil.example/account",
    "/account/%2E%2E//evil.example/account",
    "?tab=orders",
    "#sessions",
    "%2F%2Fevil.example",
    "javascript:alert(1)",
  ]) {
    assert.equal(safeReturnPath(value), "/", `must reject ${JSON.stringify(value)}`);
  }

  assert.equal(loginHref("/\\\\evil.example/account"), "/login?return_to=%2F");
});

test("every Web login completion path uses the shared return-path validator", () => {
  const panel = readFileSync(new URL("../components/auth-panel.tsx", import.meta.url), "utf8");
  const adapter = readFileSync(new URL("../lib/api-adapter.ts", import.meta.url), "utf8");

  assert.match(panel, /return normalizeReturnPath\(requested\)/);
  assert.match(panel, /window\.location\.assign\(destination\)/);
  assert.match(panel, /window\.location\.replace\(normalizeReturnPath\(result\.return_to\)\)/);
  assert.match(adapter, /import \{ safeReturnPath \} from "@\/lib\/auth-navigation"/);
  assert.match(adapter, /cookies\.set\(RETURN_TO_COOKIE, safeReturnPath\(/);
  assert.match(adapter, /return_to: safeReturnPath\(request\.cookies\.get\(RETURN_TO_COOKIE\)\?\.value\)/);
  assert.doesNotMatch(adapter, /function safeReturnPath\(/);
});
