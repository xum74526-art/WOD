import assert from 'node:assert/strict'
import test from 'node:test'

import { DEFAULT_PRODUCT_IMAGE, fallbackProductImage, resolveProductImage } from '../src/utils/product-image.ts'

test('every model uses the reviewed neutral App illustration', () => {
  for (const model of ['H100', 'RTX 4090', 'B300', '', undefined]) {
    assert.equal(fallbackProductImage(model), DEFAULT_PRODUCT_IMAGE)
  }
})

test('legacy, remote, and unsafe image paths cannot bypass the reviewed asset', () => {
  for (const value of [
    '',
    '/static/gpu/RTX4090.jpg',
    '/static/products/gpu.png',
    'https://cdn.example.com/gpu.jpg',
    'http://127.0.0.1/gpu.jpg',
    'javascript:alert(1)',
  ]) {
    assert.equal(resolveProductImage(value, 'RTX4090'), DEFAULT_PRODUCT_IMAGE)
  }
})
