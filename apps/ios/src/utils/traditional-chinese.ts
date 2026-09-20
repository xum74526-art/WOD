import OpenCC from 'opencc-js/cn2t'

// Use Taiwan-standard Traditional characters without regional phrase
// substitution. Phrase substitution can change business meaning (for example,
// converting account cancellation into sign-out), while character conversion
// keeps the registered application name intact.
const convert = OpenCC.Converter({ from: 'cn', to: 'tw' })
const cache = new Map<string, string>()
const MAX_CACHE_SIZE = 800
const REGISTERED_APP_NAME = '算力星图'

export function toTraditionalChinese(value: string): string {
  if (!value) return value
  const cached = cache.get(value)
  if (cached !== undefined) return cached

  // The store, copyright and filing name must stay byte-for-byte identical in
  // every UI language. Convert the surrounding copy while protecting the
  // registered Simplified-Chinese proper name.
  const converted = value
    .split(REGISTERED_APP_NAME)
    .map((segment) => convert(segment))
    .join(REGISTERED_APP_NAME)
  if (cache.size >= MAX_CACHE_SIZE) cache.delete(cache.keys().next().value as string)
  cache.set(value, converted)
  return converted
}
