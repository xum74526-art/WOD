import { getToken, clearAuth } from '@/utils/auth'
import { API_BASE } from '@/utils/config'
import { useI18nStore } from '@/store/i18n'

export interface ApiResponse<T = unknown> {
  code: number
  msg: string
  data: T
  detail?: unknown
}

export class ApiRequestError extends Error {
  readonly statusCode: number

  constructor(message: string, statusCode: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.statusCode = statusCode
  }
}

let expiringToken: string | null = null

function responseBody<T>(value: unknown): Partial<ApiResponse<T>> {
  return value && typeof value === 'object' ? value as Partial<ApiResponse<T>> : {}
}

function expireSession(i18n: ReturnType<typeof useI18nStore>, requestToken: string) {
  // A response belongs to the token captured when the request started. An old
  // request may finish after the user has signed in again, so it must never
  // clear the newer session.
  if (getToken() !== requestToken || expiringToken === requestToken) return
  expiringToken = requestToken
  clearAuth()
  uni.$emit('wod-auth-expired')
  uni.reLaunch({
    url: '/pages/login/index',
    complete: () => {
      if (expiringToken === requestToken) expiringToken = null
    },
  })
}

function errorMessage(
  i18n: ReturnType<typeof useI18nStore>,
  body: Partial<ApiResponse<unknown>>,
  fallback: string,
) {
  const message = typeof body.msg === 'string' ? body.msg.trim() : ''
  const detail = typeof body.detail === 'string' ? body.detail.trim() : ''
  return i18n.tr(message || detail || i18n.t(fallback))
}

export function request<T = unknown>(options: {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: UniNamespace.RequestOptions['data']
  silent?: boolean
  /** Only credential-independent endpoints, such as deletion capability receipts. */
  auth?: 'session' | 'none'
  /** Explicit logout handles an invalid bearer locally without a second redirect. */
  unauthorized?: 'expire-session' | 'reject'
}): Promise<T> {
  const token = options.auth === 'none' ? '' : getToken()
  const i18n = useI18nStore()
  return new Promise((resolve, reject) => {
    uni.request({
      url: API_BASE + options.url,
      method: options.method || 'GET',
      data: options.data,
      timeout: 15000,
      header: {
        'Content-Type': 'application/json',
        'Accept-Language': i18n.locale,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      success: (res) => {
        const body = responseBody<T>(res.data)
        if (res.statusCode === 401 || body.code === 401) {
          if (options.auth === 'none' || options.unauthorized === 'reject') {
            reject(new ApiRequestError(errorMessage(i18n, body, '请求失败'), 401))
            return
          }
          expireSession(i18n, token)
          reject(new Error(i18n.t('未登录')))
          return
        }
        if (res.statusCode >= 400) {
          const fallback = res.statusCode === 422 ? 'requestValidationFailed' : '请求失败'
          const msg = errorMessage(i18n, body, fallback)
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new ApiRequestError(msg, res.statusCode))
          return
        }
        if (body.code !== 0 || !('data' in body)) {
          const msg = errorMessage(i18n, body, '请求失败')
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
  onProgress?: (progress: number) => void
}): Promise<T> {
  const token = getToken()
  const i18n = useI18nStore()
  return new Promise((resolve, reject) => {
    const task = uni.uploadFile({
      url: API_BASE + options.url,
      filePath: options.filePath,
      name: options.name,
      files: options.files,
      formData: options.formData,
      timeout: options.timeout || 30000,
      header: {
        'Accept-Language': i18n.locale,
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
          expireSession(i18n, token)
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
    task.onProgressUpdate?.((event) => {
      const progress = Math.max(0, Math.min(100, Math.round(Number(event.progress) || 0)))
      options.onProgress?.(progress)
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
