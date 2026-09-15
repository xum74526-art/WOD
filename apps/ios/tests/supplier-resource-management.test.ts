import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string) {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

function exportedFunction(sourceText: string, name: string): string {
  const start = sourceText.indexOf(`export function ${name}`)
  assert.notEqual(start, -1, `${name} must be exported from the supplier API`)
  const next = sourceText.indexOf('\nexport function ', start + 1)
  return sourceText.slice(start, next === -1 ? undefined : next)
}

const pages = JSON.parse(source('../src/pages.json')) as {
  pages?: Array<{ path?: string }>
}
const supplierApi = source('../src/api/supplier.ts')
const devicePage = source('../src/pages/supplier/devices.vue')
const dashboardPage = source('../src/pages/supplier/dashboard.vue')
const profilePage = source('../src/pages/profile/index.vue')
const createPageUrl = new URL('../src/pages/supplier/product-create.vue', import.meta.url)

test('approved sellers have a registered mobile resource-creation page', () => {
  assert.ok(
    pages.pages?.some((page) => page.path === 'pages/supplier/product-create'),
    'pages.json must register the seller resource-creation page',
  )
  assert.ok(existsSync(createPageUrl), 'the seller resource-creation page must exist')
})

test('supplier API exposes only the required create and update resource writes', () => {
  const createResource = exportedFunction(supplierApi, 'createSupplierDevice')
  assert.match(createResource, /url:\s*['"]\/supplier\/devices['"]/)
  assert.match(createResource, /method:\s*['"]POST['"]/)

  const updateResource = exportedFunction(supplierApi, 'updateSupplierDevice')
  assert.match(updateResource, /url:\s*`\/supplier\/devices\/\$\{[^}]+\}`/)
  assert.match(updateResource, /method:\s*['"]PUT['"]/)
  assert.match(updateResource, /expectedVersion:\s*number/)
  assert.match(updateResource, /expected_version:\s*expectedVersion/)
  assert.match(supplierApi, /interface SupplierDeviceItem[\s\S]*version:\s*number/)
})

test('seller resource list is writable and displays the backend card-hour unit directly', () => {
  assert.doesNotMatch(devicePage, /mobileMerchantReadOnly(?:Title|Hint)|read-only-note/)
  assert.match(devicePage, /fmtCardHours\s*\(/)
  assert.doesNotMatch(devicePage, /fmtCH\s*\(\s*d\.price\s*\)/)
  assert.match(devicePage, /createSupplierDevice|pages\/supplier\/product-create/)
  assert.match(devicePage, /updateSupplierDevice/)
})

test('seller mode exposes a clearly labelled compute-resource management entry', () => {
  assert.match(devicePage, /t\('merchantResourceManagement'\)/)
  assert.match(dashboardPage, /pages\/supplier\/devices/)
  assert.match(dashboardPage, /t\('merchantResourceManagement'\)/)
  assert.match(profilePage, /pages\/supplier\/devices/)
  assert.match(profilePage, /t\('merchantResourceManagement'\)/)
})

test('resource creation submits card hours without applying the RMB conversion helper', () => {
  const createPage = source('../src/pages/supplier/product-create.vue')
  assert.match(createPage, /createSupplierDevice/)
  assert.doesNotMatch(createPage, /fromCardHours/)
  assert.match(createPage, /slice\(0, 4\)/)
  assert.match(createPage, /if \(submitting\.value\) return/)
  assert.match(createPage, /if \(!listed\) submitting\.value = false/)
  assert.match(createPage, /ensureClientRequestIntent/)
  assert.match(createPage, /client_request_id:\s*ensureCreateRequestId\(payload\)/)
  assert.match(createPage, /pendingCreateIntent\.value = null/)
  assert.match(createPage, /onBackPress\(\(\) => submitting\.value\)/)
  assert.match(createPage, /:show-back="!submitting"/)
  assert.match(supplierApi, /interface SupplierDeviceCreateInput[\s\S]*client_request_id:\s*string/)
})

test('resource editing preserves four-decimal prices and submits only changed fields', () => {
  assert.match(devicePage, /maximumFractionDigits:\s*4/)
  assert.match(devicePage, /slice\(0, 4\)/)
  assert.match(devicePage, /const changes:\s*SupplierDeviceUpdateInput = \{\}/)
  assert.match(devicePage, /if \(stock !== editTarget\.value\.stock\) changes\.stock = stock/)
  assert.match(devicePage, /updateSupplierDevice\(editTarget\.value\.id, editTarget\.value\.version, changes\)/)
  assert.match(devicePage, /updateSupplierDevice\(device\.id, device\.version, \{ status \}\)/)
})

test('stale resource edits reload the latest device version instead of retrying old data', () => {
  const i18n = source('../src/store/i18n.ts')
  assert.match(devicePage, /error instanceof ApiRequestError/)
  assert.match(devicePage, /error\.statusCode !== 409/)
  assert.match(devicePage, /await load\(\)/)
  assert.match(devicePage, /t\('resourceChangedRefresh'\)/)
  assert.match(i18n, /resourceChangedRefresh:/)
})
