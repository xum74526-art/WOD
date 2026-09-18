import { kaiAuthCallbackFingerprint, type KaiAuthCallback } from './kai-auth-callback.ts'

export interface PendingDeletionKaiCallback { token?: string; error?: string }

let flowPending = false
let pendingCallback: PendingDeletionKaiCallback | null = null
let lastFingerprint = ''

export function beginDeletionKaiReauth() { flowPending = true }
export function cancelDeletionKaiReauth() { flowPending = false }

/** Keep the short-lived OIDC proof in process memory only. */
export function stageDeletionKaiCallback(callback: KaiAuthCallback | null) {
  if (!callback?.deletionToken && !(flowPending && callback?.error)) return false
  const fingerprint = kaiAuthCallbackFingerprint(callback)
  if (fingerprint === lastFingerprint) return false
  lastFingerprint = fingerprint
  flowPending = false
  pendingCallback = callback.deletionToken
    ? { token: callback.deletionToken }
    : { error: callback.error || 'authorization_failed' }
  return true
}

export function takePendingDeletionKaiCallback() {
  const value = pendingCallback
  pendingCallback = null
  return value
}
