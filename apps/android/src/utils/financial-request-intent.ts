export interface StoredClientRequestIntent {
  version: 1
  requestId: string
  fingerprint: string
}

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{12,64}$/

export function readClientRequestIntent(value: unknown): StoredClientRequestIntent | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Partial<StoredClientRequestIntent>
  const requestId = String(raw.requestId || '').trim()
  const fingerprint = String(raw.fingerprint || '').trim()
  if (raw.version !== 1 || !REQUEST_ID_PATTERN.test(requestId) || !fingerprint || fingerprint.length > 200) {
    return null
  }
  return { version: 1, requestId, fingerprint }
}

export function ensureClientRequestIntent(
  storedValue: unknown,
  fingerprint: string,
  generatedRequestId: string,
): StoredClientRequestIntent {
  const normalizedFingerprint = String(fingerprint || '').trim()
  if (!normalizedFingerprint || normalizedFingerprint.length > 200) {
    throw new Error('invalid financial request fingerprint')
  }
  const existing = readClientRequestIntent(storedValue)
  if (existing?.fingerprint === normalizedFingerprint) return existing
  if (!REQUEST_ID_PATTERN.test(generatedRequestId)) {
    throw new Error('invalid financial client request id')
  }
  return {
    version: 1,
    requestId: generatedRequestId,
    fingerprint: normalizedFingerprint,
  }
}
