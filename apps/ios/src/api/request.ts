import { getToken, clearAuth } from '@/utils/auth'
import { API_BASE } from '@/utils/config'
import { useI18nStore } from '@/store/i18n'
import { stageAuthReturnPath } from '@/utils/auth-return-path'
import { requirePrivacyConsent } from '@/utils/privacy-consent'

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

export interface TrustedPublicJsonRequestOptions {
  url: string
  timeout?: number
  header?: Record<string, string>
}

const TRUSTED_PUBLIC_JSON_ORIGIN = 'https://api.bilibili.com'
const UNSAFE_HEADER_VALUE = /[\r\n\u0000]/

function trustedPublicJsonUrl(value: string): string | null {
  const url = String(value || '').trim()
  if (!url.startsWith(`${TRUSTED_PUBLIC_JSON_ORIGIN}/`) || /[\u0000-\u0020\u007f]/.test(url)) return null
  const authority = /^https:\/\/([^/?#]+)(?:[/?#]|$)/i.exec(url)?.[1]?.toLowerCase() || ''
  return authority === 'api.bilibili.com' ? url : null
}

function trustedPublicJsonHeaders(value: TrustedPublicJsonRequestOptions['header']) {
  const result: Record<string, string> = {}
  for (const [name, raw] of Object.entries(value || {})) {
    if (!['Accept', 'Referer', 'User-Agent'].includes(name)) throw new Error('Untrusted public JSON request header')
    const headerValue = String(raw || '').trim()
    if (!headerValue || UNSAFE_HEADER_VALUE.test(headerValue)) throw new Error('Invalid public JSON request header')
    result[name] = headerValue
  }
  return result
}

function rejectWhenPrivacyConsentIsMissing(reject: (reason?: unknown) => void): boolean {
  try {
    requirePrivacyConsent()
    return false
  } catch (error) {
    reject(error)
    return true
  }
}

/**
 * Credential-free transport for the one approved public metadata origin.
 * Session tokens, locale headers and API response-envelope handling must never
 * be added here because the destination is outside the canonical KAI API.
 */
export function requestTrustedPublicJson<T = unknown>(options: TrustedPublicJsonRequestOptions): Promise<T> {
  try {
    requirePrivacyConsent()
  } catch (error) {
    return Promise.reject(error)
  }
  const url = trustedPublicJsonUrl(options.url)
  if (!url) return Promise.reject(new Error('Untrusted public JSON request URL'))

  let header: Record<string, string>
  try {
    header = trustedPublicJsonHeaders(options.header)
  } catch (error) {
    return Promise.reject(error)
  }
  const timeout = Math.max(1000, Math.min(15000, Math.round(Number(options.timeout) || 15000)))
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method: 'GET',
      timeout,
      header,
      success: (response) => {
        if (rejectWhenPrivacyConsentIsMissing(reject)) return
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data as T)
          return
        }
        reject(new Error(`Public JSON request failed with HTTP ${response.statusCode}`))
      },
      fail: (error) => {
        if (rejectWhenPrivacyConsentIsMissing(reject)) return
        reject(error)
      },
    })
  })
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
  stageAuthReturnPath()
  clearAuth()
  uni.$emit('wod-auth-expired')
  // The launch gate will choose login after restore completes. Re-launching
  // here as well used to mount the login page twice and replay its entrance.
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
  const currentRoute = pages[pages.length - 1]?.route
  if (currentRoute === 'pages/privacy-consent/index' || currentRoute === 'pages/login/index') {
    expiringToken = null
    return
  }
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
  /** Only for mutations whose server endpoint safely reconciles an identical retry. */
  retryUncertainOnce?: boolean
}): Promise<T> {
  try {
    requirePrivacyConsent()
  } catch (error) {
    return Promise.reject(error)
  }
  const token = options.auth === 'none' ? '' : getToken()
  const i18n = useI18nStore()
  return new Promise((resolve, reject) => {
    const send = (attempt: 0 | 1) => {
      try {
        // Consent can be withdrawn while an earlier attempt is in flight.
        // Recheck immediately before every attempt so an automatic retry can
        // never become a new post-withdrawal business request.
        requirePrivacyConsent()
      } catch (error) {
        reject(error)
        return
      }
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
          if (rejectWhenPrivacyConsentIsMissing(reject)) return
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
          const uncertainStatus = res.statusCode === 408 || res.statusCode === 502 || res.statusCode === 503 || res.statusCode === 504
          if (options.retryUncertainOnce && attempt === 0 && uncertainStatus) {
            send(1)
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
          if (rejectWhenPrivacyConsentIsMissing(reject)) return
          if (options.retryUncertainOnce && attempt === 0) {
            send(1)
            return
          }
          if (!options.silent) uni.showToast({ title: i18n.t('网络异常'), icon: 'none' })
          reject(err)
        },
      })
    }
    send(0)
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
  try {
    requirePrivacyConsent()
  } catch (error) {
    return Promise.reject(error)
  }
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
        if (rejectWhenPrivacyConsentIsMissing(reject)) return
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
        if (rejectWhenPrivacyConsentIsMissing(reject)) return
        if (!options.silent) uni.showToast({ title: i18n.t('网络异常'), icon: 'none' })
        reject(err)
      },
    })
    task.onProgressUpdate?.((event) => {
      try {
        requirePrivacyConsent()
      } catch {
        return
      }
      const progress = Math.max(0, Math.min(100, Math.round(Number(event.progress) || 0)))
      options.onProgress?.(progress)
    })
  })
}

export function download(options: { url: string; silent?: boolean }): Promise<string> {
  try {
    requirePrivacyConsent()
  } catch (error) {
    return Promise.reject(error)
  }
  const token = getToken()
  const i18n = useI18nStore()
  return new Promise((resolve, reject) => {
    uni.downloadFile({
      url: API_BASE + options.url,
      header: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      success: result => {
        if (rejectWhenPrivacyConsentIsMissing(reject)) return
        if (result.statusCode >= 200 && result.statusCode < 300) {
          resolve(result.tempFilePath)
          return
        }
        if (!options.silent) uni.showToast({ title: i18n.t('photoLoadFailed'), icon: 'none' })
        reject(new Error(i18n.t('photoLoadFailed')))
      },
      fail: error => {
        if (rejectWhenPrivacyConsentIsMissing(reject)) return
        if (!options.silent) uni.showToast({ title: i18n.t('photoLoadFailed'), icon: 'none' })
        reject(error)
      },
    })
  })
}
