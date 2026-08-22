import { getToken, clearAuth } from '@/utils/auth'
import { API_BASE } from '@/utils/config'
import { useI18nStore } from '@/store/i18n'

export interface ApiResponse<T = unknown> {
  code: number
  msg: string
  data: T
  detail?: unknown
}

let redirecting = false

function responseBody<T>(value: unknown): Partial<ApiResponse<T>> {
  return value && typeof value === 'object' ? value as Partial<ApiResponse<T>> : {}
}

function expireSession(i18n: ReturnType<typeof useI18nStore>) {
  clearAuth()
  uni.$emit('wod-auth-expired')
  if (redirecting) return
  redirecting = true
  uni.reLaunch({
    url: '/pages/login/index',
    complete: () => { redirecting = false },
  })
}

function errorMessage(
  i18n: ReturnType<typeof useI18nStore>,
  body: Partial<ApiResponse<unknown>>,
  fallback: string,
) {
  const detail = typeof body.detail === 'string' ? body.detail : ''
  return i18n.tr(body.msg || detail || i18n.t(fallback))
}

export function request<T = unknown>(options: {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: UniNamespace.RequestOptions['data']
  silent?: boolean
}): Promise<T> {
  const token = getToken()
  const i18n = useI18nStore()
  const localize = (message: unknown, fallback = '请求失败') => i18n.tr(message || i18n.t(fallback))
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + options.url,
      method: options.method || 'GET',
      data: options.data,
      timeout: 15000,
      header: {
        'Content-Type': 'application/json',
        'Accept-Language': i18n.lang === 'en' ? 'en-US' : 'zh-CN',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success: (res) => {
        const body = responseBody<T>(res.data)
        if (res.statusCode === 401 || body.code === 401) {
          expireSession(i18n)
          reject(new Error(i18n.t('未登录')))
          return
        }
        if (res.statusCode >= 400) {
          const msg = localize(body.msg || body.detail, '请求失败')
            || `${i18n.t('请求失败')} (${res.statusCode})`
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
          return
        }
        if (body.code !== 0 || !('data' in body)) {
          const msg = localize(body.msg)
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
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

export function upload<T = unknown>(options: {
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
        let body: Partial<ApiResponse<T>> = {}
        try {
          body = responseBody<T>(typeof res.data === 'string' ? JSON.parse(res.data) : res.data)
        } catch {
          body = {}
        }
        if (res.statusCode === 401 || body?.code === 401) {
          expireSession(i18n)
          reject(new Error(i18n.t('未登录')))
          return
        }
        if (res.statusCode >= 400 || body.code !== 0 || !('data' in body)) {
          const message = errorMessage(i18n, body, '上传失败')
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

export function download(options: { url: string; silent?: boolean }): Promise<string> {
  const token = getToken()
  const i18n = useI18nStore()
  return new Promise((resolve, reject) => {
    uni.downloadFile({
      url: API_BASE + options.url,
      header: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      success: result => {
        if (result.statusCode >= 200 && result.statusCode < 300) {
          resolve(result.tempFilePath)
          return
        }
        if (!options.silent) uni.showToast({ title: i18n.t('photoLoadFailed'), icon: 'none' })
        reject(new Error(i18n.t('photoLoadFailed')))
      },
      fail: error => {
        if (!options.silent) uni.showToast({ title: i18n.t('photoLoadFailed'), icon: 'none' })
        reject(error)
      },
    })
  })
}
