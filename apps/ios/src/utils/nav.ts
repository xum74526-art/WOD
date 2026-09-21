/**
 * 导航工具：防止 uni-app H5 下 @tap 事件多触发导致的重复跳转。
 * 双重防护：① 时间锁 800ms  ② URL 去重（目标=当前页则跳过）
 */

import { hasCurrentPrivacyConsent } from './privacy-consent'
import { APP_MOTION, backAnimation, navigateAnimation, type RouteMotion } from './motion'

let navLock = false
let lastUrl = ''

export interface NavigationOptions {
  motion?: RouteMotion
}

export interface SwitchTabOptions {
  fallbackToReLaunch?: boolean
}

function _getCurrentPath(): string {
  try {
    const pages = getCurrentPages()
    if (pages.length === 0) return ''
    const route = pages[pages.length - 1].route
    return route || ''
  } catch {
    return ''
  }
}

function releaseLock(delay: number = APP_MOTION.lock) {
  setTimeout(() => { navLock = false }, delay)
}

export function navigateTo(url: string, options: NavigationOptions = {}) {
  if (navLock) return
  // 去重：如果目标 URL 跟上次跳转的一样，且在锁定期内，跳过
  if (url === lastUrl && navLock) return
  // 去重：如果目标页面已经是当前页面，跳过
  const currentPath = _getCurrentPath()
  const targetPath = url.split('?')[0].replace(/^\//, '')
  if (currentPath === targetPath) return

  navLock = true
  lastUrl = url
  const animation = navigateAnimation(options.motion)
  uni.navigateTo({
    url,
    ...animation,
    success: () => {
      releaseLock(Math.max(APP_MOTION.lock, animation.animationDuration + 120))
    },
    fail: () => {
      navLock = false
    },
  })
}

/** Switch between root tab pages with the same duplicate-tap protection. */
export function switchTab(url: string, options: SwitchTabOptions = {}) {
  if (navLock) return
  const currentPath = _getCurrentPath()
  const targetPath = url.split('?')[0].replace(/^\//, '')
  if (currentPath === targetPath) return

  navLock = true
  uni.switchTab({
    url,
    success: () => releaseLock(APP_MOTION.lock),
    fail: () => {
      navLock = false
      if (options.fallbackToReLaunch) uni.reLaunch({ url })
    },
  })
}

export function navigateBack(delta = 1, options: NavigationOptions = {}) {
  if (navLock) return
  navLock = true
  const animation = backAnimation(options.motion)
  uni.navigateBack({
    delta,
    ...animation,
    success: () => {
      releaseLock(Math.max(APP_MOTION.lock, animation.animationDuration + 120))
    },
    fail: () => {
      navLock = false
      try {
        if (!hasCurrentPrivacyConsent()) {
          uni.reLaunch({ url: '/pages/privacy-consent/index' })
          return
        }
        uni.switchTab({ url: '/pages/index/index' })
      } catch {}
    },
  })
}
