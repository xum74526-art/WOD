import assert from 'node:assert/strict'
import test from 'node:test'

import { buildHomeTrendRequests, HOME_TREND_LIMIT } from '../src/utils/home-market-policy.ts'

function item(index: number) {
  return {
    gpu_model: `GPU${index}`,
    gpu_variant: '24GB',
    sources: ['kai'],
    volatility_sources: ['kai'],
    history_provenance: {
      upstream_provider: 'kai',
    },
  }
}

test('homepage request plan is bounded to four exact K-line identities', () => {
  const plan = buildHomeTrendRequests(Array.from({ length: 8 }, (_, index) => item(index)))

  assert.equal(plan.length, HOME_TREND_LIMIT)
  assert.deepEqual(plan.map((entry) => entry.item.gpu_model), ['GPU0', 'GPU1', 'GPU2', 'GPU3'])
  assert.equal(new Set(plan.map((entry) => entry.key)).size, HOME_TREND_LIMIT)
})

test('attributed legacy Vast archive never triggers a new frontend request', () => {
  const plan = buildHomeTrendRequests([{
    gpu_model: 'RTX 4090',
    gpu_variant: '24GB',
    sources: ['wod'],
    volatility_sources: ['hf_gpu_prices'],
    history_provenance: { upstream_provider: 'vast' },
  }])

  assert.deepEqual(plan, [])
})

test('KAI provenance requests the KAI source', () => {
  const plan = buildHomeTrendRequests([{
    gpu_model: 'RTX 5090',
    gpu_variant: '32GB',
    sources: ['kai', 'autodl'],
    volatility_sources: ['kai'],
    history_provenance: { upstream_provider: 'kai' },
  }])

  assert.deepEqual(plan[0].sources, ['kai'])
})

test('KAI pricing domain provenance resolves to the KAI transport key', () => {
  const plan = buildHomeTrendRequests([{
    gpu_model: 'H200',
    gpu_variant: '141GB',
    sources: ['kai'],
    volatility_sources: [],
    history_provenance: { upstream_provider: 'pricing.kai.com' },
  }])

  assert.deepEqual(plan[0].sources, ['kai'])
})

test('live fallback selects KAI only and ignores every retired source', () => {
  const plan = buildHomeTrendRequests([{
    gpu_model: 'RTX 6000',
    gpu_variant: '48GB',
    sources: ['vast', 'kai', 'autodl'],
    volatility_sources: [],
    history_provenance: null,
  }])
  const legacyOnly = buildHomeTrendRequests([{
    gpu_model: 'RTX 3090',
    gpu_variant: '24GB',
    sources: ['vast'],
    volatility_sources: [],
    history_provenance: null,
  }])

  assert.deepEqual(plan[0].sources, ['kai'])
  assert.deepEqual(legacyOnly, [])
})

test('duplicate model identities never create duplicate homepage requests', () => {
  const plan = buildHomeTrendRequests([item(1), item(1), item(2)], 3)
  assert.deepEqual(plan.map((entry) => entry.item.gpu_model), ['GPU1', 'GPU2'])
})
