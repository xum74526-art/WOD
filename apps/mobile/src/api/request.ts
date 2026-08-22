import { getToken, clearAuth } from '@/utils/auth'
import { API_BASE } from '@/utils/config'
import { useI18nStore } from '@/store/i18n'

export interface ApiResponse<T = any> {
  code: number
  msg: string
  data: T
}

let redirecting = false

export function request<T = any>(options: {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: any
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
        const body = res.data as ApiResponse<T>
        if (res.statusCode === 401 || (body && body.code === 401)) {
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
            body && (body.msg || (body as any).detail),
            '请求失败',
          ) || `${i18n.t('请求失败')} (${res.statusCode})`
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
          return
        }
        if (body.code !== 0) {
          const msg = localize(body.msg)
          if (!options.silent) uni.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
          return
        }
        resolve(body.data)
      },
      fail: (err) => {
        if (!options.silent) uni.showToast({ title: i18n.t('网络异常'), icon: 'none' })
        reject(err)
      },
    })
  })
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
        if (res.statusCode === 401 || body?.code === 401) {
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
        if (res.statusCode >= 400 || !body || body.code !== 0) {
          const message = i18n.tr(body?.msg || i18n.t('上传失败'))
          if (!options.silent) uni.showToast({ title: message, icon: 'none' })
          reject(new Error(message))
          return
        }
        resolve(body.data)
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
