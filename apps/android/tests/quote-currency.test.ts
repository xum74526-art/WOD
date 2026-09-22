import assert from 'node:assert/strict'
import test from 'node:test'
import { formatQuoteAmount, normalizeQuoteCurrency } from '../src/utils/quote-currency.ts'

test('quote amounts preserve CNY and card-hour units without conversion', () => {
  assert.equal(formatQuoteAmount(1200, 'CNY', '卡时'), '¥1,200.000')
  assert.equal(formatQuoteAmount(58.25, 'CH', '卡时'), '58.250 卡时')
  assert.equal(formatQuoteAmount(58.25, 'CARD_HOUR', 'CH'), '58.250 CH')
})

test('unknown quote currencies are normalized before display', () => {
  assert.equal(formatQuoteAmount(9.5, ' usdt<script> ', 'CH'), '9.500 USDTSCRIPT')
  assert.equal(normalizeQuoteCurrency(''), '')
  assert.equal(formatQuoteAmount(9.5, '', 'CH'), '9.500 —')
})
