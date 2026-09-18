import { getAppRelease, type MobilePlatform } from '@/api/platform'
import { useI18nStore } from '@/store/i18n'
import { openExternalLink } from '@/utils/external-link'
import { isNewerRelease, isValidRelease, normalizeVersionCode } from '@/utils/app-update-policy'

export const APP_FALLBACK_VERSION_NAME = '1.2.1'
export const APP_FALLBACK_VERSION_CODE = 122

const DISMISSAL_KEY = 'ztw_app_update_dismissal'
const DISMISSAL_DURATION_MS = 24 * 60 * 60 * 1000

export interface InstalledAppVersion {
  name: string
  code: number | null
}

export type AppUpdateCheckResult = 'update-available' | 'up-to-date' | 'unavailable' | 'dismissed'

interface DismissalRecord {
  platform: MobilePlatform
  versionCode: number
  dismissedAt: number
}

let activeCheck: Promise<AppUpdateCheckResult> | null = null
let activeCheckIsManual = false

export function getInstalledAppVersion(): InstalledAppVersion {
  try {
    const info = uni.getAppBaseInfo() as unknown as {
      appVersion?: string
      appVersionCode?: string | number
    }
    const runtimeCode = (globalThis as unknown as {
      plus?: { runtime?: { versionCode?: string | number } }
    }).plus?.runtime?.versionCode
    return {
      name: info.appVersion?.trim() || APP_FALLBACK_VERSION_NAME,
      code: normalizeVersionCode(info.appVersionCode ?? runtimeCode) ?? APP_FALLBACK_VERSION_CODE,
    }
  } catch {
    return { name: APP_FALLBACK_VERSION_NAME, code: APP_FALLBACK_VERSION_CODE }
  }
}

function dismissalRecord(): DismissalRecord | null {
  try {
    const value = uni.getStorageSync(DISMISSAL_KEY) as Partial<DismissalRecord> | null
    const versionCode = normalizeVersionCode(value?.versionCode)
    const dismissedAt = Number(value?.dismissedAt)
    if ((value?.platform !== 'android' && value?.platform !== 'ios')
      || versionCode === null
      || !Number.isFinite(dismissedAt)) return null
    return { platform: value.platform, versionCode, dismissedAt }
  } catch {
    return null
  }
}

function wasRecentlyDismissed(platform: MobilePlatform, versionCode: number): boolean {
  const record = dismissalRecord()
  return record?.platform === platform
    && record.versionCode === versionCode
    && Date.now() - record.dismissedAt < DISMISSAL_DURATION_MS
}

function rememberDismissal(platform: MobilePlatform, versionCode: number) {
  try {
    uni.setStorageSync(DISMISSAL_KEY, { platform, versionCode, dismissedAt: Date.now() })
  } catch {
    // Storage failure must not turn an optional update prompt into an app error.
  }
}

function manualToast(key: string) {
  uni.showToast({ title: useI18nStore().t(key), icon: 'none' })
}

async function runCheck(platform: MobilePlatform, manual: boolean): Promise<AppUpdateCheckResult> {
  const i18n = useI18nStore()
  let release
  try {
    release = await getAppRelease(platform)
  } catch {
    if (manual) manualToast('appUpdateUnavailable')
    return 'unavailable'
  }

  if (!isValidRelease(release, platform)) {
    if (manual) manualToast('appUpdateUnavailable')
    return 'unavailable'
  }

  const current = getInstalledAppVersion()
  if (!isNewerRelease(current.name, current.code, release)) {
    if (manual) manualToast('appUpdateLatest')
    return 'up-to-date'
  }

  const latestCode = normalizeVersionCode(release.latest_version_code) as number
  if (!manual && wasRecentlyDismissed(platform, latestCode)) return 'dismissed'

  const rawNotes = i18n.lang === 'en' ? release.release_notes_en : release.release_notes_zh
  const notes = (Array.isArray(rawNotes) ? rawNotes : [])
    .filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    .map((item) => i18n.lang === 'zh-Hant' ? i18n.tr(item) : item)
    .slice(0, 5)
  const summary = i18n.t('appUpdateContent', {
    current: current.name,
    latest: release.latest_version_name || '',
  })
  const content = notes.length > 0
    ? `${summary}\n\n${notes.map((item) => `• ${item.trim()}`).join('\n')}`
    : summary

  const confirmed = await new Promise<boolean>((resolve) => {
    uni.showModal({
      title: i18n.t('appUpdateTitle', { version: release.latest_version_name || '' }),
      content,
      confirmText: i18n.t('appUpdateNow'),
      cancelText: i18n.t('appUpdateLater'),
      success: ({ confirm }) => resolve(confirm),
      fail: () => resolve(false),
    })
  })
  if (confirmed) {
    openExternalLink(release.update_url as string, () => manualToast('appUpdateLinkCopied'))
  } else {
    rememberDismissal(platform, latestCode)
  }
  return 'update-available'
}

export function checkForAppUpdate(
  platform: MobilePlatform,
  options: { manual?: boolean } = {},
): Promise<AppUpdateCheckResult> {
  const manual = options.manual === true
  if (activeCheck) {
    if (!manual || activeCheckIsManual) return activeCheck
    return activeCheck.then((result) => result === 'update-available'
      ? result
      : runCheck(platform, true))
  }
  activeCheckIsManual = manual
  activeCheck = runCheck(platform, manual).finally(() => {
    activeCheck = null
    activeCheckIsManual = false
  })
  return activeCheck
}
