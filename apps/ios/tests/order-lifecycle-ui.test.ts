import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const orderApi = source('../src/api/order.ts')
const supplierApi = source('../src/api/supplier.ts')
const orderDetail = source('../src/pages/order/detail.vue')
const supplierRevenue = source('../src/pages/supplier/revenue.vue')
const i18n = source('../src/store/i18n.ts')

test('buyer order contract and detail expose fulfillment deadlines and disputes', () => {
  for (const field of [
    'delivery_due_at',
    'confirmation_due_at',
    'dispute_due_at',
    'dispute_reason',
    'can_cancel',
    'can_confirm',
    'can_dispute',
  ]) {
    assert.match(orderApi, new RegExp(`${field}\\?:`))
  }
  assert.match(orderApi, /url: `\/orders\/\$\{id\}\/dispute`/)
  assert.match(orderDetail, /order\.delivery_due_at/)
  assert.match(orderDetail, /order\.confirmation_due_at/)
  assert.match(orderDetail, /order\.dispute_due_at/)
  assert.match(orderDetail, /disputeOrder\(oid\.value, reason\)/)
})

test('buyer actions follow server capability flags with legacy status fallback', () => {
  assert.match(orderDetail, /order\.value\.can_cancel \?\? order\.value\.status === 'paid'/)
  assert.match(orderDetail, /order\.value\.can_confirm \?\? order\.value\.status === 'delivering'/)
  assert.match(orderDetail, /order\.value\.can_dispute \?\? order\.value\.status === 'delivering'/)
  assert.match(orderDetail, /v-if="canDisputeOrder"/)
  assert.match(orderDetail, /v-if="canConfirmOrder"/)
  assert.match(orderDetail, /v-if="canCancelOrder"/)
})

test('supplier revenue distinguishes settled, pending and historical unreconciled orders', () => {
  assert.match(supplierApi, /historical_unreconciled_count: number/)
  assert.match(supplierApi, /settlement_status: 'settled' \| 'pending' \| 'historical_unreconciled'/)
  assert.match(supplierRevenue, /r\.settlement_status === 'settled'/)
  assert.match(supplierRevenue, /r\.settlement_status === 'historical_unreconciled'/)
  assert.match(supplierRevenue, /historical_unreconciled_count/)
  assert.match(i18n, /'待财务核账': 'Awaiting financial reconciliation'/)
  assert.match(i18n, /历史订单待财务核账（\{count\} 笔）/)
})
