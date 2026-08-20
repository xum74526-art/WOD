import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildHomeTrendRequests,
  HOME_TREND_LIMIT,
  selectHomeTrendCandidates,
} from '../src/utils/home-market-policy.ts'

function item(index: number) {
  return {
    gpu_model: `GPU${index}`,
    gpu_variant: '24GB',
    sources: ['vast'],
    volatility_sources: ['hf_gpu_prices'],
    history_provenance: {
      upstream_provider: 'vast',
    },
  }
}

test('homepage request plan is bounded to four exact K-line identities', () => {
  const plan = buildHomeTrendRequests(Array.from({ length: 8 }, (_, index) => item(index)))

  assert.equal(plan.length, HOME_TREND_LIMIT)
  assert.deepEqual(plan.map((entry) => entry.item.gpu_model), ['GPU0', 'GPU1', 'GPU2', 'GPU3'])
  assert.equal(new Set(plan.map((entry) => entry.key)).size, HOME_TREND_LIMIT)
})

test('attributed Vast history is requested even when the live card is a WOD listing', () => {
  const plan = buildHomeTrendRequests([{
    gpu_model: 'RTX 4090',
    gpu_variant: '24GB',
    sources: ['wod'],
    volatility_sources: ['hf_gpu_prices'],
    history_provenance: { upstream_provider: 'vast' },
  }])

  assert.deepEqual(plan[0].sources, ['vast'])
  assert.equal(plan[0].billingMode, 'ondemand')
})

test('duplicate model identities never create duplicate homepage requests', () => {
  const plan = buildHomeTrendRequests([item(1), item(1), item(2)], 3)
  assert.deepEqual(plan.map((entry) => entry.item.gpu_model), ['GPU1', 'GPU2'])
})

test('historical GetDeploying rows remain eligible when the snapshot has no live offers', () => {
  const candidates = selectHomeTrendCandidates([{
    ...item(1),
    sources: ['getdeploying'],
    volatility_sources: ['getdeploying'],
    median_price_cny: 3.38,
    sample_count: 0,
    market_status: 'delayed',
    hot_eligible: true,
    history_day_count: 14,
  }])

  assert.equal(candidates.length, 1)
  assert.equal(candidates[0].gpu_model, 'GPU1')
})

test('live rows stay ahead of historical fallback rows', () => {
  const candidates = selectHomeTrendCandidates([
    {
      ...item(1), median_price_cny: 2, sample_count: 0, market_status: 'delayed',
      hot_eligible: true, history_day_count: 14,
    },
    {
      ...item(2), median_price_cny: 3, sample_count: 4, market_status: 'live',
      hot_eligible: true, history_day_count: 7,
    },
  ])

  assert.deepEqual(candidates.map((entry) => entry.gpu_model), ['GPU2', 'GPU1'])
})

test('unavailable or history-free rows are excluded from the homepage', () => {
  const candidates = selectHomeTrendCandidates([
    {
      ...item(1), median_price_cny: 2, sample_count: 0, market_status: 'unavailable',
      hot_eligible: false, history_day_count: 0,
    },
    {
      ...item(2), median_price_cny: 3, sample_count: 0, market_status: 'delayed',
      hot_eligible: false, history_day_count: 1,
    },
  ])

  assert.equal(candidates.length, 0)
})
