import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const page = readFileSync(new URL('../src/pages/coupons/index.vue', import.meta.url), 'utf8')
const api = readFileSync(new URL('../src/api/coupon.ts', import.meta.url), 'utf8')

test('coupon page reads the authenticated backend list and has complete request states', () => {
  assert.match(api, /url:\s*['"]\/coupons['"]/)
  assert.match(page, /getCoupons\(STATUS\[tab\.value\]\)/)
  assert.match(page, /coupon-skeleton/)
  assert.match(page, /couponLoadFailed/)
  assert.match(page, /couponEmptyAvailable/)
  assert.match(page, /load-retry/)
})

test('coupon page exposes all real backend states in both locale dictionaries', () => {
  assert.match(page, /'available',\s*'used',\s*'expired'/)
  assert.match(page, /couponAvailable/)
  assert.match(page, /couponUsed/)
  assert.match(page, /couponExpired/)
})

test('coupon UI does not advertise hard-coded redemption codes or mint coupons', () => {
  assert.doesNotMatch(page, /WOD10|WOD50|NEW88|redeemCoupon/)
  assert.doesNotMatch(api, /\/coupons\/redeem|redeemCoupon/)
})
