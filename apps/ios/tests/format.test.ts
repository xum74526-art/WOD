import assert from 'node:assert/strict'
import test from 'node:test'

import {
  fmtCH,
  fmtCHr,
  fmtCardHours,
  formatAmount,
  formatDeadline,
  formatMoney,
  formatNumber,
  formatNumberInput,
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

test('card-hour accounting values always display exactly three decimals', () => {
  assert.equal(fmtCardHours('0.009980'), '0.010')
  assert.equal(fmtCardHours(12), '12.000')
})

test('card-hour units follow an in-page language switch without storage reload', () => {
  setFormatLanguage('zh-Hans')
  assert.equal(fmtCH(1.002), '1.000卡时')
  assert.equal(fmtCHr(1.002), '1.000卡时/h')

  setFormatLanguage('zh-Hant')
  assert.equal(fmtCH(1.002), '1.000卡時')
  assert.equal(fmtCHr(1.002), '1.000卡時/h')

  setFormatLanguage('en')
  assert.equal(fmtCH(1.002), '1.000 CH')
  assert.equal(fmtCHr(1.002), '1.000 CH/h')

  setFormatLanguage('zh-Hant')
})
