import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const supplierDashboard = readFileSync(new URL('../src/pages/supplier/dashboard.vue', import.meta.url), 'utf8')
const supplierRebate = readFileSync(new URL('../src/pages/supplier/rebate.vue', import.meta.url), 'utf8')
const personalRebate = readFileSync(new URL('../src/pages/rebate/index.vue', import.meta.url), 'utf8')
const profile = readFileSync(new URL('../src/pages/profile/index.vue', import.meta.url), 'utf8')
const locale = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

test('supplier dashboard keeps sales and personal purchase rebates in their dedicated views', () => {
  assert.match(supplierDashboard, /supplierSalesRebateTitle/)
  assert.match(supplierDashboard, /supplierSalesRebateCardHint/)
  assert.doesNotMatch(supplierDashboard, /getRebateSummary|personalRebate/)
})

test('supplier rebate explains the sales basis, top-up, exclusions and monthly cap', () => {
  for (const key of [
    'supplierSalesRebateRuleBasis',
    'supplierSalesRebateRuleTarget',
    'supplierSalesRebateRuleTopUp',
    'supplierSalesRebateRuleExclusions',
    'supplierBuyerRebateIndependent',
    'rebateCapUsage',
    'monthlyRebateCapRule',
  ]) {
    assert.match(supplierRebate, new RegExp(key))
  }
})

test('personal rebate explains confirmation, payout, exclusions and monthly cap', () => {
  for (const key of [
    'personalPurchaseRebateRuleBasis',
    'personalPurchaseRebateRuleConfirm',
    'personalPurchaseRebateRulePayout',
    'personalPurchaseRebateRuleExclusions',
    'rebateCapUsage',
    'monthlyRebateCapRule',
  ]) {
    assert.match(personalRebate, new RegExp(key))
  }
})

test('profile labels the two independent rebate programs consistently', () => {
  for (const key of [
    'supplierSalesRebateTitle',
    'supplierSalesRebateCardHint',
    'personalPurchaseRebateTitle',
    'personalPurchaseRebateCardHint',
  ]) {
    assert.match(profile, new RegExp(key))
    assert.match(locale, new RegExp(`^\\s*${key}:`, 'm'))
  }
})
