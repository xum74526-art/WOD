export type MobilePlatform = 'android' | 'ios'

export interface ComparableRelease {
  platform: MobilePlatform
  application_id: string | null
  available: boolean
  latest_version_name: string | null
  latest_version_code: number | null
  update_url: string | null
}

const EXPECTED_APPLICATION_ID: Record<MobilePlatform, string> = {
  android: 'com.kai.ztwstarmap',
  ios: 'com.kai.ztwstarmap',
}

export function normalizeVersionCode(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(String(value ?? '').trim())
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

export function compareVersionNames(left: string, right: string): number {
  const parse = (value: string) => {
    if (!/^\d+(?:\.\d+)*$/.test(value.trim())) return null
    return value.trim().split('.').map((part) => Number(part))
  }
  const leftParts = parse(left)
  const rightParts = parse(right)
  if (!leftParts || !rightParts) return 0
  const length = Math.max(leftParts.length, rightParts.length)
  for (let index = 0; index < length; index += 1) {
    const difference = (leftParts[index] ?? 0) - (rightParts[index] ?? 0)
    if (difference !== 0) return difference > 0 ? 1 : -1
  }
  return 0
}

export function isTrustedUpdateUrl(platform: MobilePlatform, value: unknown): boolean {
  const candidate = typeof value === 'string' ? value.trim() : ''
  // APP-PLUS does not expose the browser URL global consistently. Exact
  // allow-list patterns keep this check available in every native runtime.
  if (platform === 'android') {
    return /^https:\/\/wod\.kai\.com\/download\/[A-Za-z0-9._~-]+\.apk$/i.test(candidate)
  }
  return /^https:\/\/apps\.apple\.com\/[A-Za-z0-9._~%/-]+$/i.test(candidate)
}

export function isValidRelease(release: unknown, platform: MobilePlatform): release is ComparableRelease {
  if (!release || typeof release !== 'object') return false
  const value = release as Partial<ComparableRelease>
  return value.platform === platform
    && value.application_id === EXPECTED_APPLICATION_ID[platform]
    && value.available === true
    && typeof value.latest_version_name === 'string'
    && Boolean(value.latest_version_name.trim())
    && normalizeVersionCode(value.latest_version_code) !== null
    && isTrustedUpdateUrl(platform, value.update_url)
}

export function isNewerRelease(
  currentVersionName: string,
  currentVersionCode: number | null,
  release: ComparableRelease,
): boolean {
  const latestCode = normalizeVersionCode(release.latest_version_code)
  if (currentVersionCode !== null && latestCode !== null) return latestCode > currentVersionCode
  return compareVersionNames(release.latest_version_name || '', currentVersionName) > 0
}
