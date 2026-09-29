import assert from 'node:assert/strict'
import test from 'node:test'

import {
  cardHoursToDisplayCurrency,
  displayCurrencyCode,
  displayCurrencyToCardHours,
  fmtCH,
  fmtCHr,
  fmtCardHours,
  formatAmount,
  formatDeadline,
  formatMoney,
  formatNumber,
  formatNumberInput,
  formatCardHourCurrency,
  formatCnyCurrency,
  normalizeDisplayInputToCny,
  setDisplayCurrencyConfig,
  setFormatLanguage,
} from '../src/utils/format.ts'

test('order deadlines render deterministic Asia/Shanghai date and time', () => {
  assert.equal(formatDeadline('2026-08-26T01:02:03'), '2026-08-26 09:02 UTC+8')
  assert.equal(formatDeadline('2026-08-26T01:02:03+08:00'), '2026-08-26 01:02 UTC+8')
  assert.equal(formatDeadline(null), '')
})

test('formatNumber limits long Android-style floating tails without Intl', () => {
  assert.equal(formatNumber(1740.439121756487), '1,740.439')
  assert.equal(formatNumber('3906.1077844311376'), '3,906.108')
  assert.equal(formatNumber(2.4950099800399204), '2.495')
})

test('formatNumber applies deterministic rounding and grouping', () => {
  assert.equal(formatNumber(1234567.899), '1,234,567.899')
  assert.equal(formatNumber(1.005), '1.005')
  assert.equal(formatNumber(1.006), '1.006')
  assert.equal(formatNumberInput(1234567.899), '1234567.899')
})

test('formatNumber normalizes negative zero and honors minimum digits', () => {
  assert.equal(formatNumber(-0), '0')
  assert.equal(formatNumber(-0.001), '-0.001')
  assert.equal(formatNumber(-0.006), '-0.006')
  assert.equal(formatNumber(12, { minimumFractionDigits: 2 }), '12.00')
  assert.equal(formatMoney(12), '12.000')
  assert.equal(formatAmount(1.002), '1.002')
})

test('formatNumber safely normalizes non-finite API values', () => {
  assert.equal(formatNumber(undefined), '0')
  assert.equal(formatNumber(Number.NaN), '0')
  assert.equal(formatNumber(Number.POSITIVE_INFINITY), '0')
})

test('account money keeps CNY as its ledger base while display rates vary by currency', () => {
  setDisplayCurrencyConfig({ card_hour_cny_rate: 1.002, rates: { CNY: 1, HKD: 1.08, USD: 0.14 } })
  setFormatLanguage('zh-Hans')
  assert.equal(fmtCardHours('0.009980'), '0.010')
  assert.equal(fmtCardHours(12), '12.000')
  setFormatLanguage('zh-Hant')
})

test('legacy CNY formatters follow an in-page currency switch without storage reload', () => {
  setDisplayCurrencyConfig({ card_hour_cny_rate: 1, rates: { CNY: 1, HKD: 1.08, USD: 0.14 } })
  setFormatLanguage('zh-Hans')
  assert.equal(fmtCH(1.002), '¥1.002')
  assert.equal(fmtCHr(1.002), '¥1.002/h')

  setFormatLanguage('zh-Hant')
  assert.equal(fmtCH(1.002), 'HK$1.082')
  assert.equal(fmtCHr(1.002), 'HK$1.082/h')

  setFormatLanguage('en')
  assert.equal(fmtCH(1.002), 'US$0.140')
  assert.equal(fmtCHr(1.002), 'US$0.140/h')

  setFormatLanguage('zh-Hant')
})

test('display currency follows language and reverses safely to the ledger unit', () => {
  setDisplayCurrencyConfig({
    card_hour_cny_rate: 1.002,
    rates: { CNY: 1, HKD: 1.08, USD: 0.14 },
  })

  setFormatLanguage('zh-Hans')
  assert.equal(displayCurrencyCode(), 'CNY')
  assert.equal(formatCardHourCurrency(1), '¥1.000')

  setFormatLanguage('zh-Hant')
  assert.equal(displayCurrencyCode(), 'HKD')
  assert.equal(formatCardHourCurrency(1), 'HK$1.080')

  setFormatLanguage('en')
  assert.equal(displayCurrencyCode(), 'USD')
  assert.equal(formatCnyCurrency(10), 'US$1.400')
  assert.equal(cardHoursToDisplayCurrency(10), 1.4000000000000001)
  assert.ok(Math.abs(displayCurrencyToCardHours(1.4) - 10) < 1e-9)

  setFormatLanguage('zh-Hant')
})

test('three-decimal display input preserves legal CNY payment boundaries', () => {
  setDisplayCurrencyConfig({ rates: { CNY: 1, HKD: 1.169032900251, USD: 0.149020326907 } })
  setFormatLanguage('en')
  assert.equal(normalizeDisplayInputToCny('1.490', { fractionDigits: 2, minimum: 10 }), 10)
  assert.equal(normalizeDisplayInputToCny('1.490', { fractionDigits: 3, minimum: 10 }), 10)
  assert.equal(normalizeDisplayInputToCny('1.489', { fractionDigits: 3, minimum: 10 }), 9.992)
  setFormatLanguage('zh-Hant')
})
