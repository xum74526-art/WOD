import assert from 'node:assert/strict'
import test from 'node:test'

import {
  hasAdvancedMarketObservation,
  latestMarketObservationMs,
  QUOTE_POLL_SECONDS,
} from '../src/utils/market-polling.ts'

test('quote polling checks every ten seconds', () => {
  assert.equal(QUOTE_POLL_SECONDS, 10)
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
