import OpenCC from "opencc-js/cn2t";

// Convert characters only. Regional phrase substitution can alter business
// meaning, while Taiwan-standard characters preserve the original wording.
const convert = OpenCC.Converter({ from: "cn", to: "tw" });
const cache = new Map<string, string>();
const MAX_CACHE_SIZE = 1200;

export function toTraditionalChinese(value: string): string {
  if (!value) return value;
  const cached = cache.get(value);
  if (cached !== undefined) return cached;

  const converted = convert(value);
  if (cache.size >= MAX_CACHE_SIZE) cache.delete(cache.keys().next().value as string);
  cache.set(value, converted);
  return converted;
}
