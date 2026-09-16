import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const privacyConfig = JSON.parse(
  readFileSync(new URL('../src/androidPrivacy.json', import.meta.url), 'utf8'),
) as {
  version?: string
  prompt?: string
  title?: string
  message?: string
  buttonAccept?: string
  buttonRefuse?: string
  hrefLoader?: string
  backToExit?: string
  second?: {
    message?: string
    buttonAccept?: string
    buttonRefuse?: string
  }
  disagreeMode?: {
    support?: boolean
    loadNativePlugins?: boolean
    visitorEntry?: boolean
  }
}

function linksIn(value = '') {
  return [...value.matchAll(/href="([^"]+)"/g)].map((match) => match[1])
}

test('Android uses the blocking native privacy template before app startup', () => {
  assert.equal(privacyConfig.prompt, 'template')
  assert.match(privacyConfig.version || '', /^\d+$/)
  assert.match(privacyConfig.title || '', /隱私政策/)
  assert.match(privacyConfig.buttonAccept || '', /同意/)
  assert.match(privacyConfig.buttonRefuse || '', /不同意/)
  assert.equal(privacyConfig.hrefLoader, 'system')
  assert.equal(privacyConfig.backToExit, 'true')
  assert.equal(privacyConfig.disagreeMode?.support, false)
  assert.equal(privacyConfig.disagreeMode?.loadNativePlugins, false)
  assert.equal(privacyConfig.disagreeMode?.visitorEntry, false)
})

test('the startup prompt links to the public ZTW agreement and privacy policy', () => {
  const expected = [
    'https://wod.kai.com/terms',
    'https://wod.kai.com/privacy',
  ]
  assert.deepEqual(linksIn(privacyConfig.message), expected)
  assert.deepEqual(linksIn(privacyConfig.second?.message), expected)
  assert.match(privacyConfig.second?.buttonAccept || '', /同意/)
  assert.match(privacyConfig.second?.buttonRefuse || '', /退出/)

  for (const value of expected) {
    const url = new URL(value)
    assert.equal(url.protocol, 'https:')
    assert.equal(url.hostname, 'wod.kai.com')
  }
})
