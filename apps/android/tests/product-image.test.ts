import assert from 'node:assert/strict'
import test from 'node:test'

import { DEFAULT_PRODUCT_IMAGE, fallbackProductImage, resolveProductImage } from '../src/utils/product-image.ts'

test('product images map the legacy generic API path to a bundled App asset', () => {
  assert.equal(resolveProductImage('/static/gpu/gpu.png'), DEFAULT_PRODUCT_IMAGE)
  assert.equal(resolveProductImage(''), DEFAULT_PRODUCT_IMAGE)
})

test('product images keep valid bundled and HTTPS paths', () => {
  assert.equal(resolveProductImage('/static/gpu/RTX4090.jpg'), '/static/gpu/RTX4090.jpg')
  assert.equal(resolveProductImage('https://cdn.example.com/gpu.jpg'), 'https://cdn.example.com/gpu.jpg')
  assert.equal(resolveProductImage('javascript:alert(1)'), DEFAULT_PRODUCT_IMAGE)
})

test('missing or case-mismatched provider image paths use a bundled model-family photo', () => {
  assert.equal(
    resolveProductImage('/static/gpu/RTX5070TI.jpg', 'RTX5070TI'),
    '/static/gpu/RTX5070.jpg',
  )
  assert.equal(
    resolveProductImage('/static/gpu/RTX2080TI.jpg', 'RTX2080TI'),
    '/static/gpu/RTX2080Ti.jpg',
  )
  assert.equal(fallbackProductImage('RTX 4060 Ti'), '/static/gpu/RTX4070.jpg')
})

test('provider model paths with case-sensitive App filenames resolve to real bundled images', () => {
  assert.equal(resolveProductImage('/static/gpu/VGPU32.jpg', 'VGPU32'), '/static/gpu/vGPU32.jpg')
  assert.equal(resolveProductImage('/static/gpu/VGPU48.jpg', 'VGPU48'), '/static/gpu/vGPU48.jpg')
  assert.equal(resolveProductImage('/static/gpu/MTTS4000.jpg', 'MTTS4000'), '/static/gpu/MTTS4000.jpg')
  assert.equal(resolveProductImage('/static/gpu/RTX4070TI.jpg', 'RTX4070TI'), '/static/gpu/RTX4070.jpg')
})

test('all supported KAI model families avoid the generic product placeholder', () => {
  const supportedKaiModels = [
    'A10', 'A100', 'A30', 'A40', 'A4000', 'A5000', 'A6000', 'A800', 'B100', 'B200', 'B300',
    'H100', 'H200', 'L40', 'L40S', 'RTX2000', 'RTX2060', 'RTX2070',
    'RTX2070SUPER', 'RTX2080', 'RTX2080TI', 'RTX3050', 'RTX3060',
    'RTX3060TI', 'RTX3070', 'RTX3070TI', 'RTX3080', 'RTX3080TI',
    'RTX3090', 'RTX3090TI', 'RTX4000', 'RTX4060', 'RTX4060TI',
    'RTX4070', 'RTX4070SUPER', 'RTX4070TI', 'RTX4080', 'RTX4080SUPER',
    'RTX4090', 'RTX4090D', 'RTX4500', 'RTX5000', 'RTX5060', 'RTX5060TI',
    'RTX5070', 'RTX5070TI', 'RTX5080', 'RTX5090', 'RTX5880', 'RTX6000',
    'RTXPRO6000', 'T4', 'V100',
  ]

  for (const model of supportedKaiModels) {
    assert.notEqual(fallbackProductImage(model), DEFAULT_PRODUCT_IMAGE, model)
  }

  assert.equal(fallbackProductImage('B100'), '/static/gpu/H200.jpg')
  assert.equal(fallbackProductImage('B200'), '/static/gpu/H200.jpg')
  assert.equal(fallbackProductImage('B300'), '/static/gpu/H200.jpg')
})
