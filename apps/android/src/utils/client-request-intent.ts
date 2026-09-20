export type ClientRequestIntent = Readonly<{
  signature: string
  requestId: string
}>

export function ensureClientRequestIntent(
  current: ClientRequestIntent | null,
  payload: unknown,
  createRequestId: () => string,
): ClientRequestIntent {
  const signature = JSON.stringify(payload)
  if (current?.signature === signature) return current
  return { signature, requestId: createRequestId() }
}
