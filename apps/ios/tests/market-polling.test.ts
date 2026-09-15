import assert from 'node:assert/strict'
import test from 'node:test'

import {
  hasAdvancedMarketObservation,
  latestMarketObservationMs,
  marketCandlesNeedRefresh,
  MARKET_PUBLICATION_MS,
  QUOTE_POLL_SECONDS,
} from '../src/utils/market-polling.ts'

test('quote polling follows the five-minute upstream publication cadence', () => {
  assert.equal(QUOTE_POLL_SECONDS, 300)
  assert.equal(MARKET_PUBLICATION_MS, 300_000)
})

test('only a genuinely newer upstream observation advances the candle cursor', () => {
  const first = [{ observed_at: '2026-08-29T04:00:00Z' }]
  const samePublication = [{ observed_at: '2026-08-29T04:00:00Z', source_checked_at: '2026-08-29T04:00:10Z' }]
  const nextPublication = [{ observed_at: '2026-08-29T04:05:00Z' }]
  const cursor = latestMarketObservationMs(first)

  assert.equal(hasAdvancedMarketObservation(cursor, samePublication), false)
  assert.equal(hasAdvancedMarketObservation(cursor, nextPublication), true)
})

test('invalid timestamps never create a synthetic observation', () => {
  assert.equal(latestMarketObservationMs([{ observed_at: 'invalid' }]), 0)
  assert.equal(latestMarketObservationMs([{ source_checked_at: '2026-08-29T04:00:10Z' }]), 0)
})

test('a first observation establishes a cursor without invalidating the shared candle cache', () => {
  const items = [{ observed_at: '2026-08-29T04:00:00Z' }]
  assert.equal(marketCandlesNeedRefresh(0, items, null), false)
})

test('a newer quote refreshes candles only when their live marker is behind', () => {
  const previous = new Date('2026-08-29T04:00:00Z').getTime()
  const items = [{ observed_at: '2026-08-29T04:05:00Z' }]

  assert.equal(marketCandlesNeedRefresh(previous, items, '2026-08-29T04:00:00Z'), true)
  assert.equal(marketCandlesNeedRefresh(previous, items, '2026-08-29T04:05:00Z'), false)
})
