export interface CommunityVideoSource {
  content_type?: string | null
  origin?: string | null
  video_provider?: string | null
  video_id?: string | null
}

export type CommunityVideoFailureCode =
  | 'invalid-video-source'
  | 'player-open-failed'
  | 'player-load-failed'

export interface CommunityVideoFailure {
  code: CommunityVideoFailureCode
  message: string
  cause?: unknown
}

export type CommunityVideoFailureHandler = (failure: CommunityVideoFailure) => void

interface NativeCommunityVideoWebviewStyles {
  background: '#000000'
  cachemode: 'noCache'
  hardwareAccelerated: true
  backButtonAutoControl: 'close'
  popGesture: 'close'
  disablePlus: true
  plusrequire: 'none'
  'uni-app': 'none'
  additionalHttpHeaders: Record<string, string>
  titleNView: {
    autoBackButton: true
    backgroundColor: '#FFFFFF'
    titleColor: '#0F3440'
    titleText: string
  }
}

interface NativeCommunityVideoWebview {
  overrideUrlLoading(
    options: {
      effect: 'instant'
      mode: 'reject'
      match: string
      exclude: 'none'
    },
    callback: (event: unknown) => void,
  ): void
  addEventListener(event: 'error' | 'close', callback: (event: unknown) => void): void
  loadURL(url: string, additionalHttpHeaders?: Record<string, string>): void
  show(animation?: string): void
  close(animation?: string): void
}

export interface NativeCommunityVideoRuntime {
  navigator?: {
    getUserAgent(): string
    setUserAgent(userAgent: string, checkplus?: boolean): void
  }
  webview: {
    create(
      url: string,
      id: string,
      styles: NativeCommunityVideoWebviewStyles,
    ): NativeCommunityVideoWebview
  }
}

export const BILIBILI_PLAYER_ORIGIN = 'https://player.bilibili.com'
export const BILIBILI_REFERER = 'https://www.bilibili.com/'
export const BLOCK_UNTRUSTED_PLAYER_NAVIGATION =
  '^(?!(?:https://player\\.bilibili\\.com/player\\.html|https://www\\.bilibili\\.com/blackboard/webplayer/mbplayer\\.html)(?:[?#]|$)).*'

const BILIBILI_VIDEO_ID = /^BV[0-9A-Za-z]{10}$/
let playerSequence = 0

interface ActiveCommunityVideoPlayer {
  runtime: NativeCommunityVideoRuntime
  target: string
  webview: NativeCommunityVideoWebview
}

let activePlayer: ActiveCommunityVideoPlayer | null = null

export function buildCommunityVideoDesktopUserAgent(currentUserAgent: string): string {
  const chromeVersion = String(currentUserAgent || '').match(/Chrome\/[0-9.]+/)?.[0]
    || 'Chrome/120.0.0.0'
  return `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ${chromeVersion} Safari/537.36`
}

export function requiresCommunityVideoDesktopUserAgent(currentUserAgent: string): boolean {
  const userAgent = String(currentUserAgent || '')
  return /\bAndroid\b/i.test(userAgent) && (/\bwv\b/i.test(userAgent) || /Html5Plus/i.test(userAgent))
}

function useDesktopPlayerUserAgent(runtime: NativeCommunityVideoRuntime): () => void {
  const nativeNavigator = runtime.navigator
  if (!nativeNavigator) return () => {}

  try {
    const originalUserAgent = nativeNavigator.getUserAgent()
    if (!requiresCommunityVideoDesktopUserAgent(originalUserAgent)) return () => {}
    const desktopUserAgent = buildCommunityVideoDesktopUserAgent(originalUserAgent)
    if (!originalUserAgent || originalUserAgent === desktopUserAgent) return () => {}

    nativeNavigator.setUserAgent(desktopUserAgent, false)
    let restored = false
    return () => {
      if (restored) return
      try {
        nativeNavigator.setUserAgent(originalUserAgent, false)
        restored = true
      } catch {}
    }
  } catch {
    return () => {}
  }
}

function trustedBilibiliVideoId(source: CommunityVideoSource): string {
  if (
    source.content_type !== 'video'
    || source.origin !== 'aggregated'
    || source.video_provider !== 'bilibili'
  ) return ''

  const videoId = String(source.video_id || '').trim()
  return BILIBILI_VIDEO_ID.test(videoId) ? videoId : ''
}

function nextPlayerWebviewId(): string {
  playerSequence += 1
  return `wod-community-video-${Date.now()}-${playerSequence}`
}

function failureMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') return fallback
  const message = (error as { message?: unknown }).message
  return typeof message === 'string' && message.trim() ? message.trim() : fallback
}

function reportFailure(
  onError: CommunityVideoFailureHandler | undefined,
  code: CommunityVideoFailureCode,
  message: string,
  cause?: unknown,
): void {
  onError?.({ code, message, cause })
}

/**
 * Build the player URL from trusted structured fields instead of accepting an
 * arbitrary URL from the API or route query.
 */
export function buildCommunityVideoPlayerUrl(source: CommunityVideoSource): string {
  const videoId = trustedBilibiliVideoId(source)
  if (!videoId) return ''

  return `${BILIBILI_PLAYER_ORIGIN}/player.html?bvid=${videoId}&p=1&autoplay=false&poster=true&danmaku=false`
}

export function buildCommunityVideoSourceUrl(source: CommunityVideoSource): string {
  const videoId = trustedBilibiliVideoId(source)
  return videoId ? `https://www.bilibili.com/video/${videoId}/` : ''
}

export function openNativeCommunityVideo(
  runtime: NativeCommunityVideoRuntime,
  source: CommunityVideoSource,
  title: string,
  onError?: CommunityVideoFailureHandler,
): boolean {
  const target = buildCommunityVideoPlayerUrl(source)
  if (!target) {
    reportFailure(onError, 'invalid-video-source', '视频来源无效')
    return false
  }

  const headers = { Referer: BILIBILI_REFERER }
  if (activePlayer?.runtime === runtime && activePlayer.target === target) {
    const stalePlayer = activePlayer
    try {
      stalePlayer.webview.show('pop-in')
      return true
    } catch {
      activePlayer = null
      try { stalePlayer.webview.close('none') } catch {}
    }
  } else if (activePlayer) {
    const stalePlayer = activePlayer
    activePlayer = null
    try { stalePlayer.webview.close('none') } catch {}
  }

  const restoreUserAgent = useDesktopPlayerUserAgent(runtime)
  let player: NativeCommunityVideoWebview | null = null
  try {
    try {
      player = runtime.webview.create('', nextPlayerWebviewId(), {
        background: '#000000',
        cachemode: 'noCache',
        hardwareAccelerated: true,
        backButtonAutoControl: 'close',
        popGesture: 'close',
        disablePlus: true,
        plusrequire: 'none',
        'uni-app': 'none',
        additionalHttpHeaders: headers,
        titleNView: {
          autoBackButton: true,
          backgroundColor: '#FFFFFF',
          titleColor: '#0F3440',
          titleText: title || '视频播放',
        },
      })
    } finally {
      // A created WebView keeps its creation-time UA; immediately restore the
      // application UA so normal API requests are never sent as desktop Chrome.
      restoreUserAgent()
    }
    const createdPlayer = player

    let terminal = false
    const finish = (
      shouldClose: boolean,
      code?: CommunityVideoFailureCode,
      message?: string,
      cause?: unknown,
    ) => {
      if (terminal) return
      terminal = true
      if (activePlayer?.webview === createdPlayer) activePlayer = null
      if (shouldClose) {
        try { createdPlayer.close('none') } catch {}
      }
      if (code && message) reportFailure(onError, code, message, cause)
    }

    createdPlayer.overrideUrlLoading({
      effect: 'instant',
      mode: 'reject',
      match: BLOCK_UNTRUSTED_PLAYER_NAVIGATION,
      exclude: 'none',
    }, (event) => {
      finish(true, 'player-load-failed', '播放器拒绝了不受信任的跳转', event)
    })

    createdPlayer.addEventListener('error', (error) => {
      finish(
        true,
        'player-load-failed',
        failureMessage(error, '视频加载失败'),
        error,
      )
    })
    createdPlayer.addEventListener('close', () => finish(false))
    activePlayer = { runtime, target, webview: createdPlayer }
    try {
      createdPlayer.loadURL(target, headers)
      createdPlayer.show('pop-in')
    } catch (error) {
      finish(
        true,
        'player-open-failed',
        failureMessage(error, '无法打开视频播放器'),
        error,
      )
      return false
    }
    return true
  } catch (error) {
    restoreUserAgent()
    if (player) {
      try { player.close('none') } catch {}
    }
    reportFailure(
      onError,
      'player-open-failed',
      failureMessage(error, '无法打开视频播放器'),
      error,
    )
    return false
  }
}

export function openCommunityVideo(
  source: CommunityVideoSource,
  title: string,
  onError?: CommunityVideoFailureHandler,
): boolean {
  // #ifdef APP-PLUS
  return openNativeCommunityVideo(plus as unknown as NativeCommunityVideoRuntime, source, title, onError)
  // #endif

  return false
}
