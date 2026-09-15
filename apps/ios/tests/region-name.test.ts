import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { localizeMarketLocation, localizeRegionName } from '../src/utils/region-name.ts'

const MARKET_REGIONS = [
  ['north_china', '华北', 'North China'],
  ['east_china', '华东', 'East China'],
  ['central_china', '华中', 'Central China'],
  ['south_china', '华南', 'South China'],
  ['northeast_china', '东北', 'Northeast China'],
  ['northwest_china', '西北', 'Northwest China'],
  ['southwest_china', '西南', 'Southwest China'],
  ['china_unspecified', '中国大陆', 'Mainland China'],
  ['asia_pacific', '亚太', 'Asia Pacific'],
  ['north_america', '北美', 'North America'],
  ['europe', '欧洲', 'Europe'],
  ['middle_east', '中东', 'Middle East'],
  ['south_america', '南美', 'South America'],
  ['africa', '非洲', 'Africa'],
  ['global_unspecified', '全球/未披露', 'Global / Undisclosed'],
] as const

test('all canonical market regions have explicit English labels', () => {
  for (const [code, zh, en] of MARKET_REGIONS) {
    assert.equal(localizeRegionName(zh, 'en', code), en)
    assert.equal(localizeRegionName(zh, 'zh-Hans', code), zh)
  }
})

test('Traditional Chinese localizes upstream region labels without changing stable codes', () => {
  assert.equal(localizeRegionName('华东', 'zh-Hant', 'east_china'), '華東')
  assert.equal(localizeRegionName('台湾省', 'zh-Hant'), '臺灣省')
  assert.equal(localizeMarketLocation('中国大陆', 'china_unspecified', '华北', 'zh-Hant'), '中國大陸 · 華北')
})

test('the six regions currently used by the KAI catalogue never leak Chinese in English mode', () => {
  const liveRegions = MARKET_REGIONS.filter(([code]) => [
    'north_america',
    'east_china',
    'europe',
    'global_unspecified',
    'asia_pacific',
    'china_unspecified',
  ].includes(code))

  assert.equal(liveRegions.length, 6)
  for (const [code, zh, en] of liveRegions) {
    assert.equal(localizeRegionName(zh, 'en', code), en)
    assert.doesNotMatch(en, /[\u3400-\u9fff]/)
  }
})

test('stable region code wins over stale upstream text and duplicate detail is removed', () => {
  assert.equal(localizeRegionName('旧地区名', 'en', 'europe'), 'Europe')
  assert.equal(localizeRegionName('EU-West-1', 'en'), 'EU-West-1')
  assert.equal(localizeRegionName('全球 / 未披露', 'en'), 'Global / Undisclosed')
  assert.equal(localizeMarketLocation('欧洲', 'europe', '欧洲', 'en'), 'Europe')
  assert.equal(localizeMarketLocation('华东', 'east_china', 'CN-East-1', 'en'), 'East China · CN-East-1')
})

test('all market, request, and merchant pages use the shared runtime region localizer', () => {
  const sources = [
    '../src/pages/market/index.vue',
    '../src/pages/quote/index.vue',
    '../src/pages/product/detail.vue',
    '../src/pages/supplier/settings.vue',
    '../src/pages/buy-request/index.vue',
    '../src/pages/supplier/dashboard.vue',
    '../src/pages/supplier/devices.vue',
  ].map((path) => readFileSync(new URL(path, import.meta.url), 'utf8'))

  assert.match(sources[0], /localizeRegionName\(p\.region_name \|\| '-', i18n\.lang, p\.region_code\)/)
  assert.match(sources[1], /localizeRegionName\(item\.region, i18n\.lang, item\.region_code\)/)
  assert.match(sources[2], /localizeMarketLocation\(product\.region_name, product\.region_code, product\.city, i18n\.lang\)/)
  assert.match(sources[3], /localizeRegionName\(info\.region, i18n\.lang\)/)
  for (const source of sources.slice(4)) {
    assert.match(source, /localizeRegionName\(/)
    assert.doesNotMatch(source, /tr\([^\n]*(?:\.region|region_name)/)
  }
})
