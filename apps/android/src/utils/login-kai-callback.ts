import {
  kaiAuthCallbackFingerprint,
  parseKaiAuthUrl,
  type KaiAuthCallback,
} from './kai-auth-callback.ts'

export const PENDING_KAI_INTENT_KEY = 'wod_kai_auth_intent'
export const KAI_LOGIN_INTENT_TTL_MS = 10 * 60 * 1000

export type KaiLoginIntent = 'login' | 'register'

interface StoredKaiLoginIntent {
  intent: KaiLoginIntent
  startedAt: number
}

let pendingCallback: KaiAuthCallback | null = null
let lastFingerprint = ''

export function createPendingKaiLoginIntent(intent: KaiLoginIntent, now = Date.now()): StoredKaiLoginIntent {
  return { intent, startedAt: now }
}

export function readPendingKaiLoginIntent(value: unknown, now = Date.now()): KaiLoginIntent | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Partial<StoredKaiLoginIntent>
  if (record.intent !== 'login' && record.intent !== 'register') return null
  if (typeof record.startedAt !== 'number' || !Number.isFinite(record.startedAt)) return null
  const age = now - record.startedAt
  if (age < 0 || age > KAI_LOGIN_INTENT_TTL_MS) return null
  return record.intent
}

/**
 * Capture only a trusted native KAI callback in process memory.
 *
 * ``parseKaiAuthUrl`` rejects foreign schemes and paths while still accepting
 * the argument-only form exposed by some App-Plus runtimes.  A callback is
 * staged only while this installation has a recorded login/register intent,
 * so an unrelated scheme launch cannot switch the signed-in identity.
 */
export function stageLoginKaiCallback(input: unknown, hasPendingIntent = false) {
  const callback = parseKaiAuthUrl(input)
  if (!hasPendingIntent || (!callback?.ticket && !callback?.error)) return false
  const next = callback.ticket ? { ticket: callback.ticket } : { error: callback.error }
  const fingerprint = kaiAuthCallbackFingerprint(next)
  if (fingerprint === lastFingerprint) return false
  if (pendingCallback?.ticket && next.error) return false
  lastFingerprint = fingerprint
  pendingCallback = next
  return true
}

export function peekPendingLoginKaiCallback() {
  return pendingCallback
}

export function hasPendingLoginKaiCallback() {
  return pendingCallback !== null
}

export function clearPendingLoginKaiCallback(callback?: KaiAuthCallback | null) {
  if (callback && pendingCallback) {
    if (kaiAuthCallbackFingerprint(callback) !== kaiAuthCallbackFingerprint(pendingCallback)) return false
  }
  pendingCallback = null
  return true
}
