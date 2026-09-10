import OpenCC from 'opencc-js/cn2t'

// Use Taiwan-standard Traditional characters without regional phrase
// substitution. Phrase substitution can change business meaning (for example,
// converting account cancellation into sign-out), while character conversion
// keeps the original ZTW wording intact.
const convert = OpenCC.Converter({ from: 'cn', to: 'tw' })
const cache = new Map<string, string>()
const MAX_CACHE_SIZE = 800

export function toTraditionalChinese(value: string): string {
  if (!value) return value
  const cached = cache.get(value)
  if (cached !== undefined) return cached

  const converted = convert(value)
  if (cache.size >= MAX_CACHE_SIZE) cache.delete(cache.keys().next().value as string)
  cache.set(value, converted)
  return converted
}
