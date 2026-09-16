import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  formatPlatformDateTime,
  localDateTimeInputToUtcIso,
  parseApiUtcDateTime,
  toLocalDateTimeInputValue,
} from "../lib/date-time.ts";

function withTimeZone(timeZone: string, action: () => void) {
  const previous = process.env.TZ;
  process.env.TZ = timeZone;
  try {
    action();
  } finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
}

test("datetime-local uses the browser's local wall clock and submits the matching UTC instant", () => {
  withTimeZone("Asia/Shanghai", () => {
    const instant = new Date("2026-09-16T04:34:56.789Z");
    const inputValue = toLocalDateTimeInputValue(instant);

    assert.equal(inputValue, "2026-09-16T12:34");
    assert.equal(localDateTimeInputToUtcIso(inputValue), "2026-09-16T04:34:00.000Z");
  });
});

test("datetime-local conversion rejects values that are not valid local wall-clock times", () => {
  assert.throws(() => localDateTimeInputToUtcIso("2026-02-30T12:00"), /无效的本地日期时间/);
  assert.throws(() => localDateTimeInputToUtcIso("2026-09-16T12:00Z"), /无效的本地日期时间/);
});

test("API timestamps without offsets are treated as UTC and displayed in Asia/Shanghai", () => {
  withTimeZone("America/Los_Angeles", () => {
    assert.equal(parseApiUtcDateTime("2026-09-16T04:34:00")?.toISOString(), "2026-09-16T04:34:00.000Z");
    assert.equal(formatPlatformDateTime("2026-09-16T04:34:00"), "2026-09-16 12:34");
    assert.equal(formatPlatformDateTime("2026-09-16T04:34:00Z"), "2026-09-16 12:34");
    assert.equal(formatPlatformDateTime("2026-09-16T12:34:00+08:00"), "2026-09-16 12:34");
  });
  assert.equal(formatPlatformDateTime("not-a-date"), "—");
});

test("admin withdrawal payment uses the shared conversion and displays paid_at explicitly", () => {
  const workspace = fs.readFileSync(new URL("../components/admin-withdrawal-workspace.tsx", import.meta.url), "utf8");

  assert.match(workspace, /paid_at: toLocalDateTimeInputValue\(\)/);
  assert.match(workspace, /paid_at: localDateTimeInputToUtcIso\(payment\.paid_at\)/);
  assert.match(workspace, /打款时间（本地时间）/);
  assert.match(workspace, /row\.status === "paid" && <p>打款时间（北京时间）：\{formatPlatformDateTime\(row\.paid_at\)\}<\/p>/);
  assert.doesNotMatch(workspace, /new Date\(\)\.toISOString\(\)\.slice\(0, 16\)/);
});
