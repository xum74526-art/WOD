import assert from 'node:assert/strict'
import test from 'node:test'
import { localizedNotificationContent } from '../src/utils/notification-content.ts'
import { setDisplayCurrency, setDisplayCurrencyConfig } from '../src/utils/format.ts'

const revenue = {
  id: 1,
  title: '今日收益已更新',
  content: '今日已记录人民币 ¥100.000 收益，可在收益中心查看明细。',
  title_en: "Today's revenue updated",
  content_en: 'CNY ¥100.000 of revenue has been recorded today.',
  template_key: 'daily_revenue_recorded',
  amount_cny: '100.000',
  type: 'revenue',
  is_read: false,
}

test('mobile revenue notification converts canonical CNY for every language', () => {
  setDisplayCurrencyConfig({ card_hour_cny_rate: 1, rates: { CNY: 1, HKD: 1.08, USD: 0.14 } })
  setDisplayCurrency('CNY')
  assert.match(localizedNotificationContent(revenue, 'zh-Hans', value => value), /¥100\.000/)
  setDisplayCurrency('HKD')
  assert.match(localizedNotificationContent(revenue, 'zh-Hant', value => value), /HK\$108\.000/)
  setDisplayCurrency('USD')
  assert.match(localizedNotificationContent(revenue, 'en', value => value), /US\$14\.000/)
})

test('ordinary English notification keeps its authored English copy', () => {
  const ordinary = { ...revenue, template_key: null, amount_cny: null, content_en: 'Settings updated.' }
  assert.equal(localizedNotificationContent(ordinary, 'en', value => value), 'Settings updated.')
})
