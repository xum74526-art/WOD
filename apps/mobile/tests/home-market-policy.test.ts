import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildHomeTrendRequests,
  HOME_TREND_LIMIT,
  isHomeMarketStatusDisplayable,
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

test('homepage keeps delayed quotes visible but rejects unusable source states', () => {
  assert.equal(isHomeMarketStatusDisplayable('live'), true)
  assert.equal(isHomeMarketStatusDisplayable('delayed'), true)
  assert.equal(isHomeMarketStatusDisplayable('stale'), false)
  assert.equal(isHomeMarketStatusDisplayable('unavailable'), false)
  assert.equal(isHomeMarketStatusDisplayable('pending'), false)
})
