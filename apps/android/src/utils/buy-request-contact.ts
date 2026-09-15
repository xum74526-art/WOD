export function normalizeBuyRequestContactPhone(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed.length > 32 || !/^[+0-9 ()-]+$/.test(trimmed)) return null
  const normalized = trimmed.replace(/[ ()-]/g, '')
  return /^(?:[0-9]{6,20}|\+[1-9][0-9]{5,14})$/.test(normalized) ? normalized : null
}
