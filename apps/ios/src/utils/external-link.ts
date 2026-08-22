export function openExternalLink(url: string, onFallback?: () => void) {
  if (!url || !/^https:\/\//i.test(url)) return

  // #ifdef H5
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) return
  // #endif

  // #ifdef APP-PLUS
  const runtime = (globalThis as any).plus?.runtime
  if (runtime?.openURL) {
    runtime.openURL(url)
    return
  }
  // #endif

  uni.setClipboardData({
    data: url,
    success: () => onFallback?.(),
  })
}
