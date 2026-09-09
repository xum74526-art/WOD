import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  COMMUNITY_IMAGE_MAX_BYTES,
  COMMUNITY_VIDEO_MAX_BYTES,
  hasOversizedCommunityImage,
  isCommunityVideoTooLarge,
} from '../src/utils/community-media.ts'

test('community image selection allows exactly 5 MiB and rejects the whole batch when any image is larger', () => {
  assert.equal(COMMUNITY_IMAGE_MAX_BYTES, 5 * 1024 * 1024)
  assert.equal(hasOversizedCommunityImage({ path: 'one.jpg', size: COMMUNITY_IMAGE_MAX_BYTES }), false)
  assert.equal(hasOversizedCommunityImage([
    { path: 'one.jpg', size: COMMUNITY_IMAGE_MAX_BYTES - 1 },
    { path: 'two.png', size: COMMUNITY_IMAGE_MAX_BYTES },
  ]), false)
  assert.equal(hasOversizedCommunityImage([
    { path: 'one.jpg', size: COMMUNITY_IMAGE_MAX_BYTES },
    { path: 'two.png', size: COMMUNITY_IMAGE_MAX_BYTES + 1 },
  ]), true)
})

test('oversized chosen images stop before creating any draft or starting upload', () => {
  const publishPage = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')
  const chooseImageSuccess = publishPage.slice(
    publishPage.indexOf('uni.chooseImage({'),
    publishPage.indexOf('\n    })', publishPage.indexOf('uni.chooseImage({')) + 7,
  )

  assert.match(
    chooseImageSuccess,
    /if \(hasOversizedCommunityImage\(res\.tempFiles\)\) \{[\s\S]*t\('communityImageTooLarge'\)[\s\S]*return[\s\S]*const paths/,
  )
  assert.match(chooseImageSuccess, /const item: ImageDraft[\s\S]*imageDrafts\.value\.push\(item\)[\s\S]*void uploadImage\(item\)/)
})

test('community video selection allows exactly 20 MiB and rejects any larger file', () => {
  assert.equal(COMMUNITY_VIDEO_MAX_BYTES, 20 * 1024 * 1024)
  assert.equal(isCommunityVideoTooLarge(COMMUNITY_VIDEO_MAX_BYTES - 1), false)
  assert.equal(isCommunityVideoTooLarge(COMMUNITY_VIDEO_MAX_BYTES), false)
  assert.equal(isCommunityVideoTooLarge(COMMUNITY_VIDEO_MAX_BYTES + 1), true)
})

test('oversized chosen videos stop before creating a draft or starting upload', () => {
  const publishPage = readFileSync(new URL('../src/pages/community/publish.vue', import.meta.url), 'utf8')
  const chooseVideoSuccess = publishPage.slice(
    publishPage.indexOf('uni.chooseVideo({'),
    publishPage.indexOf('\n    })', publishPage.indexOf('uni.chooseVideo({')) + 7,
  )

  assert.match(
    chooseVideoSuccess,
    /if \(isCommunityVideoTooLarge\(res\.size\)\) \{[\s\S]*t\('communityVideoTooLarge'\)[\s\S]*return[\s\S]*const item: VideoDraft/,
  )
  assert.match(chooseVideoSuccess, /extension: \['mp4', 'mov', 'webm'\]/)
  assert.match(chooseVideoSuccess, /videoDraft\.value = item[\s\S]*void uploadVideo\(item\)/)
})
