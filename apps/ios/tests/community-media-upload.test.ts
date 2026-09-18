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

test('community publisher has no image or video selection path in the first review release', () => {
  const page = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(page, /uni\.chooseImage|uni\.chooseVideo|uploadCommunityMedia/)
  assert.doesNotMatch(page, /accept=["'][^"']*(?:image|video)/)
})
