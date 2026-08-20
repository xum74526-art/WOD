export function makeIdempotencyKey(scope: string, supplied?: string): string {
  const value = supplied?.trim()
  if (value && value.length >= 16 && value.length <= 64) return value
  return `${scope}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`.slice(0, 64)
}
