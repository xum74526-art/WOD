// Keep the native cover until the destination page is rendered. The first
// local page may only be deciding between consent, login, and a restored session.
let launchClosed = false
let launchFallback: ReturnType<typeof setTimeout> | null = null

export function finishAppLaunch() {
  if (launchFallback) clearTimeout(launchFallback)
  launchFallback = null
  if (launchClosed) return
  launchClosed = true
  // #ifdef APP-PLUS
  if (typeof plus !== 'undefined') plus.navigator.closeSplashscreen()
  // #endif
}

export function beginAppLaunch() {
  // A navigation/network failure must never leave a permanent native cover.
  // The local startup surface remains visible if restoring a session is slow.
  // #ifdef APP-PLUS
  if (typeof plus !== 'undefined' && !launchClosed && !launchFallback) {
    launchFallback = setTimeout(finishAppLaunch, 8000)
  }
  // #endif
}
