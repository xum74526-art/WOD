import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import {
  ACCOUNT_REVENUE_RANGE_DAYS,
  startAssetDetailRequests,
} from '../src/utils/asset-detail-requests.ts'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const detail = source('../src/pages/asset/detail.vue')
const i18n = source('../src/store/i18n.ts')
const revenueApi = source('../src/api/revenue.ts')

test('asset 200 remains usable when the account revenue chart request fails', async () => {
  const assetFrom200 = { id: 42, product_name: 'H100' }
  const chartFailure = new Error('chart unavailable')
  let rejectChart!: (reason: unknown) => void
  const pendingChart = new Promise<never>((_resolve, reject) => {
    rejectChart = reject
  })
  const requests = startAssetDetailRequests(
    Promise.resolve(assetFrom200),
    pendingChart,
  )

  const assetResult = await requests.asset
  assert.equal(assetResult.status, 'fulfilled')
  if (assetResult.status === 'fulfilled') assert.equal(assetResult.value, assetFrom200)

  rejectChart(chartFailure)
  const chartResult = await requests.accountRevenueChart
  assert.equal(chartResult.status, 'rejected')
  if (chartResult.status === 'rejected') assert.equal(chartResult.reason, chartFailure)
})

test('asset state and optional account chart state are handled independently', () => {
  assert.match(detail, /void requests\.accountRevenueChart\.then\(\(result\) => \{/)
  assert.match(detail, /const assetResult = await requests\.asset/)
  assert.match(detail, /asset\.value = assetResult\.value/)
  assert.match(detail, /accountRevenueChartFailed\.value = true/)
  assert.match(detail, /accountRevenueChartLoading\.value = false/)
  assert.match(detail, /assetResult\.reason instanceof ApiRequestError && assetResult\.reason\.statusCode === 404/)
  assert.match(detail, /assetLoading\.value = false/)
  assert.match(detail, /v-else-if="assetMissing"[\s\S]*?assetNotFound/)
  assert.match(detail, /v-else-if="assetLoadFailed \|\| !asset"/)
  assert.match(detail, /v-else-if="accountRevenueChartFailed"[\s\S]*?accountRevenueChartUnavailable/)
  assert.doesNotMatch(detail, /Promise\.all\(\s*\[\s*getAsset\(id\),\s*getRevenueChart/)
})

test('the chart is explicitly account-wide for the last seven days', () => {
  assert.equal(ACCOUNT_REVENUE_RANGE_DAYS, 7)
  assert.match(detail, /getRevenueChart\(ACCOUNT_REVENUE_RANGE_DAYS, \{ silent: true \}\)/)
  assert.doesNotMatch(detail, /getRevenueChart\(\s*id\s*\)/)
  assert.match(detail, /:title="t\('accountRevenueLast7Days'\)"/)
  assert.match(i18n, /assetNotFound: '资产不存在'/)
  assert.match(i18n, /assetNotFound: 'Asset not found'/)
  assert.match(i18n, /accountRevenueLast7Days: '账户近 7 天总收益'/)
  assert.match(i18n, /accountRevenueLast7Days: 'Total account revenue \(last 7 days\)'/)
  assert.match(i18n, /accountRevenueChartUnavailable: '账户近 7 天总收益暂时无法加载，不影响本资产信息。'/)
  assert.match(i18n, /accountRevenueChartUnavailable: 'Total account revenue for the last 7 days is temporarily unavailable\. This does not affect the asset details\.'/)

  const chartFunction = revenueApi.match(/export function getRevenueChart[\s\S]*?\n\}/)?.[0] || ''
  assert.match(chartFunction, /url: '\/revenue\/chart'/)
  assert.match(chartFunction, /data: \{ range_days: rangeDays \}/)
  assert.match(chartFunction, /silent: options\.silent/)
  assert.doesNotMatch(chartFunction, /asset_id|assetId/)
})
