import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  BILIBILI_REFERER,
  BLOCK_UNTRUSTED_PLAYER_NAVIGATION,
  buildCommunityVideoDesktopUserAgent,
  buildCommunityVideoPlayerUrl,
  buildCommunityVideoSourceUrl,
  openNativeCommunityVideo,
  requiresCommunityVideoDesktopUserAgent,
  type CommunityVideoFailure,
  type NativeCommunityVideoRuntime,
} from '../src/utils/community-video.ts'

const validSource = {
  content_type: 'video',
  origin: 'aggregated',
  video_provider: 'bilibili',
  video_id: 'BV1Ab411C7De',
} as const

function fakeNativeRuntime() {
  const capture: {
    id: string
    styles: Record<string, any>
    overrideOptions: Record<string, unknown>
    intercepted?: (event: unknown) => void
    errorListener?: (event: unknown) => void
    closeListener?: (event: unknown) => void
    loadedUrl: string
    loadHeaders: Record<string, string>
    animation: string
    closeAnimation: string
    createCount: number
    showCount: number
    originalUserAgent: string
    currentUserAgent: string
    userAgentCalls: Array<{ userAgent: string; checkplus?: boolean }>
    throwOnShow: boolean
  } = {
    id: '',
    styles: {},
    overrideOptions: {},
    loadedUrl: '',
    loadHeaders: {},
    animation: '',
    closeAnimation: '',
    createCount: 0,
    showCount: 0,
    originalUserAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Html5Plus/1.0',
    currentUserAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Html5Plus/1.0',
    userAgentCalls: [],
    throwOnShow: false,
  }
  const runtime: NativeCommunityVideoRuntime = {
    navigator: {
      getUserAgent() { return capture.currentUserAgent },
      setUserAgent(userAgent, checkplus) {
        capture.currentUserAgent = userAgent
        capture.userAgentCalls.push({ userAgent, checkplus })
      },
    },
    webview: {
      create(_url, id, styles) {
        capture.createCount += 1
        capture.id = id
        capture.styles = styles
        return {
          overrideUrlLoading(options, callback) {
            capture.overrideOptions = options
            capture.intercepted = callback
          },
          addEventListener(event, callback) {
            if (event === 'error') capture.errorListener = callback
            else capture.closeListener = callback
          },
          loadURL(url, headers = {}) {
            capture.loadedUrl = url
            capture.loadHeaders = headers
          },
          show(animation = '') {
            if (capture.throwOnShow) {
              capture.throwOnShow = false
              throw new Error('show failed')
            }
            capture.animation = animation
            capture.showCount += 1
          },
          close(animation = '') { capture.closeAnimation = animation },
        }
      },
    },
  }
  return { runtime, capture }
}

test('player URL is reconstructed from a trusted Bilibili provider and BV id', () => {
  assert.equal(
    buildCommunityVideoPlayerUrl(validSource),
    'https://player.bilibili.com/player.html?bvid=BV1Ab411C7De&p=1&autoplay=false&poster=true&danmaku=false',
  )
  assert.equal(buildCommunityVideoSourceUrl(validSource), 'https://www.bilibili.com/video/BV1Ab411C7De/')
})

test('player URL rejects untrusted providers, post types, origins and malformed ids', () => {
  const rejected = [
    { ...validSource, content_type: 'article' },
    { ...validSource, origin: 'user' },
    { ...validSource, video_provider: 'youtube' },
    { ...validSource, video_id: '' },
    { ...validSource, video_id: 'BV1Ab411C7De&autoplay=0' },
    { ...validSource, video_id: 'https://evil.example/video' },
  ]
  for (const source of rejected) {
    assert.equal(buildCommunityVideoPlayerUrl(source), '')
    assert.equal(buildCommunityVideoSourceUrl(source), '')
  }
})

test('desktop player identity removes mobile WebView markers and has a stable fallback version', () => {
  const userAgent = buildCommunityVideoDesktopUserAgent(
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
  )
  assert.match(userAgent, /Windows NT 10\.0/)
  assert.match(userAgent, /Chrome\/120\.0\.0\.0/)
  assert.doesNotMatch(userAgent, /iPhone|Mobile|Html5Plus/)
  assert.equal(requiresCommunityVideoDesktopUserAgent(captureAndroidWebViewUserAgent()), true)
  assert.equal(
    requiresCommunityVideoDesktopUserAgent(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Html5Plus/1.0',
    ),
    false,
  )
})

function captureAndroidWebViewUserAgent(): string {
  return 'Mozilla/5.0 (Linux; Android 14; Test; wv) AppleWebKit/537.36 Chrome/146.0.7680.119 Mobile Safari/537.36 Html5Plus/1.0'
}

test('native playback uses an isolated in-app WebView and the official Referer', () => {
  const { runtime, capture } = fakeNativeRuntime()
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  assert.match(capture.id, /^wod-community-video-/)
  assert.equal(capture.styles.disablePlus, true)
  assert.equal(capture.styles.hardwareAccelerated, true)
  assert.equal(capture.styles.plusrequire, 'none')
  assert.equal(capture.styles['uni-app'], 'none')
  assert.equal(capture.styles.backButtonAutoControl, 'close')
  assert.equal(capture.styles.popGesture, 'close')
  assert.equal(capture.styles.titleNView.autoBackButton, true)
  assert.equal(capture.styles.titleNView.titleText, '视频')
  assert.deepEqual(capture.userAgentCalls, [])
  assert.deepEqual(capture.styles.additionalHttpHeaders, { Referer: BILIBILI_REFERER })
  assert.deepEqual(capture.overrideOptions, {
    effect: 'instant',
    mode: 'reject',
    match: BLOCK_UNTRUSTED_PLAYER_NAVIGATION,
    exclude: 'none',
  })
  assert.equal(capture.loadedUrl, buildCommunityVideoPlayerUrl(validSource))
  assert.deepEqual(capture.loadHeaders, { Referer: BILIBILI_REFERER })
  assert.equal(capture.animation, 'pop-in')
})

test('navigation policy permits only the documented player and its official mobile redirect', () => {
  const blocked = new RegExp(BLOCK_UNTRUSTED_PLAYER_NAVIGATION)
  assert.equal(blocked.test(buildCommunityVideoPlayerUrl(validSource)), false)
  assert.equal(
    blocked.test('https://www.bilibili.com/blackboard/webplayer/mbplayer.html?bvid=BV1Ab411C7De&p=1'),
    false,
  )
  assert.equal(blocked.test('https://www.bilibili.com/video/BV1Ab411C7De/'), true)
  assert.equal(blocked.test('https://evil.example/player'), true)
})

test('native playback closes the player and reports a load failure', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const failures: CommunityVideoFailure[] = []
  openNativeCommunityVideo(runtime, validSource, '视频', failure => failures.push(failure))
  capture.errorListener?.({ message: 'network unavailable' })
  assert.equal(capture.closeAnimation, 'none')
  assert.equal(failures[0]?.code, 'player-load-failed')
  assert.equal(failures[0]?.message, 'network unavailable')
  assert.deepEqual(capture.userAgentCalls, [])
})

test('blocked top-level navigation closes the player and reports a recoverable failure', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const failures: CommunityVideoFailure[] = []
  openNativeCommunityVideo(runtime, validSource, '视频', failure => failures.push(failure))
  capture.intercepted?.({ url: 'https://evil.example/player' })
  assert.equal(capture.closeAnimation, 'none')
  assert.equal(failures[0]?.code, 'player-load-failed')
})

test('repeated taps reuse one active player and closing permits a fresh player', () => {
  const { runtime, capture } = fakeNativeRuntime()
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  assert.equal(capture.createCount, 1)
  assert.equal(capture.showCount, 2)

  capture.closeListener?.({})
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  assert.equal(capture.createCount, 2)
})

test('iOS keeps its native UA when an active player has to be reopened', () => {
  const { runtime, capture } = fakeNativeRuntime()
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  capture.throwOnShow = true
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  assert.deepEqual(capture.userAgentCalls, [])
})

test('invalid video data never creates a native WebView', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const failures: CommunityVideoFailure[] = []
  assert.equal(
    openNativeCommunityVideo(runtime, { ...validSource, video_id: 'bad' }, '视频', failure => failures.push(failure)),
    false,
  )
  assert.equal(capture.id, '')
  assert.equal(failures[0]?.code, 'invalid-video-source')
})

test('community list opens video details before playback and preserves comments', () => {
  const indexPage = readFileSync(new URL('../src/pages/community/index.vue', import.meta.url), 'utf8')
  const detailPage = readFileSync(new URL('../src/pages/community/detail.vue', import.meta.url), 'utf8')
  const locale = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')

  assert.match(indexPage, /class="card dcard" @tap="goDetail\(d\.id\)"/)
  assert.match(indexPage, /class="dvideo" @tap\.stop="goDetail\(d\.id\)"/)
  assert.doesNotMatch(indexPage, /openCommunityVideo|function openVideo|function openPost/)
  assert.match(indexPage, /d\.source_url && d\.content_type !== 'video'/)
  assert.match(detailPage, /v-if="userVideoUrl\(post\)"/)
  assert.match(detailPage, /v-if="playerUrl\(post\)"/)
  assert.match(detailPage, /openCommunityVideo\(value, t\('video'\)/)
  assert.match(detailPage, /v-for="c in comments"/)
  assert.match(detailPage, /v-model="commentText"/)
  assert.match(detailPage, /videoOpenExternalHint/)
  assert.match(detailPage, /if \(confirm\) openExternalLink/)
  assert.equal((locale.match(/videoOpenExternalHint:/g) || []).length, 2)
})
