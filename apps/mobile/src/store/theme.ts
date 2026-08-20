import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'wod-theme'
const VALID_MODES: ThemeMode[] = ['light', 'dark', 'system']

const PALETTE = {
  light: {
    background: '#FFFFFF',
    text: '#111111',
    muted: '#A1ADB2',
    primary: '#18AFC4',
    border: '#F0F1F2',
  },
  dark: {
    background: '#0A0E14',
    text: '#E8EDF2',
    muted: '#6B7785',
    primary: '#00D4FF',
    border: '#1A212B',
  },
} as const

function normalizeTheme(value: unknown): ResolvedTheme | null {
  return value === 'dark' || value === 'light' ? value : null
}

function detectSystemTheme(): ResolvedTheme {
  try {
    const info = uni.getSystemInfoSync() as UniNamespace.GetSystemInfoResult & {
      osTheme?: string
      theme?: string
    }
    const detected = normalizeTheme(info.osTheme) || normalizeTheme(info.theme)
    if (detected) return detected
  } catch {}

  try {
    const detected = normalizeTheme(uni.getAppBaseInfo().hostTheme)
    if (detected) return detected
  } catch {}

  // #ifdef H5
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  // #endif

  return 'light'
}

function updateDocumentTheme(theme: ResolvedTheme) {
  if (typeof document === 'undefined') return
  const isDark = theme === 'dark'
  const nodes: Array<Element | null> = [
    document.documentElement,
    document.body,
    document.querySelector('uni-app'),
    document.querySelector('uni-page-body'),
  ]
  document.querySelectorAll('page, .page').forEach((node) => nodes.push(node))
  nodes.forEach((node) => {
    if (!node) return
    node.classList.toggle('dark', isDark)
    node.setAttribute('data-wod-theme', theme)
  })
  document.documentElement.style.colorScheme = theme
}

function updateNativeChrome(theme: ResolvedTheme) {
  const colors = PALETTE[theme]
  try {
    uni.setTabBarStyle({
      color: colors.muted,
      selectedColor: colors.primary,
      backgroundColor: colors.background,
      borderStyle: theme === 'dark' ? 'black' : 'white',
      fail: () => {},
    })
  } catch {}
  try {
    uni.setNavigationBarColor({
      frontColor: theme === 'dark' ? '#ffffff' : '#000000',
      backgroundColor: colors.background,
      fail: () => {},
    })
  } catch {}
  try {
    uni.setBackgroundColor({
      backgroundColor: colors.background,
      backgroundColorTop: colors.background,
      backgroundColorBottom: colors.background,
      fail: () => {},
    })
    uni.setBackgroundTextStyle({ textStyle: theme === 'dark' ? 'light' : 'dark', fail: () => {} })
  } catch {}

  // #ifdef APP-PLUS
  try {
    plus.navigator.setStatusBarBackground(colors.background)
    plus.navigator.setStatusBarStyle(theme === 'dark' ? 'light' : 'dark')
  } catch {}
  // #endif
}

// App-plus renders pages in separate WebViews. Updating only the logic-layer
// document (or only the current page) leaves tab pages and newly opened pages
// in the old theme, so broadcast the class to every live WebView.
function updateAppPlusWebviews(theme: ResolvedTheme) {
  // #ifdef APP-PLUS
  const isDark = theme === 'dark'
  const colors = PALETTE[theme]
  const script = `;(function(){try{var d=${isDark ? 'true' : 'false'};var t=${JSON.stringify(theme)};var n=[document.documentElement,document.body,document.querySelector('uni-app'),document.querySelector('uni-page-body')];var q=document.querySelectorAll('page,.page');for(var i=0;i<q.length;i++)n.push(q[i]);for(var j=0;j<n.length;j++){var e=n[j];if(!e)continue;if(d)e.classList.add('dark');else e.classList.remove('dark');e.setAttribute('data-wod-theme',t)}document.documentElement.style.colorScheme=t}catch(e){}})();`
  try {
    plus.webview.all().forEach((webview) => {
      try {
        webview.setStyle({
          background: colors.background,
          backgroundColorTop: colors.background,
          backgroundColorBottom: colors.background,
          backgroundTextStyle: theme === 'dark' ? 'light' : 'dark',
          bounceBackground: colors.background,
        })
        webview.evalJS(script)
      } catch {}
    })
  } catch {}
  // #endif
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('light')
  const systemTheme = ref<ResolvedTheme>(detectSystemTheme())
  const resolvedMode = computed<ResolvedTheme>(() => mode.value === 'system' ? systemTheme.value : mode.value)
  const isDark = computed(() => resolvedMode.value === 'dark')
  const themeClass = computed(() => isDark.value ? 'dark' : 'light')
  let initialized = false
  let systemListenerRegistered = false
  let routeInterceptorsRegistered = false
  let appPlusTimers: Array<ReturnType<typeof setTimeout>> = []

  function clearScheduledUpdates() {
    appPlusTimers.forEach((timer) => clearTimeout(timer))
    appPlusTimers = []
  }

  function applyTheme() {
    const activeTheme = resolvedMode.value
    updateDocumentTheme(activeTheme)
    updateNativeChrome(activeTheme)
    updateAppPlusWebviews(activeTheme)

    // A new App WebView may not have finished creating when the navigation
    // callback fires. Re-apply briefly after render so it never flashes back
    // to the default light variables.
    clearScheduledUpdates()
    ;[0, 80, 240].forEach((delay) => {
      appPlusTimers.push(setTimeout(() => {
        updateDocumentTheme(resolvedMode.value)
        updateAppPlusWebviews(resolvedMode.value)
      }, delay))
    })
  }

  function refreshSystemTheme() {
    const next = detectSystemTheme()
    if (systemTheme.value === next) {
      if (mode.value === 'system') applyTheme()
      return
    }
    systemTheme.value = next
  }

  function registerSystemThemeListener() {
    if (systemListenerRegistered) return
    systemListenerRegistered = true
    try {
      uni.onThemeChange(({ theme }) => {
        const next = normalizeTheme(theme)
        if (next) systemTheme.value = next
      })
    } catch {}

    // #ifdef H5
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      const media = window.matchMedia('(prefers-color-scheme: dark)')
      const onChange = (event: MediaQueryListEvent) => {
        systemTheme.value = event.matches ? 'dark' : 'light'
      }
      if (typeof media.addEventListener === 'function') media.addEventListener('change', onChange)
      else media.addListener(onChange)
    }
    // #endif
  }

  function registerRouteInterceptors() {
    if (routeInterceptorsRegistered) return
    routeInterceptorsRegistered = true
    const refresh = () => applyTheme()
    ;['navigateTo', 'redirectTo', 'reLaunch', 'switchTab', 'navigateBack'].forEach((name) => {
      try {
        uni.addInterceptor(name, { success: refresh })
      } catch {}
    })
  }

  function init() {
    const saved = uni.getStorageSync(STORAGE_KEY) as ThemeMode
    if (VALID_MODES.includes(saved)) mode.value = saved
    systemTheme.value = detectSystemTheme()
    registerSystemThemeListener()
    registerRouteInterceptors()
    initialized = true
    applyTheme()
  }

  function setMode(next: ThemeMode) {
    if (!VALID_MODES.includes(next)) return
    if (mode.value === next) {
      applyTheme()
      return
    }
    mode.value = next
  }

  // The compact home-page button remains a predictable light/dark toggle.
  // "Follow system" is an explicit choice in Settings.
  function toggle() {
    setMode(resolvedMode.value === 'dark' ? 'light' : 'dark')
  }

  watch(mode, (next) => {
    if (initialized) uni.setStorageSync(STORAGE_KEY, next)
    applyTheme()
  }, { flush: 'sync' })

  watch(systemTheme, () => {
    if (mode.value === 'system') applyTheme()
  }, { flush: 'sync' })

  return {
    mode,
    systemTheme,
    resolvedMode,
    isDark,
    themeClass,
    init,
    setMode,
    toggle,
    applyTheme,
    refreshSystemTheme,
  }
})
