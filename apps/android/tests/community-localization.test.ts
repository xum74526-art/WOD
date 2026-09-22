import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { localizeInternalBrandText, localizePersonName } from '../src/utils/localize-content.ts'

const indexSource = readFileSync(new URL('../src/pages/community/index.vue', import.meta.url), 'utf8')
const detailSource = readFileSync(new URL('../src/pages/community/detail.vue', import.meta.url), 'utf8')
const localeSource = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

test('community categories and empty states follow the active language', () => {
  assert.match(indexSource, /:items="\[t\('recommend'\), t\('follow'\), t\('latest'\)\]"/)
  assert.match(indexSource, /:text="searching \? t\('noResults'\) : t\('noPosts'\)"/)
  assert.match(detailSource, /:text="t\('暂无评论，快来抢沙发'\)"/)

  assert.doesNotMatch(indexSource, /:items="\['推荐','关注','最新','视频'\]"/)
  assert.doesNotMatch(indexSource, /searching \? '没有找到相关内容' : '暂无动态'/)
  assert.doesNotMatch(detailSource, /<EmptyState text="暂无评论，快来抢沙发"/)
})

test('community navigation and empty-state keys have English translations', () => {
  for (const translation of [
    "recommend: 'Hot'",
    "follow: 'Following'",
    "latest: 'Latest'",
    "video: 'Video'",
    "noPosts: 'No posts yet'",
    "noResults: 'No results found'",
    "'暂无评论，快来抢沙发': 'No comments yet. Start the conversation.'",
  ]) {
    assert.ok(localeSource.includes(translation), `missing translation: ${translation}`)
  }
})

test('first-party market posts remove mixed Chinese from English display copy', () => {
  assert.equal(localizePersonName('KAI星算平台行情', 'en'), 'KAI Platform Market')
  assert.equal(
    localizeInternalBrandText(
      'The current reference price in 北美 is 5.04 CH/h. KAI星算 market data.',
      'wod-market',
      'en',
    ),
    'The current reference price in North America is 5.04 CH/h. KAI Compute Market data.',
  )
  assert.equal(
    localizeInternalBrandText('北美用戶原文', 'user-post', 'en'),
    '北美用戶原文',
    'user-authored content must remain untouched',
  )
})
