import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

import { englishRegionName, localizeMarketLocation, localizeRegionName } from '../src/utils/region-name.ts'

test('iOS localizes every canonical KAI market region', () => {
  const cases: Array<[string, string, string]> = [
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
  ]
  for (const [code, source, expected] of cases) {
    assert.equal(englishRegionName(source, code), expected)
    assert.equal(localizeRegionName(source, 'zh', code), source)
  }
  assert.equal(localizeRegionName('北美', 'zh'), '北美')
  assert.equal(localizeRegionName('全球 / 未披露', 'en'), 'Global / Undisclosed')
  assert.equal(localizeRegionName('旧地区名', 'en', 'europe'), 'Europe')
  assert.equal(localizeMarketLocation('欧洲', 'europe', '欧洲', 'en'), 'Europe')
  assert.equal(localizeMarketLocation('华东', 'east_china', 'CN-East-1', 'en'), 'East China · CN-East-1')
})

test('iOS English market copy uses buyer-friendly natural language', () => {
  const i18n = fs.readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')
  const generated = fs.readFileSync(new URL('../src/store/i18n_generated.ts', import.meta.url), 'utf8')
  const supplierSettings = fs.readFileSync(new URL('../src/pages/supplier/settings.vue', import.meta.url), 'utf8')
  const runtimeRegionViews = [
    '../src/pages/market/index.vue',
    '../src/pages/quote/index.vue',
    '../src/pages/product/detail.vue',
    '../src/pages/buy-request/index.vue',
    '../src/pages/store/index.vue',
    '../src/pages/supplier/dashboard.vue',
    '../src/pages/supplier/devices.vue',
  ].map((path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8'))

  assert.match(i18n, /buyUsage: 'Buy Now'/)
  assert.match(i18n, /marketOfferSource: 'Pricing Source'/)
  assert.match(i18n, /sevenDayChangeValue: '7-Day Change \{value\}%'/)
  assert.match(i18n, /sevenDayPriceRangeValue: '7-Day Price Range \{low\}-\{high\} CH'/)
  assert.doesNotMatch(`${i18n}\n${generated}`, /Buy Usage|Offer source|7d Change|7d Range|7d range/)
  assert.match(supplierSettings, /localizeRegionName\(info\.region, i18n\.lang\)/)
  for (const source of runtimeRegionViews) {
    assert.match(source, /localize(?:MarketLocation|RegionName)\(/)
    assert.doesNotMatch(source, /tr\([^\n]*(?:\.region|region_name)/)
  }
})
