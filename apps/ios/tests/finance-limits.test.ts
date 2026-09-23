import test from 'node:test'
import assert from 'node:assert/strict'

import {
  effectiveRechargeMinimum,
  effectiveWithdrawalMinimum,
  MINIMUM_RECHARGE_CNY,
  MINIMUM_WITHDRAW_CARD_HOURS,
  resolveRechargeBuildMinimum,
} from '../src/utils/recharge-payment.ts'

test('mobile finance minimums never fall below the production limits', () => {
  assert.equal(MINIMUM_RECHARGE_CNY, 10)
  assert.equal(MINIMUM_WITHDRAW_CARD_HOURS, 10)
  assert.equal(effectiveRechargeMinimum(undefined), 10)
  assert.equal(effectiveRechargeMinimum(0.01), 10)
  assert.equal(effectiveRechargeMinimum(20), 20)
  assert.equal(resolveRechargeBuildMinimum('0.01'), 10)
  assert.equal(resolveRechargeBuildMinimum('0'), 10)
  assert.equal(resolveRechargeBuildMinimum('20'), 10)
  assert.equal(effectiveWithdrawalMinimum(undefined), 10)
  assert.equal(effectiveWithdrawalMinimum(0), 10)
  assert.equal(effectiveWithdrawalMinimum(25), 25)
})
