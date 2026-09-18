import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import test from 'node:test'

import { DEFAULT_PRODUCT_IMAGE, fallbackProductImage, resolveProductImage } from '../src/utils/product-image.ts'

test('empty API values and image load failures use the generic bundled image', () => {
  for (const value of [undefined, null, '', '   ']) {
    assert.equal(resolveProductImage(value, 'H100'), DEFAULT_PRODUCT_IMAGE)
  }

  for (const model of ['H100', 'RTX 4090', 'B300', '', undefined]) {
    assert.equal(fallbackProductImage(model), DEFAULT_PRODUCT_IMAGE)
  }
})
test('allowlisted local GPU paths resolve to canonical bundled images', () => {
  const cases: Array<[string, string]> = [
    ['/static/gpu/H100.jpg', '/static/gpu/H100.jpg'],
    ['/static/gpu/rtx4090.JPG', '/static/gpu/RTX4090.jpg'],
    ['/static/gpu/RTX 4060 Ti.webp', '/static/gpu/RTX4070.jpg'],
    ['/static/gpu/RTX5070TI.jpg', '/static/gpu/RTX5070.jpg'],
    ['/static/gpu/RTX2080TI.jpg', '/static/gpu/RTX2080Ti.jpg'],
    ['/static/gpu/VGPU32.jpg', '/static/gpu/vGPU32.jpg'],
    ['/static/gpu/B200.jpg', '/static/gpu/B200.jpg'],
    ['/static/gpu/B300.jpg', '/static/gpu/B300.jpg'],
    ['/static/gpu/MI300X.jpg', '/static/gpu/MI300X.jpg'],
    ['/static/gpu/P100.jpg', '/static/gpu/P100.jpg'],
  ]

  for (const [source, expected] of cases) {
    assert.equal(resolveProductImage(source), expected)
  }
})

test('remote, malformed, and unknown paths cannot bypass the local allowlist', () => {
  const rejected = [
    'https://cdn.example.com/RTX4090.jpg',
    'http://127.0.0.1/RTX4090.jpg',
    '//cdn.example.com/RTX4090.jpg',
    'javascript:alert(1)',
    'data:image/png;base64,AAAA',
    'file:///static/gpu/RTX4090.jpg',
    '/static/gpu/../RTX4090.jpg',
    '/static/gpu/%2e%2e%2fRTX4090.jpg',
    '/static/gpu/RTX4090.jpg?cache=1',
    '/static/gpu/RTX4090.jpg#preview',
    '/static/gpu/not-a-real-model.jpg',
    '/static/gpu/gpu.png',
    '/static/products/not-a-real-product.png',
  ]

  for (const value of rejected) {
    assert.equal(resolveProductImage(value, 'RTX4090'), DEFAULT_PRODUCT_IMAGE, value)
  }
})

test('every supported provider model resolves to an existing bundled asset', () => {
  const supportedModels = [
    'A10', 'A30', 'A40', 'A100', 'A4000', 'A5000', 'A6000', 'A800',
    'B100', 'B200', 'B300', 'GRIDK1', 'GRIDK2', 'GTX1080', 'GTX1080TI',
    'H20', 'H100', 'H200', 'H800', 'K40', 'K80', 'L4', 'L40', 'L40S',
    'M40', 'MI300X', 'MTTS4000', 'P4', 'P40', 'P100', 'RTX2000', 'RTX2060', 'RTX2070',
    'RTX2070SUPER', 'RTX2080', 'RTX2080TI', 'RTX3050', 'RTX3060',
    'RTX3060TI', 'RTX3070', 'RTX3070TI', 'RTX3080', 'RTX3080TI',
    'RTX3090', 'RTX3090TI', 'RTX4000', 'RTX4000ADA', 'RTX4060',
    'RTX4060TI', 'RTX4070', 'RTX4070SUPER', 'RTX4070TI', 'RTX4080',
    'RTX4080SUPER', 'RTX4090', 'RTX4090D', 'RTX4500', 'RTX5000',
    'RTX5000ADA', 'RTX5060', 'RTX5060TI', 'RTX5070', 'RTX5070TI',
    'RTX5080', 'RTX5090', 'RTX5880', 'RTX6000', 'RTX6000ADA',
    'RTXPRO6000', 'T4', 'V100', 'VGPU32', 'VGPU48',
  ]

  for (const model of supportedModels) {
    const image = resolveProductImage(`/static/gpu/${model}.jpg`)
    assert.notEqual(image, DEFAULT_PRODUCT_IMAGE, model)
    assert.equal(existsSync(new URL(`../src${image}`, import.meta.url)), true, image)
  }
})
