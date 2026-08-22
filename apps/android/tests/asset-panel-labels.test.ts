import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const assetsSource = readFileSync(new URL('../src/pages/assets/index.vue', import.meta.url), 'utf8')
const i18nSource = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

const personalKeys = [
  'personalAssetOverview',
  'personalComputeAssets',
  'personalDeviceHosting',
  'personalDeviceStatus',
  'personalEarningsSettlement',
  'personalActionRequired',
  'personalExpiryRenewal',
] as const

const expectedChinese = [
  '个人资产',
  '已购算力',
  '设备托管',
  '设备状态',
  '收益与结算',
  '待办事项',
  '到期与续费',
] as const

function translationValues(key: string): string[] {
  return [...i18nSource.matchAll(new RegExp(`^\\s*${key}: '([^']+)'`, 'gm'))]
    .map((match) => match[1])
}

test('personal asset picker uses the exact seven concise labels in order', () => {
  const pickerBlock = assetsSource.match(/const personalPanelMeta[\s\S]*?\n\]\)/)?.[0] ?? ''
  const usedKeys = [...pickerBlock.matchAll(/label: t\('([^']+)'\)/g)].map((match) => match[1])

  assert.deepEqual(usedKeys, personalKeys)
  assert.deepEqual(personalKeys.map((key) => translationValues(key)[0]), expectedChinese)
})

test('personal label changes do not replace the supplier-specific picker mapping', () => {
  const supplierBlock = assetsSource.match(/const supplierPanelMeta[\s\S]*?\n\]\)/)?.[0] ?? ''
  const usedKeys = [...supplierBlock.matchAll(/label: t\('([^']+)'\)/g)].map((match) => match[1])

  assert.deepEqual(usedKeys, [
    'merchantOperationsOverview',
    'merchantComputeInventory',
    'merchantHostingFleet',
    'merchantDeviceOperations',
    'merchantSalesSettlement',
    'merchantOperationsAlerts',
    'merchantInventoryMaintenance',
  ])
})
