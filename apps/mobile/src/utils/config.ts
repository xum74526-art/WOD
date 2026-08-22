// H5 开发环境走 Vite 的 /api 代理；原生 App 使用构建时配置的 HTTPS API。
// 复制 .env.example 为 .env.local 后设置 VITE_KAI_APP_API_BASE。
// 旧名 VITE_WOD_APP_API_BASE 仅用于平滑迁移已有构建环境。
const APP_API_BASE = String(
  import.meta.env.VITE_KAI_APP_API_BASE
  || import.meta.env.VITE_WOD_APP_API_BASE
  || 'https://wod.kai.com/api',
).replace(/\/$/, '')
let API_BASE = '/api'
// #ifndef H5
API_BASE = APP_API_BASE
// #endif

/** Resolve an API-relative persisted media URL on both H5 and native App. */
export function resolveApiMediaUrl(value?: string | null): string {
  const source = String(value || '').trim()
  if (!source) return ''
  if (/^https:\/\//i.test(source)) return source
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(source)) return source

  const base = API_BASE.replace(/\/$/, '')
  if (source.startsWith('/api/')) {
    const apiRoot = base.endsWith('/api') ? base.slice(0, -4) : base
    return `${apiRoot}${source}`
  }
  // Community media is intentionally exposed by a narrow API route. The
  // persisted value stays deployment-independent while H5 and App resolve it
  // below their own API base (/api/uploads/... or /wod-api/api/uploads/...).
  if (source.startsWith('/uploads/community/')) {
    return `${base}${source}`
  }
  if (source.startsWith('/user/') || source.startsWith('user/')) {
    return `${base}/${source.replace(/^\//, '')}`
  }
  // Legacy temp-file paths are device/session scoped and must not be rendered
  // after a restart. Falling back to initials is safer than a broken image.
  return ''
}

/** Resolve a backend route returned by the API for H5 and native App. */
export function resolveBackendUrl(value?: string | null): string {
  const source = String(value || '').trim()
  if (!source) return ''
  if (/^https:\/\//i.test(source)) return source
  if (!source.startsWith('/api/')) return ''
  if (/^https:\/\//i.test(API_BASE)) {
    const apiRoot = API_BASE.endsWith('/api') ? API_BASE.slice(0, -4) : API_BASE
    return `${apiRoot}${source}`
  }
  // #ifdef H5
  if (typeof window !== 'undefined') return `${window.location.origin}${source}`
  // #endif
  return source
}

export { API_BASE }
