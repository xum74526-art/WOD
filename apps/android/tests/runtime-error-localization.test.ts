import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

test('runtime errors only expose known localized messages and otherwise use a localized fallback', () => {
  const i18n = source('../src/store/i18n.ts')
  assert.match(i18n, /const key = aliases\[source\] \|\| TRANSLATION_KEY_BY_TEXT\.get\(source\)/)
  assert.match(i18n, /return t\(key \|\| fallbackKey\)/)

  const expectedCalls = new Map([
    ['../src/pages/community/publish.vue', 2],
    ['../src/pages/supplier/apply.vue', 1],
    ['../src/pages/supplier/devices.vue', 1],
    ['../src/pages/supplier/orders.vue', 1],
    ['../src/pages/supplier/product-create.vue', 1],
    ['../src/pages/coupons/index.vue', 1],
    ['../src/pages/recovery-email/index.vue', 1],
    ['../src/pages/forgot-password/index.vue', 1],
    ['../src/pages/reset-password/index.vue', 1],
  ])

  for (const [path, expected] of expectedCalls) {
    const page = source(path)
    assert.equal(
      (page.match(/localizedErrorMessage\(/g) || []).length,
      expected,
      `${path} must route visible runtime errors through localizedErrorMessage`,
    )
    assert.doesNotMatch(page, /title:\s*[^\n}]*error\.message/)
    assert.doesNotMatch(page, /loadError\.value\s*=\s*[^\n]*error\.message/)
  }
})
