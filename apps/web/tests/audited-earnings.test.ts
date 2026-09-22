import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const component = fs.readFileSync(new URL("../components/mobile-account-services.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/mobile-business-api.ts", import.meta.url), "utf8");

test("Web personal earnings show auditable rebate and holding P/L fields", () => {
  assert.match(api, /settled_rebate_total: number/);
  assert.match(api, /pending_rebate: number/);
  assert.match(api, /holding_realized_pnl: number/);
  assert.match(api, /holding_unrealized_pnl: number/);
  assert.match(component, /summary\?\.pending_rebate/);
  assert.match(component, /summary\?\.holding_unrealized_pnl/);
  assert.match(component, /row\.source_type === "holding_sale"/);
  assert.match(component, /历史模拟收益.*仅保留作审计，不计入余额或当前收益/);
});
