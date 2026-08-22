import assert from 'node:assert/strict'
import test from 'node:test'

import {
  fmtCH,
  fmtCHr,
  formatMoney,
  formatNumber,
  formatNumberInput,
  setFormatLanguage,
} from '../src/utils/format.ts'

test('formatNumber limits long Android-style floating tails without Intl', () => {
  assert.equal(formatNumber(1740.439121756487), '1,740.44')
  assert.equal(formatNumber('3906.1077844311376'), '3,906.11')
  assert.equal(formatNumber(2.4950099800399204), '2.5')
})

test('formatNumber applies deterministic rounding and grouping', () => {
  assert.equal(formatNumber(1234567.899), '1,234,567.9')
  assert.equal(formatNumber(1.005), '1.01')
  assert.equal(formatNumber(1.006), '1.01')
  assert.equal(formatNumberInput(1234567.899), '1234567.9')
})

test('formatNumber normalizes negative zero and honors minimum digits', () => {
  assert.equal(formatNumber(-0), '0')
  assert.equal(formatNumber(-0.001), '0')
  assert.equal(formatNumber(-0.006), '-0.01')
  assert.equal(formatNumber(12, { minimumFractionDigits: 2 }), '12.00')
  assert.equal(formatMoney(12), '12.00')
})

test('formatNumber safely normalizes non-finite API values', () => {
  assert.equal(formatNumber(undefined), '0')
  assert.equal(formatNumber(Number.NaN), '0')
  assert.equal(formatNumber(Number.POSITIVE_INFINITY), '0')
})

test('card-hour units follow an in-page language switch without storage reload', () => {
  setFormatLanguage('zh')
  assert.equal(fmtCH(1.002), '1卡时')
  assert.equal(fmtCHr(1.002), '1卡时/h')

  setFormatLanguage('en')
  assert.equal(fmtCH(1.002), '1 CH')
  assert.equal(fmtCHr(1.002), '1 CH/h')

  setFormatLanguage('zh')
})
