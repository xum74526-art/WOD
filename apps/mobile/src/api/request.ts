import { getToken, clearAuth } from '@/utils/auth'
import { API_BASE } from '@/utils/config'
import { useI18nStore } from '@/store/i18n'

export interface ApiResponse<T = any> {
  data?: T
  meta?: Record<string, unknown>
  error?: {
    code?: string
    message?: string
  }
}

let redirecting = false

export interface RequestOptions {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  data?: any
  silent?: boolean
  headers?: Record<string, string>
  /** Reuse a successful GET response briefly. Mutating requests are never cached. */
  cacheMs?: number
  forceRefresh?: boolean
}

const responseCache = new Map<string, { expiresAt: number; body: ApiResponse<unknown> }>()
const requestsInFlight = new Map<string, Promise<ApiResponse<unknown>>>()

function stableRequestKey(options: RequestOptions, token: string, lang: string) {
  const method = (options.method || 'GET').toUpperCase()
  let data = ''
  try { data = JSON.stringify(options.data || null) } catch { data = String(options.data || '') }
  return `${method}|${options.url}|${data}|${lang}|${token}`
}

function sendRequest<T = any>(options: RequestOptions): Promise<ApiResponse<T>> {
  const token = getToken()
  const i18n = useI18nStore()
  const localize = (message: unknown, fallback = '请求失败') => i18n.tr(message || i18n.t(fallback))
  const method = (options.method || 'GET').toUpperCase()
  const requestKey = stableRequestKey(options, token || '', i18n.lang)
  if (method === 'GET') {
    const cached = responseCache.get(requestKey)
    if (!options.forceRefresh && cached && cached.expiresAt > Date.now()) {
      return Promise.resolve(cached.body as ApiResponse<T>)
    }
    const active = requestsInFlight.get(requestKey)
    if (active) return active as Promise<ApiResponse<T>>
  }

  const transport = new Promise<ApiResponse<T>>((resolve, reject) => {
    uni.request({
      url: API_BASE + options.url,
      // uni-app's bundled type omits PATCH even though the H5/App transports support it.
      method: (options.method || 'GET') as UniApp.RequestOptions['method'],
      data: options.data,
      timeout: 15000,
      header: {
        'Content-Type': 'application/json',
        'Accept-Language': i18n.lang === 'en' ? 'en-US' : 'zh-CN',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
      success: (res) => {
        const body = res.data as ApiResponse<T>
        if (res.statusCode === 401) {
          clearAuth()
          uni.$emit('wod-auth-expired')
          if (!redirecting) {
            redirecting = true
            uni.reLaunch({
              url: '/pages/login/index',
              complete: () => { redirecting = false },
            })
          }
          reject(new Error(i18n.t('未登录')))
          return
        }
        if (res.statusCode >= 400) {
          const msg = localize(
            body?.error?.message || (body as any)?.detail,
            '请求失败',
          ) || `${i18n.t('请求失败')} (${res.statusCode})`
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
          return
        }
        if (!body || body.error) {
          const msg = localize(body?.error?.message)
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
          return
        }
        resolve(body)
      },
      fail: (err) => {
        if (!options.silent) uni.showToast({ title: i18n.t('网络异常'), icon: 'none' })
        reject(err)
      },
    })
  })
  if (method !== 'GET') return transport

  const tracked = transport.then((body) => {
    if ((options.cacheMs || 0) > 0) {
      responseCache.set(requestKey, { expiresAt: Date.now() + Number(options.cacheMs), body })
      if (responseCache.size > 100) responseCache.delete(responseCache.keys().next().value as string)
    }
    return body
  }).finally(() => {
    if (requestsInFlight.get(requestKey) === tracked) requestsInFlight.delete(requestKey)
  })
  requestsInFlight.set(requestKey, tracked as Promise<ApiResponse<unknown>>)
  return tracked
}

export function request<T = any>(options: RequestOptions): Promise<T> {
  return sendRequest<T>(options).then(body => body.data as T)
}

export function requestEnvelope<
  T = any,
  M extends Record<string, unknown> = Record<string, unknown>,
>(options: RequestOptions): Promise<{ data: T; meta: M }> {
  return sendRequest<T>(options).then(body => ({
    data: body.data as T,
    meta: (body.meta || {}) as M,
  }))
}

export function upload<T = any>(options: {
  url: string
  filePath?: string
  name?: string
  files?: Array<{ name: string; uri: string }>
  formData?: Record<string, string>
  silent?: boolean
  timeout?: number
}): Promise<T> {
  const token = getToken()
  const i18n = useI18nStore()
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: API_BASE + options.url,
      filePath: options.filePath,
      name: options.name,
      files: options.files,
      formData: options.formData,
      timeout: options.timeout || 30000,
      header: {
        'Accept-Language': i18n.lang === 'en' ? 'en-US' : 'zh-CN',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success: (res) => {
        let body: ApiResponse<T> | null = null
        try {
          body = typeof res.data === 'string' ? JSON.parse(res.data) : res.data as ApiResponse<T>
        } catch {
          body = null
        }
        if (res.statusCode === 401) {
          clearAuth()
          uni.$emit('wod-auth-expired')
          if (!redirecting) {
            redirecting = true
            uni.reLaunch({
              url: '/pages/login/index',
              complete: () => { redirecting = false },
            })
          }
          reject(new Error(i18n.t('未登录')))
          return
        }
        if (res.statusCode >= 400 || !body || body.error) {
          const message = i18n.tr(body?.error?.message || i18n.t('上传失败'))
          if (!options.silent) uni.showToast({ title: message, icon: 'none' })
          reject(new Error(message))
          return
        }
        resolve(body.data as T)
      },
      fail: (err) => {
        if (!options.silent) uni.showToast({ title: i18n.t('网络异常'), icon: 'none' })
        reject(err)
      },
    })
  })
}
