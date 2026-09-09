export interface PasswordResetCallback {
  token: string
}

let pendingToken = ''
let lastCapturedFingerprint = ''

function decodeValue(value: string) {
  try {
    return decodeURIComponent(value.replace(/\+/g, ' '))
  } catch {
    return value
  }
}

function tokenFromParameters(parameters: string) {
  for (const pair of parameters.split('&')) {
    if (!pair) continue
    const separator = pair.indexOf('=')
    const key = decodeValue(separator < 0 ? pair : pair.slice(0, separator))
    if (key !== 'token') continue
    const token = decodeValue(separator < 0 ? '' : pair.slice(separator + 1)).trim()
    return token && token.length <= 512 ? token : ''
  }
  return ''
}

/** Accept only ZTW-owned reset callbacks, never a token embedded in an arbitrary URL. */
export function parsePasswordResetUrl(input: unknown): PasswordResetCallback | null {
  if (typeof input !== 'string') return null
  const raw = input.trim()
  const trustedWebUrl = /^https:\/\/wod\.kai\.com\/reset-password#token=/i.test(raw)
  // Verified iOS Universal Links may expose the route without repeating the origin.
  const trustedRuntimeValue = /^\/?reset-password#token=/i.test(raw)
  if (!trustedWebUrl && !trustedRuntimeValue) return null

  const fragmentStart = raw.indexOf('#')
  const token = tokenFromParameters(raw.slice(fragmentStart + 1))
  return token ? { token } : null
}

export function passwordResetCallbackFingerprint(callback: PasswordResetCallback) {
  let hash = 2166136261
  for (let index = 0; index < callback.token.length; index += 1) {
    hash ^= callback.token.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}

/** Stage a one-time token in process memory so it never enters routing or storage logs. */
export function stagePasswordResetCallback(input: unknown, allowRepeatedIntent = false) {
  const callback = parsePasswordResetUrl(input)
  if (!callback) return false
  const fingerprint = passwordResetCallbackFingerprint(callback)
  if (!allowRepeatedIntent && fingerprint === lastCapturedFingerprint) return false
  pendingToken = callback.token
  lastCapturedFingerprint = fingerprint
  return true
}

export function takePendingPasswordResetToken() {
  const token = pendingToken
  pendingToken = ''
  return token
}
