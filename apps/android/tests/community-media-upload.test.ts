import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  COMMUNITY_IMAGE_MAX_BYTES,
  COMMUNITY_VIDEO_MAX_BYTES,
  hasOversizedCommunityImage,
  isCommunityVideoTooLarge,
} from '../src/utils/community-media.ts'

test('community image limit allows exactly 5 MiB and rejects an oversized batch', () => {
  assert.equal(COMMUNITY_IMAGE_MAX_BYTES, 5 * 1024 * 1024)
  assert.equal(hasOversizedCommunityImage({ size: COMMUNITY_IMAGE_MAX_BYTES - 1 }), false)
  assert.equal(hasOversizedCommunityImage({ size: COMMUNITY_IMAGE_MAX_BYTES }), false)
  assert.equal(hasOversizedCommunityImage({ size: COMMUNITY_IMAGE_MAX_BYTES + 1 }), true)
  assert.equal(hasOversizedCommunityImage([
    { size: COMMUNITY_IMAGE_MAX_BYTES },
    { size: COMMUNITY_IMAGE_MAX_BYTES + 1 },
  ]), true)
})

test('community video limit allows exactly 20 MiB and rejects the next byte', () => {
  assert.equal(COMMUNITY_VIDEO_MAX_BYTES, 20 * 1024 * 1024)
  assert.equal(isCommunityVideoTooLarge(COMMUNITY_VIDEO_MAX_BYTES - 1), false)
  assert.equal(isCommunityVideoTooLarge(COMMUNITY_VIDEO_MAX_BYTES), false)
  assert.equal(isCommunityVideoTooLarge(COMMUNITY_VIDEO_MAX_BYTES + 1), true)
})

test('community publisher rejects an oversized image batch before drafting or uploading it', () => {
  const page = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')
  const selection = page.indexOf('success: (res) => {', page.indexOf('uni.chooseImage'))
  const limitCheck = page.indexOf('if (hasOversizedCommunityImage(res.tempFiles))', selection)
  const rejection = page.indexOf("t('communityImageTooLarge')", limitCheck)
  const earlyReturn = page.indexOf('return', rejection)
  const paths = page.indexOf('const paths =', selection)
  const draft = page.indexOf('const item: ImageDraft', selection)
  const upload = page.indexOf('void uploadImage(item)', selection)

  assert.ok(selection >= 0)
  assert.ok(limitCheck > selection)
  assert.ok(rejection > limitCheck)
  assert.ok(earlyReturn > rejection)
  assert.ok(paths > earlyReturn)
  assert.ok(draft > paths)
  assert.ok(upload > draft)
})

test('community publisher rejects an oversized selection before drafting or uploading it', () => {
  const page = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')
  const selection = page.indexOf('success: (res) => {', page.indexOf('uni.chooseVideo'))
  const limitCheck = page.indexOf('if (isCommunityVideoTooLarge(res.size))', selection)
  const rejection = page.indexOf("t('communityVideoTooLarge')", limitCheck)
  const earlyReturn = page.indexOf('return', rejection)
  const draft = page.indexOf('const item: VideoDraft', selection)
  const upload = page.indexOf('void uploadVideo(item)', selection)

  assert.ok(selection >= 0)
  assert.ok(limitCheck > selection)
  assert.ok(rejection > limitCheck)
  assert.ok(earlyReturn > rejection)
  assert.ok(draft > earlyReturn)
  assert.ok(upload > draft)
})
