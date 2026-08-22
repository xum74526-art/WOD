import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { getProfileWidgetGroups, type ProfileWidget } from '../src/config/profile-widgets.ts'

const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8')) as {
  pages: Array<{ path: string }>
}
const registeredPages = new Set(pages.pages.map((page) => page.path))
const appIconSource = readFileSync(new URL('../src/components/AppIcon.vue', import.meta.url), 'utf8')

function appIconPaths(): Map<string, string> {
  const pathsBlock = appIconSource.match(/const PATHS:[^{]+\{([\s\S]*?)\n\}/)?.[1] ?? ''
  const entries = new Map<string, string>()
  const entryPattern = /^\s*(?:'([^']+)'|([a-z][\w-]*)):\s*'([^']+)'/gm
  for (const match of pathsBlock.matchAll(entryPattern)) {
    entries.set(match[1] || match[2], match[3])
  }
  return entries
}

const iconPaths = appIconPaths()

function flatten(role: 'personal' | 'supplier', hasSupplierAccess: boolean): ProfileWidget[] {
  return getProfileWidgetGroups(role, hasSupplierAccess).flatMap((group) => group.items)
}

function assertWidgetSet(items: ProfileWidget[]) {
  assert.equal(new Set(items.map((item) => item.key)).size, items.length, 'widget keys must be unique')
  assert.equal(new Set(items.map((item) => item.route)).size, items.length, 'widget routes must be unique')
  items.forEach((item) => assert.ok(iconPaths.has(item.icon), `${item.icon} must exist in AppIcon PATHS`))
  assert.equal(
    new Set(items.map((item) => iconPaths.get(item.icon))).size,
    items.length,
    'actual SVG paths must be unique within a role',
  )

  items.forEach((item) => {
    const pagePath = item.route.split('?')[0].replace(/^\//, '')
    assert.ok(registeredPages.has(pagePath), `${item.route} must exist in pages.json`)
  })
}

test('personal and supplier profiles expose distinct role-aware widget counts', () => {
  const personalWithMerchantAccess = flatten('personal', true)
  const personalBeforeOnboarding = flatten('personal', false)
  const supplier = flatten('supplier', true)

  assert.equal(personalWithMerchantAccess.length, 12)
  assert.equal(personalBeforeOnboarding.length, 12)
  assert.equal(supplier.length, 15)
  assert.ok(!personalBeforeOnboarding.some((item) => item.key === 'onboarding'))
  assert.ok(!personalWithMerchantAccess.some((item) => item.key === 'onboarding'))
  assert.ok(supplier.some((item) => item.route === '/pages/supplier/stats'))
  assert.ok(!personalWithMerchantAccess.some((item) => item.route === '/pages/supplier/stats'))
})

test('all profile widgets use registered routes and non-repeating visual icons', () => {
  assertWidgetSet(flatten('personal', true))
  assertWidgetSet(flatten('personal', false))
  assertWidgetSet(flatten('supplier', true))
})

test('supplier operations and shared account tools remain separate groups', () => {
  const groups = getProfileWidgetGroups('supplier', true)

  assert.deepEqual(groups.map((group) => group.key), ['merchant-operations', 'account-tools'])
  assert.deepEqual(groups.map((group) => group.items.length), [7, 8])
  assert.ok(groups[0].items.every((item) => item.route.includes('/pages/supplier/')))
  assert.ok(groups[1].items.every((item) => !item.route.includes('/pages/supplier/')))
})

test('role-facing aliases use their own AppIcon paths', () => {
  for (const [businessIcon, genericIcon] of [
    ['bank-card', 'wallet'],
    ['verified', 'shield'],
    ['online-service', 'bell'],
  ]) {
    assert.notEqual(iconPaths.get(businessIcon), iconPaths.get(genericIcon), `${businessIcon} must not reuse ${genericIcon}`)
  }
})
