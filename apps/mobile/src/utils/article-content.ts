const NAMED_ENTITIES: Record<string, string> = {
  amp: '&',
  apos: "'",
  gt: '>',
  lt: '<',
  nbsp: ' ',
  quot: '"',
}

function decodeEntity(entity: string): string {
  if (entity.startsWith('#x') || entity.startsWith('#X')) {
    const value = Number.parseInt(entity.slice(2), 16)
    return Number.isFinite(value) ? String.fromCodePoint(value) : `&${entity};`
  }
  if (entity.startsWith('#')) {
    const value = Number.parseInt(entity.slice(1), 10)
    return Number.isFinite(value) ? String.fromCodePoint(value) : `&${entity};`
  }
  return NAMED_ENTITIES[entity] ?? `&${entity};`
}

export function articlePlainText(value?: string | null): string {
  return String(value || '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&([^;\s]{1,16});/g, (_, entity: string) => decodeEntity(entity))
    .replace(/\s+/g, ' ')
    .trim()
}

export function articlePreview(summary?: string | null, content?: string | null, title?: string | null): string {
  const text = articlePlainText(summary || content || title)
  return text.length > 240 ? `${text.slice(0, 237).trimEnd()}...` : text
}

export function isArticleHtml(value?: string | null): boolean {
  return /<(?:p|br|h[2-4]|ul|ol|li|blockquote|pre|code|strong|em|a|img|figure|table)\b/i.test(String(value || ''))
}
