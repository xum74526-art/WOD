import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { extname, relative } from 'node:path'
import test from 'node:test'

const srcRoot = new URL('../src/', import.meta.url)

function walk(directory: URL): URL[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const child = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory)
    return entry.isDirectory() ? walk(child) : [child]
  })
}

test('mobile writes stay inside the approved merchant transaction loop', () => {
  const offenders: string[] = []
  for (const file of walk(srcRoot)) {
    if (!['.ts', '.vue', '.json'].includes(extname(file.pathname))) continue
    if (!statSync(file).isFile()) continue
    const source = readFileSync(file, 'utf8')
    const checks: Array<[RegExp, string]> = [
      [/\/finance\//, 'finance administration route'],
      [/\/supplier\/profile[`'"]?[\s\S]{0,100}?method:\s*['"](?:POST|PUT|PATCH|DELETE)['"]/, 'merchant profile write'],
      [/\/supplier\/devices(?:\/\$\{[^}]+\})?[`'"]?[\s\S]{0,100}?method:\s*['"](?:PATCH|DELETE)['"]/, 'unsupported merchant resource write'],
      [/\/buy-requests\/\$\{[^}]+\}\/quotes[`'"][\s\S]{0,100}?method:\s*['"]POST['"]/, 'merchant quote write'],
    ]
    for (const [pattern, label] of checks) {
      if (pattern.test(source)) offenders.push(`${relative(srcRoot.pathname, file.pathname)}: ${label}`)
    }
  }
  assert.deepEqual(offenders, [])

  const supplierApi = readFileSync(new URL('api/supplier.ts', srcRoot), 'utf8')
  const supplierOrders = readFileSync(new URL('pages/supplier/orders.vue', srcRoot), 'utf8')
  assert.match(supplierApi, /url: '\/supplier\/register', method: 'POST'/)
  assert.match(supplierApi, /url: `\/orders\/\$\{id\}\/deliver`/)
  assert.match(supplierOrders, /order\.can_deliver \?\? order\.status === 'paid'/)
})
