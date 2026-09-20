export function normalizeTempFilePaths(value: unknown): string[] {
  const paths = Array.isArray(value) ? value : typeof value === 'string' ? [value] : []
  return paths.filter((path): path is string => typeof path === 'string' && path.trim().length > 0)
}
