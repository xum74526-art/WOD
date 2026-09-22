import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const page = source('../src/pages/revenue/index.vue')
const api = source('../src/api/revenue.ts')
const home = source('../src/pages/index/index.vue')
const i18n = source('../src/store/i18n.ts')

test('personal earnings use audited rebates and holding profit or loss', () => {
  assert.match(api, /settled_rebate_total: number/)
  assert.match(api, /pending_rebate: number/)
  assert.match(api, /holding_realized_pnl: number/)
  assert.match(api, /holding_unrealized_pnl: number/)
  assert.match(page, /summary\?\.pending_rebate/)
  assert.match(page, /summary\?\.holding_unrealized_pnl/)
  assert.match(page, /summary\?\.holding_realized_pnl/)
  assert.match(page, /record\.source_type === 'holding_sale'/)
  assert.doesNotMatch(page, /toCardHours\(r\.amount\)|toCardHours\(summary\?\./)
})
test('home labels the API totals as realized earnings', () => {
  assert.match(home, /todayRealizedEarnings/)
  assert.match(home, /totalRealizedEarnings/)
  assert.match(home, /signedCardHours\(rev\?\.today\)/)
  assert.match(i18n, /auditedEarningsScope: '仅汇总服务端可核验的购买返佣与持有资产出售盈亏；使用资产不会生成固定日收益。'/)
  assert.match(i18n, /auditedEarningsScope: 'Only auditable purchase rebates and holding-sale profit or loss are included\./)
})
