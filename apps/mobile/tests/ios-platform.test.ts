import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeIosDistribution,
  isDistributionRouteAllowed,
  shouldRestrictCommerce,
} from '../src/utils/ios-distribution.ts'
import {
  authDeepLinkRoute,
  parseKaiAuthDeepLink,
} from '../src/utils/ios-deep-link.ts'

test('iOS App Store builds restrict direct commerce by default', () => {
  assert.equal(normalizeIosDistribution(undefined), 'app-store')
  assert.equal(normalizeIosDistribution('unexpected'), 'app-store')
  assert.equal(shouldRestrictCommerce('ios', 'app-store'), true)
  assert.equal(shouldRestrictCommerce('ios', 'enterprise'), false)
  assert.equal(shouldRestrictCommerce('android', 'app-store'), false)
  assert.equal(isDistributionRouteAllowed('/pages/buy-request/index', false), false)
  assert.equal(isDistributionRouteAllowed('/pages/supplier/product-create?from=assets', false), false)
  assert.equal(isDistributionRouteAllowed('/pages/orders/index', false), true)
  assert.equal(isDistributionRouteAllowed('/pages/buy-request/index', true), true)
})

test('KAI auth deep links accept only the bounded auth callback contract', () => {
  const ticket = 'abcdefghijklmnop_1234567890'
  assert.deepEqual(parseKaiAuthDeepLink(`kai://auth?kai_ticket=${ticket}`), { ticket })
  assert.equal(authDeepLinkRoute({ ticket }), `/pages/login/index?kai_ticket=${ticket}`)
  assert.deepEqual(parseKaiAuthDeepLink('kai://auth?kai_error=access_denied'), { error: 'access_denied' })
  assert.deepEqual(parseKaiAuthDeepLink('kai://auth?kai_error=account_not_found'), { error: 'account_not_found' })
  assert.deepEqual(parseKaiAuthDeepLink('kai://auth?kai_error=identity_conflict'), { error: 'identity_conflict' })
  assert.deepEqual(parseKaiAuthDeepLink('kai://auth?kai_error=unknown'), { error: 'authorization_failed' })
  assert.equal(parseKaiAuthDeepLink('https://example.com/auth?kai_ticket=abcdefghijklmnop'), null)
  assert.equal(parseKaiAuthDeepLink('kai://settings?kai_ticket=abcdefghijklmnop'), null)
  assert.equal(parseKaiAuthDeepLink('kai://auth?kai_ticket=short'), null)
  assert.equal(parseKaiAuthDeepLink('kai://auth?kai_ticket=abcdefghijklmnop&kai_error=access_denied'), null)
})
