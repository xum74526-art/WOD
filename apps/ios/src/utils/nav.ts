/**
 * 导航工具：防止 uni-app H5 下 @tap 事件多触发导致的重复跳转。
 * 双重防护：① 时间锁 800ms  ② URL 去重（目标=当前页则跳过）
 */

import { hasCurrentPrivacyConsent } from './privacy-consent'

let navLock = false
let lastUrl = ''

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

export function navigateTo(url: string) {
  if (navLock) return
  // 去重：如果目标 URL 跟上次跳转的一样，且在锁定期内，跳过
  if (url === lastUrl && navLock) return
  // 去重：如果目标页面已经是当前页面，跳过
  const currentPath = _getCurrentPath()
  const targetPath = url.split('?')[0].replace(/^\//, '')
  if (currentPath === targetPath) return

  navLock = true
  lastUrl = url
  uni.navigateTo({
    url,
    success: () => {
      setTimeout(() => { navLock = false }, 800)
    },
    fail: () => {
      navLock = false
    },
  })
}

export function navigateBack(delta = 1) {
  if (navLock) return
  navLock = true
  uni.navigateBack({
    delta,
    success: () => {
      setTimeout(() => { navLock = false }, 800)
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
