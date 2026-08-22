import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildMarketRangeMap,
  mergeUniqueProducts,
  selectFeaturedProducts,
  sortByMarketPriority,
} from '../src/utils/market-list.ts'

test('market cards put complete-history models with larger seven-day moves first without changing prices', () => {
  const ranges = buildMarketRangeMap([
    { gpu_model: 'RTX 4090', gpu_variant: '24GB', change_7d_pct: 3.25, range_low_cny: 2, range_high_cny: 2.2, history_day_count: 7, history_span_hours: 144 },
    { gpu_model: 'A100', gpu_variant: '80GB', change_7d_pct: -8.5, range_low_cny: 5, range_high_cny: 5.5, history_day_count: 7, history_span_hours: 144 },
  ])
  const products = [
    { id: 1, gpu_model: 'RTX4090', memory: '24GB', stock: 20, price: 2.49500998 },
    { id: 2, gpu_model: 'A100', memory: '80GB', stock: 2, price: 5.24 },
    { id: 3, gpu_model: 'L40S', memory: '48GB', stock: 99, price: 1.2 },
  ]

  const sorted = sortByMarketPriority(products, ranges)

  assert.deepEqual(sorted.map((item) => item.id), [2, 1, 3])
  assert.equal(sorted[0].price, 5.24)
  assert.equal(sorted[1].price, 2.49500998)
})

test('pagination merge removes duplicate cards when live offers move between pages', () => {
  const merged = mergeUniqueProducts(
    [{ id: 1, gpu_model: 'A100', memory: '80GB' }],
    [
      { id: 1, gpu_model: 'A100', memory: '80GB' },
      { id: 2, gpu_model: 'H100', memory: '80GB' },
    ],
  )

  assert.deepEqual(merged.map((item) => item.id), [1, 2])
})

test('featured products remain populated when seven-day history is unavailable', () => {
  const products = [
    { id: 1, gpu_model: 'RTX4090', memory: '24GB', stock: 19, price: 2.08, status: 'on', purchasable: true },
    { id: 2, gpu_model: 'A800', memory: '80GB', stock: 170, price: 5.24, status: 'on', purchasable: true },
    { id: 3, gpu_model: 'VGPU32', memory: '32GB', stock: 135, price: 1.66, status: 'on', purchasable: true },
    { id: 4, gpu_model: 'MTTS4000', memory: '48GB', stock: 92, price: 1.96, status: 'on', purchasable: true },
  ]

  const featured = selectFeaturedProducts(products, {}, 4)

  assert.deepEqual(featured.map((item) => item.id), [2, 3, 4, 1])
})

test('featured products prefer verified movement and distinct GPU models', () => {
  const ranges = buildMarketRangeMap([
    { gpu_model: 'RTX4090', gpu_variant: '24GB', change_7d_pct: 2.5, range_low_cny: 2, range_high_cny: 2.2, history_day_count: 7, history_span_hours: 144 },
  ])
  const products = [
    { id: 1, gpu_model: 'RTX4090', memory: '24GB', stock: 1, price: 2.08, status: 'on', purchasable: true },
    { id: 2, gpu_model: 'RTX4090', memory: '24GB', stock: 99, price: 2.18, status: 'on', purchasable: true },
    { id: 3, gpu_model: 'A800', memory: '80GB', stock: 80, price: 5.24, status: 'on', purchasable: true },
  ]

  const featured = selectFeaturedProducts(products, ranges, 2)

  assert.deepEqual(featured.map((item) => item.id), [2, 3])
})
