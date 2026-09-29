import assert from 'node:assert/strict'
import test from 'node:test'

import { translateDynamicEnglishText } from '../src/utils/dynamic-text.ts'
import { setDisplayCurrency, setDisplayCurrencyConfig, setFormatLanguage } from '../src/utils/format.ts'

function useTestRates() {
  setDisplayCurrencyConfig({ card_hour_cny_rate: 1, rates: { CNY: 1, HKD: 1.08, USD: 0.14 } })
  setDisplayCurrency('USD')
  setFormatLanguage('en')
}

test('mobile translates current and legacy personal rebate progress hints', () => {
  useTestRates()
  assert.equal(
    translateDynamicEnglishText('再购买 ¥10,000.01 可升至 5% 返佣'),
    'Spend US$1,400.001 more to reach the 5% personal purchase rebate tier.',
  )
  assert.equal(
    translateDynamicEnglishText('再消费 100 卡时可升至 5% 返佣'),
    'Spend US$14.028 more to reach the 5% personal purchase rebate tier.',
  )
})

test('mobile continues to translate supplier and invitation progress hints', () => {
  useTestRates()
  assert.equal(
    translateDynamicEnglishText('再销售 ¥200 可升至 8% 返佣'),
    'Confirm US$28.000 more in sales to reach the 8% seller sales rebate tier.',
  )
  assert.equal(
    translateDynamicEnglishText('已达最高返佣等级 15%'),
    'Highest rebate tier reached: 15%',
  )
  assert.equal(
    translateDynamicEnglishText('再邀请 2 人升级至 6% 返利'),
    'Invite 2 more people to reach a 6% reward rate',
  )
  assert.equal(
    translateDynamicEnglishText('已达最高返利等级'),
    'Highest invitation reward tier reached',
  )
  assert.equal(translateDynamicEnglishText('普通提示'), null)
})
