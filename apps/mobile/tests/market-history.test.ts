import assert from 'node:assert/strict'
import test from 'node:test'

import {
  marketHistoryDisplayState,
  marketObservedDayCount,
} from '../src/utils/market-history.ts'

function candle(day: number) {
  return {
    start_time: `2026-08-${String(day).padStart(2, '0')}T00:00:00Z`,
    end_time: `2026-08-${String(day).padStart(2, '0')}T06:00:00Z`,
    open_price_cny: 2.4,
    high_price_cny: 2.41,
    low_price_cny: 2.39,
    close_price_cny: 2.405,
    sample_count: 3,
    observation_count: 3,
    sources: ['vast'],
  }
}

function payload(rows: ReturnType<typeof candle>[], extra: Record<string, unknown> = {}) {
  return {
    server_time: '2026-08-18T00:00:00Z',
    gpu_model: 'RTX 4090',
    gpu_variant: '24GB',
    billing_mode: 'ondemand',
    range: '7d',
    bucket_seconds: 21600,
    tick_seconds: 10,
    method: 'observed_source_median_ohlc' as const,
    is_interpolated: false as const,
    requested_sources: ['vast'],
    candles: rows,
    ...extra,
  }
}

test('history display keeps partial and single observations visible without upgrading them to full', () => {
  const partial = payload([candle(15), candle(16), candle(17)], { history_state: 'partial' })
  const single = payload([candle(18)], { history_state: 'single' })

  assert.equal(marketHistoryDisplayState(partial), 'partial')
  assert.equal(marketObservedDayCount(partial), 3)
  assert.equal(marketHistoryDisplayState(single), 'single')
})

test('explicit full history remains full', () => {
  const full = payload(Array.from({ length: 7 }, (_, index) => candle(11 + index)), {
    history_state: 'full',
    coverage_day_count: 7,
    coverage_span_hours: 150,
  })
  assert.equal(marketHistoryDisplayState(full), 'full')
})
