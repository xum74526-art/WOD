import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { IMAGE_ATTRIBUTIONS } from '../src/config/image-attributions.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('the app exposes complete attribution for the six Commons derivatives', () => {
  assert.equal(IMAGE_ATTRIBUTIONS.length, 6)
  assert.deepEqual(IMAGE_ATTRIBUTIONS.map((item) => item.asset), [
    'RTX2060.jpg',
    'RTX3070.jpg',
    'RTX4070.jpg',
    'RTX5060Ti.jpg',
    'RTX5070.jpg',
    'RTX5080.jpg',
  ])
  for (const item of IMAGE_ATTRIBUTIONS) {
    assert.match(item.sourceUrl, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/)
    assert.match(item.licenseUrl, /^https:\/\/creativecommons\.org\//)
    assert.ok(item.author)
    assert.ok(item.license)
    assert.ok(item.modificationKey)
  }
  assert.deepEqual(IMAGE_ATTRIBUTIONS.find((item) => item.asset === 'RTX4070.jpg')?.aliases, [
    'RTX 4060', 'RTX 4060 Ti', 'RTX 4070 SUPER', 'RTX 4070 Ti',
  ])
})

test('settings links to a registered, localized attribution page', () => {
  const settings = read('../src/pages/settings/index.vue')
  const page = read('../src/pages/image-attributions/index.vue')
  const pages = JSON.parse(read('../src/pages.json')) as { pages: Array<{ path: string }> }
  const i18n = read('../src/store/i18n.ts')

  assert.match(settings, /nav\('\/pages\/image-attributions\/index'\)/)
  assert.ok(pages.pages.some((item) => item.path === 'pages/image-attributions/index'))
  assert.match(page, /IMAGE_ATTRIBUTIONS/)
  assert.match(page, /imageAttributionsDirectRightsDescription/)
  assert.match(i18n, /imageAttributionsTitle: '图片来源与许可'/)
  assert.match(i18n, /imageAttributionsTitle: 'Image sources and licenses'/)
  assert.match(i18n, /toTraditionalChinese\(value\)/)
})
