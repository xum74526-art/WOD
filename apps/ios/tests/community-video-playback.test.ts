import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  BILIBILI_REFERER,
  BLOCK_UNTRUSTED_PLAYER_NAVIGATION,
  COMMUNITY_VIDEO_PLAYBACK_RATES,
  buildCommunityVideoDesktopUserAgent,
  buildCommunityVideoPlayerUrl,
  buildCommunityVideoSourceUrl,
  openNativeCommunityVideo,
  requiresCommunityVideoDesktopUserAgent,
  resolveCommunityVideoStreamUrl,
  type CommunityVideoFailure,
  type NativeCommunityVideoRuntime,
} from '../src/utils/community-video.ts'

const validSource = {
  content_type: 'video',
  origin: 'aggregated',
  video_provider: 'bilibili',
  video_id: 'BV1Ab411C7De',
} as const

function fakeNativeRuntime(autoLoad = true) {
  const capture: {
    id: string
    styles: Record<string, any>
    overrideOptions: Record<string, unknown>
    intercepted?: (event: unknown) => void
    loadedListener?: (event: unknown) => void
    errorListener?: (event: unknown) => void
    closeListener?: (event: unknown) => void
    loadedUrl: string
    loadHeaders: Record<string, string>
    loadUserAgent: string
    animation: string
    closeAnimation: string
    createCount: number
    showCount: number
    originalUserAgent: string
    currentUserAgent: string
    userAgentCalls: Array<{ userAgent: string; checkplus?: boolean }>
    throwOnShow: boolean
    appendedCount: number
    videoStyles: Record<string, any>
    videoPlayCount: number
    videoCloseCount: number
    videoPlaybackRates: number[]
    videoListeners: Record<string, ((event: unknown) => void) | undefined>
    titleButtonStyles: Record<string, any>
    actionSheetStyles: Record<string, any>
    actionSheetCallback?: (result: { index?: number }) => void
  } = {
    id: '',
    styles: {},
    overrideOptions: {},
    loadedUrl: '',
    loadHeaders: {},
    loadUserAgent: '',
    animation: '',
    closeAnimation: '',
    createCount: 0,
    showCount: 0,
    originalUserAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Html5Plus/1.0',
    currentUserAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Html5Plus/1.0',
    userAgentCalls: [],
    throwOnShow: false,
    appendedCount: 0,
    videoStyles: {},
    videoPlayCount: 0,
    videoCloseCount: 0,
    videoPlaybackRates: [],
    videoListeners: {},
    titleButtonStyles: {},
    actionSheetStyles: {},
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
            if (event === 'loaded') capture.loadedListener = callback
            else if (event === 'error') capture.errorListener = callback
            else capture.closeListener = callback
          },
          loadURL(url, headers = {}) {
            capture.loadedUrl = url
            capture.loadHeaders = headers
            capture.loadUserAgent = capture.currentUserAgent
            if (autoLoad) capture.loadedListener?.({})
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
          append() { capture.appendedCount += 1 },
          setTitleNViewButtonStyle(_index, styles) { capture.titleButtonStyles = styles },
        }
      },
    },
    video: {
      createVideoPlayer(_id, styles) {
        capture.videoStyles = styles
        return {
          addEventListener(event, callback) { capture.videoListeners[event] = callback },
          play() {
            capture.videoPlayCount += 1
            capture.videoListeners.play?.({})
          },
          playbackRate(rate) { capture.videoPlaybackRates.push(rate) },
          close() { capture.videoCloseCount += 1 },
        }
      },
    },
    nativeUI: {
      actionSheet(styles, callback) {
        capture.actionSheetStyles = styles
        capture.actionSheetCallback = callback
        return {}
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

test('the app resolves the trusted Bilibili page to a progressive HTTPS stream', async () => {
  const requests: string[] = []
  const resolved = await resolveCommunityVideoStreamUrl(validSource, async (url) => {
    requests.push(url)
    if (url.includes('/pagelist?')) return { code: 0, data: [{ cid: 987654321 }] }
    return { code: 0, data: { durl: [{ url: 'https://upos-hz-mirrorakam.akamaized.net/video.mp4?token=ok' }] } }
  })
  assert.equal(resolved, 'https://upos-hz-mirrorakam.akamaized.net/video.mp4?token=ok')
  assert.equal(requests.length, 2)
  assert.match(requests[0], /bvid=BV1Ab411C7De/)
  assert.match(requests[1], /cid=987654321/)
  assert.match(requests[1], /platform=html5/)
})

test('stream resolution rejects an invalid API response or an insecure stream', async () => {
  assert.equal(
    await resolveCommunityVideoStreamUrl(validSource, async () => ({ code: 0, data: [] })),
    '',
  )
  let call = 0
  assert.equal(
    await resolveCommunityVideoStreamUrl(validSource, async () => {
      call += 1
      return call === 1
        ? { code: 0, data: [{ cid: 42 }] }
        : { code: 0, data: { durl: [{ url: 'https://evil.example/video.mp4' }] } }
    }),
    '',
  )
  call = 0
  assert.equal(
    await resolveCommunityVideoStreamUrl(validSource, async () => {
      call += 1
      return call === 1
        ? { code: 0, data: [{ cid: 42 }] }
        : { code: 0, data: { durl: [{ url: 'http://cdn.example/video.mp4' }] } }
    }),
    '',
  )
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
    true,
  )
  assert.equal(
    requiresCommunityVideoDesktopUserAgent(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148',
    ),
    true,
  )
  assert.equal(
    requiresCommunityVideoDesktopUserAgent(
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
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
  assert.deepEqual(capture.userAgentCalls[0], {
    userAgent: buildCommunityVideoDesktopUserAgent(capture.originalUserAgent),
    checkplus: false,
  })
  assert.deepEqual(capture.userAgentCalls[1], {
    userAgent: capture.originalUserAgent,
    checkplus: false,
  })
  assert.equal(capture.currentUserAgent, capture.originalUserAgent)
  assert.deepEqual(capture.styles.additionalHttpHeaders, {
    Referer: BILIBILI_REFERER,
    'User-Agent': buildCommunityVideoDesktopUserAgent(''),
  })
  assert.deepEqual(capture.overrideOptions, {
    effect: 'instant',
    mode: 'reject',
    match: BLOCK_UNTRUSTED_PLAYER_NAVIGATION,
    exclude: 'none',
  })
  assert.equal(capture.loadedUrl, buildCommunityVideoPlayerUrl(validSource))
  assert.deepEqual(capture.loadHeaders, {
    Referer: BILIBILI_REFERER,
    'User-Agent': buildCommunityVideoDesktopUserAgent(''),
  })
  assert.equal(
    capture.loadUserAgent,
    buildCommunityVideoDesktopUserAgent(capture.originalUserAgent),
  )
  assert.equal(capture.animation, 'pop-in')
})

test('resolved MP4 uses the native video control with headers instead of the web player', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const streamUrl = 'https://upos-hz-mirrorakam.akamaized.net/video.mp4?token=ok'
  assert.equal(
    openNativeCommunityVideo(runtime, validSource, '视频', undefined, 15000, streamUrl),
    true,
  )
  assert.equal(capture.videoStyles.src, streamUrl)
  assert.deepEqual(capture.videoStyles.header, {
    Referer: BILIBILI_REFERER,
    'User-Agent': buildCommunityVideoDesktopUserAgent(''),
  })
  assert.equal(capture.videoStyles.autoplay, true)
  assert.equal(capture.appendedCount, 1)
  assert.equal(capture.videoPlayCount, 1)
  assert.equal(capture.styles.titleNView.buttons[0].text, '1.0x')
  assert.equal(capture.loadedUrl, '')
  assert.deepEqual(capture.overrideOptions, {})
})

test('native playback exposes all supported speed choices and applies the selection', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const streamUrl = 'https://upos-hz-mirrorakam.akamaized.net/video.mp4?token=ok'
  assert.equal(
    openNativeCommunityVideo(runtime, validSource, '视频', undefined, 15000, streamUrl),
    true,
  )

  capture.styles.titleNView.buttons[0].onclick()
  assert.equal(capture.actionSheetStyles.title, '播放速度（当前 1.0x）')
  assert.equal(capture.actionSheetStyles.cancel, '取消')
  assert.deepEqual(
    capture.actionSheetStyles.buttons.map((button: { title: string }) => button.title),
    ['0.5x', '0.8x', '1.0x', '1.25x', '1.5x', '2x'],
  )
  assert.deepEqual(COMMUNITY_VIDEO_PLAYBACK_RATES, [0.5, 0.8, 1, 1.25, 1.5, 2])

  capture.actionSheetCallback?.({ index: 5 })
  assert.deepEqual(capture.videoPlaybackRates, [1.5])
  assert.equal(capture.titleButtonStyles.text, '1.5x')
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
  assert.equal(capture.currentUserAgent, capture.originalUserAgent)
})

test('native playback stops an endless player shell and reports a recoverable timeout', async () => {
  const { runtime, capture } = fakeNativeRuntime(false)
  const failures: CommunityVideoFailure[] = []
  openNativeCommunityVideo(runtime, validSource, '视频', failure => failures.push(failure), 5)
  await new Promise(resolve => setTimeout(resolve, 15))
  assert.equal(capture.closeAnimation, 'none')
  assert.equal(failures[0]?.code, 'player-load-failed')
  assert.equal(failures[0]?.message, '视频播放器加载超时')
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

test('a failed attempt to reshow an active player restores the old UA before reopening', () => {
  const { runtime, capture } = fakeNativeRuntime()
  const desktopUserAgent = buildCommunityVideoDesktopUserAgent(capture.originalUserAgent)
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  capture.throwOnShow = true
  assert.equal(openNativeCommunityVideo(runtime, validSource, '视频'), true)
  assert.deepEqual(capture.userAgentCalls.slice(-4), [
    { userAgent: desktopUserAgent, checkplus: false },
    { userAgent: capture.originalUserAgent, checkplus: false },
    { userAgent: desktopUserAgent, checkplus: false },
    { userAgent: capture.originalUserAgent, checkplus: false },
  ])
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
  assert.match(detailPage, /await openCommunityVideo\(value, t\('video'\)/)
  assert.match(detailPage, /v-for="c in comments"/)
  assert.match(detailPage, /v-model="commentText"/)
  assert.match(detailPage, /videoOpenExternalHint/)
  assert.match(detailPage, /if \(confirm\) openExternalLink/)
  assert.equal((locale.match(/videoOpenExternalHint:/g) || []).length, 2)
})

test('legacy internal market sources always display the current ZTW brand', () => {
  const indexPage = readFileSync(new URL('../src/pages/community/index.vue', import.meta.url), 'utf8')
  const detailPage = readFileSync(new URL('../src/pages/community/detail.vue', import.meta.url), 'utf8')
  const locale = readFileSync(new URL('../src/store/i18n.ts', import.meta.url), 'utf8')
  for (const page of [indexPage, detailPage]) {
    assert.match(page, /source_key === 'wod-market'/)
    assert.match(page, /return t\('ztwMarketName'\)/)
    assert.match(page, /localizeInternalBrandText\(content, (?:post|value)\.source_key\)/)
    assert.match(page, /localizeInternalBrandText\(topic, (?:post|value)\.source_key\)/)
    assert.doesNotMatch(page, /return 'WOD Market'/)
  }
  assert.match(locale, /ztwMarketName: 'ZTW 算力行情'/)
  assert.match(locale, /ztwMarketName: 'ZTW Compute Market'/)
})

test('the app manifest enables the native VideoPlayer module', () => {
  const manifest = JSON.parse(readFileSync(new URL('../src/manifest.json', import.meta.url), 'utf8'))
  assert.deepEqual(manifest['app-plus']?.modules?.VideoPlayer, {})
})
