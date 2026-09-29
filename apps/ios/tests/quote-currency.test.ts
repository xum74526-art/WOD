import assert from 'node:assert/strict'
import test from 'node:test'
import {
  displayInputToQuoteAmount,
  formatQuoteAmount,
  normalizeQuoteCurrency,
  quoteAmountToDisplayInput,
} from '../src/utils/quote-currency.ts'
import { setDisplayCurrency, setDisplayCurrencyConfig, setFormatLanguage } from '../src/utils/format.ts'

test('quote amounts follow the language currency and convert legacy ledger values', () => {
  setDisplayCurrencyConfig({ card_hour_cny_rate: 1, rates: { CNY: 1, HKD: 1.08, USD: 0.14 } })
  setFormatLanguage('zh-Hans')
  setDisplayCurrency('CNY')
  assert.equal(formatQuoteAmount(1200, 'CNY', '卡时'), '¥1,200.000')
  assert.equal(formatQuoteAmount(58.25, 'CH', '卡时'), '¥58.250')
  setFormatLanguage('zh-Hant')
  setDisplayCurrency('HKD')
  assert.equal(formatQuoteAmount(1200, 'CNY', '卡时'), 'HK$1,296.000')
  setFormatLanguage('en')
  setDisplayCurrency('USD')
  assert.equal(formatQuoteAmount(58.25, 'CARD_HOUR', 'CH'), 'US$8.155')
})

test('unknown quote currencies are normalized before display', () => {
  assert.equal(formatQuoteAmount(9.5, ' usdt<script> ', 'CH'), '9.500 USDTSCRIPT')
  assert.equal(normalizeQuoteCurrency(''), '')
  assert.equal(formatQuoteAmount(9.5, '', 'CH'), '9.500 —')
})

test('quote form converts display currency to canonical CNY and back', () => {
  setDisplayCurrencyConfig({ card_hour_cny_rate: 1, rates: { CNY: 1, HKD: 1.08, USD: 0.14 } })
  setFormatLanguage('en')
  setDisplayCurrency('USD')
  assert.equal(quoteAmountToDisplayInput(100, 'CNY'), '14.000')
  assert.equal(displayInputToQuoteAmount(14, 'CNY'), 100)
  setFormatLanguage('zh-Hant')
  setDisplayCurrency('HKD')
  assert.equal(quoteAmountToDisplayInput(100, 'CH'), '108.000')
  assert.equal(displayInputToQuoteAmount(108, 'CH'), 100)
})
