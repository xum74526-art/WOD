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
    buttons?: Array<{
      text: string
      width: string
      float: 'right'
      color: string
      fontSize: string
      fontWeight: 'bold'
      onclick: () => void
    }>
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
  addEventListener(event: 'loaded' | 'error' | 'close', callback: (event: unknown) => void): void
  loadURL(url: string, additionalHttpHeaders?: Record<string, string>): void
  show(animation?: string): void
  close(animation?: string): void
  append?(child: NativeCommunityVideoPlayer): void
  setTitleNViewButtonStyle?(
    index: number,
    styles: { text: string },
  ): void
}

interface NativeCommunityVideoPlayer {
  addEventListener(
    event: 'play' | 'pause' | 'ended' | 'timeupdate' | 'waiting' | 'error',
    callback: (event: unknown) => void,
  ): void
  play(): void
  playbackRate(rate: number): void
  close(): void
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
  video?: {
    createVideoPlayer(
      id: string,
      styles: {
        src: string
        header: Record<string, string>
        top: string
        left: string
        width: string
        height: string
        controls: true
        autoplay: true
        direction: number
        objectFit: 'contain'
        'show-center-play-btn': true
        'show-fullscreen-btn': true
        'show-loading': true
      },
    ): NativeCommunityVideoPlayer
  }
  nativeUI?: {
    actionSheet(
      styles: {
        title: string
        cancel: string
        buttons: Array<{ title: string }>
      },
      callback: (result: { index?: number }) => void,
    ): unknown
  }
}

export const BILIBILI_PLAYER_ORIGIN = 'https://player.bilibili.com'
export const BILIBILI_REFERER = 'https://www.bilibili.com/'
export const BILIBILI_API_ORIGIN = 'https://api.bilibili.com'
export const NATIVE_VIDEO_LOAD_TIMEOUT_MS = 15000
export const COMMUNITY_VIDEO_PLAYBACK_RATES = [0.5, 0.8, 1, 1.25, 1.5, 2] as const
export const BLOCK_UNTRUSTED_PLAYER_NAVIGATION =
  '^(?!(?:https://player\\.bilibili\\.com/player\\.html|https://www\\.bilibili\\.com/blackboard/webplayer/mbplayer\\.html)(?:[?#]|$)).*'

const BILIBILI_VIDEO_ID = /^BV[0-9A-Za-z]{10}$/
let playerSequence = 0

function playbackRateLabel(rate: number): string {
  return rate === 1 ? '1.0x' : `${rate}x`
}

interface ActiveCommunityVideoPlayer {
  runtime: NativeCommunityVideoRuntime
  target: string
  webview: NativeCommunityVideoWebview
  dispose?: () => void
}

let activePlayer: ActiveCommunityVideoPlayer | null = null

export function buildCommunityVideoDesktopUserAgent(currentUserAgent: string): string {
  const chromeVersion = String(currentUserAgent || '').match(/Chrome\/[0-9.]+/)?.[0]
    || 'Chrome/120.0.0.0'
  return `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ${chromeVersion} Safari/537.36`
}

export function requiresCommunityVideoDesktopUserAgent(currentUserAgent: string): boolean {
  const userAgent = String(currentUserAgent || '')
  return /Html5Plus/i.test(userAgent)
    || /\b(?:iPhone|iPad|iPod)\b/i.test(userAgent)
    || (/\bAndroid\b/i.test(userAgent) && /\bwv\b/i.test(userAgent))
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

type CommunityVideoJsonRequest = (
  url: string,
  headers: Record<string, string>,
) => Promise<unknown>

function responseRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

function trustedStreamUrl(source: CommunityVideoSource, value: unknown): string {
  if (!trustedBilibiliVideoId(source)) return ''
  const candidate = typeof value === 'string' ? value.trim() : ''
  if (!candidate || /[\u0000-\u0020\u007f]/.test(candidate)) return ''
  const authority = /^https:\/\/([^/?#]+)(?:[/?#]|$)/i.exec(candidate)?.[1]?.toLowerCase() || ''
  if (!authority || authority.includes('@') || authority.includes(':')) return ''
  const trustedSuffixes = [
    '.akamaized.net',
    '.bilivideo.com',
    '.bilivideo.cn',
    '.bilibili.com',
    '.biliapi.net',
    '.szbdyd.com',
  ]
  return trustedSuffixes.some(suffix => authority.endsWith(suffix)) ? candidate : ''
}

function requestCommunityVideoJson(url: string, headers: Record<string, string>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method: 'GET',
      timeout: NATIVE_VIDEO_LOAD_TIMEOUT_MS,
      header: headers,
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) resolve(response.data)
        else reject(new Error(`Bilibili HTTP ${response.statusCode}`))
      },
      fail: reject,
    })
  })
}

/** Resolve a progressive MP4 so iOS can use its native media player. */
export async function resolveCommunityVideoStreamUrl(
  source: CommunityVideoSource,
  requestJson: CommunityVideoJsonRequest = requestCommunityVideoJson,
): Promise<string> {
  const videoId = trustedBilibiliVideoId(source)
  if (!videoId) return ''

  const headers = {
    Referer: BILIBILI_REFERER,
    'User-Agent': buildCommunityVideoDesktopUserAgent(''),
  }
  const pages = responseRecord(await requestJson(
    `${BILIBILI_API_ORIGIN}/x/player/pagelist?bvid=${encodeURIComponent(videoId)}`,
    headers,
  ))
  const firstPage = Array.isArray(pages.data) ? responseRecord(pages.data[0]) : {}
  const cid = Number(firstPage.cid)
  if (pages.code !== 0 || !Number.isSafeInteger(cid) || cid <= 0) return ''

  const playback = responseRecord(await requestJson(
    `${BILIBILI_API_ORIGIN}/x/player/playurl?bvid=${encodeURIComponent(videoId)}&cid=${cid}&qn=64&fnval=0&fnver=0&fourk=0&platform=html5`,
    headers,
  ))
  const playbackData = responseRecord(playback.data)
  const firstStream = Array.isArray(playbackData.durl) ? responseRecord(playbackData.durl[0]) : {}
  return playback.code === 0 ? trustedStreamUrl(source, firstStream.url) : ''
}

function nextPlayerWebviewId(): string {
  playerSequence += 1
  return `wod-community-video-${Date.now()}-${playerSequence}`
}

function closeActivePlayer(player: ActiveCommunityVideoPlayer): void {
  try { player.dispose?.() } catch {}
  try { player.webview.close('none') } catch {}
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

function openNativeCommunityVideoStream(
  runtime: NativeCommunityVideoRuntime,
  target: string,
  title: string,
  headers: Record<string, string>,
  onError?: CommunityVideoFailureHandler,
  loadTimeoutMs: number = NATIVE_VIDEO_LOAD_TIMEOUT_MS,
): boolean {
  if (!runtime.video?.createVideoPlayer) return false

  if (activePlayer?.runtime === runtime && activePlayer.target === target) {
    try {
      activePlayer.webview.show('pop-in')
      return true
    } catch {
      const stalePlayer = activePlayer
      activePlayer = null
      closeActivePlayer(stalePlayer)
    }
  } else if (activePlayer) {
    const stalePlayer = activePlayer
    activePlayer = null
    closeActivePlayer(stalePlayer)
  }

  let shell: NativeCommunityVideoWebview | null = null
  let video: NativeCommunityVideoPlayer | null = null
  let selectedRate = 1
  const choosePlaybackRate = () => {
    if (!video || !runtime.nativeUI?.actionSheet) return
    runtime.nativeUI.actionSheet({
      title: `播放速度（当前 ${playbackRateLabel(selectedRate)}）`,
      cancel: '取消',
      buttons: COMMUNITY_VIDEO_PLAYBACK_RATES.map(rate => ({ title: playbackRateLabel(rate) })),
    }, result => {
      const index = Number(result?.index)
      if (!Number.isInteger(index) || index < 1 || index > COMMUNITY_VIDEO_PLAYBACK_RATES.length) return
      const rate = COMMUNITY_VIDEO_PLAYBACK_RATES[index - 1]
      try {
        video?.playbackRate(rate)
        selectedRate = rate
        shell?.setTitleNViewButtonStyle?.(0, { text: playbackRateLabel(rate) })
      } catch {}
    })
  }
  try {
    const webviewId = nextPlayerWebviewId()
    shell = runtime.webview.create('about:blank', webviewId, {
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
        buttons: runtime.nativeUI?.actionSheet
          ? [{
              text: playbackRateLabel(selectedRate),
              width: '62px',
              float: 'right',
              color: '#0F3440',
              fontSize: '15px',
              fontWeight: 'bold',
              onclick: choosePlaybackRate,
            }]
          : undefined,
      },
    })
    const appendVideo = shell.append
    if (!appendVideo) throw new Error('当前运行环境不支持原生视频控件')

    video = runtime.video.createVideoPlayer(`${webviewId}-player`, {
      src: target,
      header: headers,
      top: '0px',
      left: '0px',
      width: '100%',
      height: '100%',
      controls: true,
      autoplay: true,
      direction: -90,
      objectFit: 'contain',
      'show-center-play-btn': true,
      'show-fullscreen-btn': true,
      'show-loading': true,
    })
    const createdShell = shell
    const createdVideo = video
    let terminal = false
    let loadTimer: ReturnType<typeof setTimeout> | null = null
    const clearLoadTimer = () => {
      if (!loadTimer) return
      clearTimeout(loadTimer)
      loadTimer = null
    }
    const dispose = () => {
      clearLoadTimer()
      try { createdVideo.close() } catch {}
    }
    const fail = (event: unknown) => {
      if (terminal) return
      terminal = true
      if (activePlayer?.webview === createdShell) activePlayer = null
      dispose()
      try { createdShell.close('none') } catch {}
      reportFailure(
        onError,
        'player-load-failed',
        failureMessage(event, '视频加载失败'),
        event,
      )
    }

    createdVideo.addEventListener('play', clearLoadTimer)
    createdVideo.addEventListener('error', fail)
    createdShell.addEventListener('close', () => {
      if (activePlayer?.webview === createdShell) activePlayer = null
      terminal = true
      dispose()
    })
    appendVideo.call(createdShell, createdVideo)
    activePlayer = { runtime, target, webview: createdShell, dispose }
    loadTimer = setTimeout(() => fail(new Error('视频播放器加载超时')), Math.max(1, loadTimeoutMs))
    ;(loadTimer as unknown as { unref?: () => void }).unref?.()
    createdShell.show('pop-in')
    createdVideo.play()
    return true
  } catch (error) {
    try { video?.close() } catch {}
    try { shell?.close('none') } catch {}
    reportFailure(
      onError,
      'player-open-failed',
      failureMessage(error, '无法打开视频播放器'),
      error,
    )
    return false
  }
}

export function openNativeCommunityVideo(
  runtime: NativeCommunityVideoRuntime,
  source: CommunityVideoSource,
  title: string,
  onError?: CommunityVideoFailureHandler,
  loadTimeoutMs: number = NATIVE_VIDEO_LOAD_TIMEOUT_MS,
  streamUrl: string = '',
): boolean {
  const embeddedTarget = buildCommunityVideoPlayerUrl(source)
  const directTarget = trustedStreamUrl(source, streamUrl)
  const target = streamUrl ? directTarget : embeddedTarget
  if (!target) {
    reportFailure(onError, 'invalid-video-source', '视频来源无效')
    return false
  }

  const headers = {
    Referer: BILIBILI_REFERER,
    'User-Agent': buildCommunityVideoDesktopUserAgent(''),
  }
  if (directTarget && runtime.video?.createVideoPlayer) {
    return openNativeCommunityVideoStream(
      runtime,
      directTarget,
      title,
      headers,
      onError,
      loadTimeoutMs,
    )
  }
  if (activePlayer?.runtime === runtime && activePlayer.target === target) {
    const stalePlayer = activePlayer
    try {
      stalePlayer.webview.show('pop-in')
      return true
    } catch {
      activePlayer = null
      closeActivePlayer(stalePlayer)
    }
  } else if (activePlayer) {
    const stalePlayer = activePlayer
    activePlayer = null
    closeActivePlayer(stalePlayer)
  }

  const restoreUserAgent = useDesktopPlayerUserAgent(runtime)
  let player: NativeCommunityVideoWebview | null = null
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
    const createdPlayer = player

    let terminal = false
    let loadTimer: ReturnType<typeof setTimeout> | null = null
    const clearLoadTimer = () => {
      if (!loadTimer) return
      clearTimeout(loadTimer)
      loadTimer = null
    }
    const finish = (
      shouldClose: boolean,
      code?: CommunityVideoFailureCode,
      message?: string,
      cause?: unknown,
    ) => {
      if (terminal) return
      terminal = true
      clearLoadTimer()
      if (activePlayer?.webview === createdPlayer) activePlayer = null
      if (shouldClose) {
        try { createdPlayer.close('none') } catch {}
      }
      if (code && message) reportFailure(onError, code, message, cause)
    }

    if (!directTarget) {
      createdPlayer.overrideUrlLoading({
        effect: 'instant',
        mode: 'reject',
        match: BLOCK_UNTRUSTED_PLAYER_NAVIGATION,
        exclude: 'none',
      }, (event) => {
        finish(true, 'player-load-failed', '播放器拒绝了不受信任的跳转', event)
      })
    }

    createdPlayer.addEventListener('error', (error) => {
      finish(
        true,
        'player-load-failed',
        failureMessage(error, '视频加载失败'),
        error,
      )
    })
    createdPlayer.addEventListener('loaded', clearLoadTimer)
    createdPlayer.addEventListener('close', () => finish(false))
    activePlayer = { runtime, target, webview: createdPlayer }
    try {
      loadTimer = setTimeout(() => {
        finish(true, 'player-load-failed', '视频播放器加载超时')
      }, Math.max(1, loadTimeoutMs))
      ;(loadTimer as unknown as { unref?: () => void }).unref?.()
      createdPlayer.loadURL(target, headers)
      // iOS resolves the request User-Agent when loadURL runs, so keep the
      // temporary desktop identity through this call and restore it at once.
      restoreUserAgent()
      createdPlayer.show('pop-in')
    } catch (error) {
      restoreUserAgent()
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

export async function openCommunityVideo(
  source: CommunityVideoSource,
  title: string,
  onError?: CommunityVideoFailureHandler,
): Promise<boolean> {
  // #ifdef APP-PLUS
  try {
    const streamUrl = await resolveCommunityVideoStreamUrl(source)
    if (!streamUrl) {
      reportFailure(onError, 'player-load-failed', '无法取得视频播放地址')
      return false
    }
    return openNativeCommunityVideo(
      plus as unknown as NativeCommunityVideoRuntime,
      source,
      title,
      onError,
      NATIVE_VIDEO_LOAD_TIMEOUT_MS,
      streamUrl,
    )
  } catch (error) {
    reportFailure(
      onError,
      'player-load-failed',
      failureMessage(error, '无法取得视频播放地址'),
      error,
    )
    return false
  }
  // #endif

  return false
}
