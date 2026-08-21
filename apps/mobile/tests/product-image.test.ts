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
    '/static/gpu/RTX5090.jpg',
  )
  assert.equal(
    resolveProductImage('/static/gpu/RTX2080TI.jpg', 'RTX2080TI'),
    '/static/gpu/RTX2080Ti.jpg',
  )
  assert.equal(fallbackProductImage('RTX 4060 Ti'), '/static/gpu/RTX4080.jpg')
})

test('provider model paths with case-sensitive App filenames resolve to real bundled images', () => {
  assert.equal(resolveProductImage('/static/gpu/VGPU32.jpg', 'VGPU32'), '/static/gpu/vGPU32.jpg')
  assert.equal(resolveProductImage('/static/gpu/VGPU48.jpg', 'VGPU48'), '/static/gpu/vGPU48.jpg')
  assert.equal(resolveProductImage('/static/gpu/MTTS4000.jpg', 'MTTS4000'), '/static/gpu/MTTS4000.jpg')
  assert.equal(resolveProductImage('/static/gpu/RTX4070TI.jpg', 'RTX4070TI'), '/static/gpu/RTX4070Ti.jpg')
})
