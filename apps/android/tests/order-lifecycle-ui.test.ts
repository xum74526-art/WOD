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
const supplierOrders = source('../src/pages/supplier/orders.vue')
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
  for (const field of [
    'supplier_id',
    'supplier_name',
    'supplier_rating',
    'supplier_order_count',
    'resource_claim_source',
    'assurance_label',
    'assurance_description',
  ]) {
    assert.match(orderApi, new RegExp(`${field}\\?:`))
  }
})

test('buyer actions follow server capability flags with legacy status fallback', () => {
  assert.match(orderDetail, /order\.value\.can_cancel \?\? order\.value\.status === 'paid'/)
  assert.match(orderDetail, /order\.value\.can_confirm \?\? order\.value\.status === 'delivering'/)
  assert.match(orderDetail, /order\.value\.can_dispute \?\? order\.value\.status === 'delivering'/)
  assert.match(orderDetail, /v-if="canDisputeOrder"/)
  assert.match(orderDetail, /v-if="canConfirmOrder"/)
  assert.match(orderDetail, /v-if="canCancelOrder"/)
})

test('seller order queue delivers valid SSH through the canonical order endpoint and refreshes', () => {
  assert.match(supplierApi, /url: `\/orders\/\$\{id\}\/deliver`/)
  assert.match(supplierApi, /data: \{ ssh_info \}/)
  assert.match(supplierOrders, /order\.can_deliver \?\? order\.status === 'paid'/)
  assert.match(supplierOrders, /isValidSshInfo\(value\)/)
  assert.match(supplierOrders, /await deliverSupplierOrder\(target\.id, value\)/)
  assert.match(supplierOrders, /await load\(\)/)
  assert.match(supplierOrders, /STATUS_FILTERS: Array<string \| undefined> = \['paid', 'delivering', 'disputed', undefined\]/)
  assert.match(supplierOrders, /HISTORY_STATUSES = new Set\(\['completed', 'running', 'done', 'canceled', 'refunded'\]\)/)
  assert.match(supplierOrders, /t\('orderHistory'\)/)
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
