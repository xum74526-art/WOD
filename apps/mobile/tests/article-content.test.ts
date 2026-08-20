import assert from 'node:assert/strict'
import test from 'node:test'

import { articlePlainText, articlePreview, isArticleHtml } from '../src/utils/article-content.ts'

test('article previews remove markup, decode entities, and stay bounded', () => {
  const html = `<img src="https://example.com/cover.png"><p>${'GPU &amp; compute '.repeat(30)}</p>`
  const preview = articlePreview(null, html, 'Fallback')

  assert.equal(preview.includes('<img'), false)
  assert.equal(preview.includes('&amp;'), false)
  assert.equal(preview.length, 240)
  assert.equal(preview.endsWith('...'), true)
})

test('plain article text removes active blocks and rich articles are detected', () => {
  assert.equal(articlePlainText('<script>alert(1)</script><p>Hello&nbsp;GPU</p>'), 'Hello GPU')
  assert.equal(isArticleHtml('<p>Hello</p>'), true)
  assert.equal(isArticleHtml('Hello'), false)
})
