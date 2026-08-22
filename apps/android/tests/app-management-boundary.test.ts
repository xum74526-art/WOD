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

test('mobile excludes Web-only finance and merchant management writes', () => {
  const offenders: string[] = []
  for (const file of walk(srcRoot)) {
    if (!['.ts', '.vue', '.json'].includes(extname(file.pathname))) continue
    if (!statSync(file).isFile()) continue
    const source = readFileSync(file, 'utf8')
    const checks: Array<[RegExp, string]> = [
      [/\/finance\//, 'finance administration route'],
      [/\/pages\/supplier\/(?:register|product-create)/, 'merchant write page'],
      [/\/supplier\/(?:register|profile)[`'"]?[\s\S]{0,100}?method:\s*['"](?:POST|PUT|PATCH|DELETE)['"]/, 'merchant profile write'],
      [/\/supplier\/devices(?:\/\$\{[^}]+\})?[`'"]?[\s\S]{0,100}?method:\s*['"](?:POST|PUT|PATCH|DELETE)['"]/, 'merchant device write'],
      [/\/orders\/\$\{[^}]+\}\/deliver/, 'merchant delivery write'],
      [/\/buy-requests\/\$\{[^}]+\}\/quotes[`'"][\s\S]{0,100}?method:\s*['"]POST['"]/, 'merchant quote write'],
    ]
    for (const [pattern, label] of checks) {
      if (pattern.test(source)) offenders.push(`${relative(srcRoot.pathname, file.pathname)}: ${label}`)
    }
  }
  assert.deepEqual(offenders, [])
})
