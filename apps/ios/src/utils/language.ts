export type AppLanguage = 'zh-Hant' | 'zh-Hans' | 'en'

export const DEFAULT_LANGUAGE: AppLanguage = 'zh-Hant'
export const LANGUAGE_ORDER: readonly AppLanguage[] = ['zh-Hant', 'zh-Hans', 'en']

export function normalizeStoredLanguage(value: unknown): AppLanguage {
  if (value === 'en') return 'en'
  if (value === 'zh-Hans' || value === 'zh-CN') return 'zh-Hans'
  if (value === 'zh-Hant' || value === 'zh-TW' || value === 'zh-HK') return 'zh-Hant'
  // Legacy clients stored all Chinese as `zh`; migrate them to the new
  // primary Traditional Chinese experience.
  return DEFAULT_LANGUAGE
}

export function languageLocale(language: AppLanguage): 'zh-TW' | 'zh-CN' | 'en-US' {
  if (language === 'en') return 'en-US'
  return language === 'zh-Hant' ? 'zh-TW' : 'zh-CN'
}

export function languageDocumentTag(language: AppLanguage): 'zh-Hant' | 'zh-Hans' | 'en' {
  return language
}

export function supportApiLanguage(language: AppLanguage): 'zh' | 'en' {
  return language === 'en' ? 'en' : 'zh'
}

export function nextLanguage(language: AppLanguage): AppLanguage {
  const index = LANGUAGE_ORDER.indexOf(language)
  return LANGUAGE_ORDER[(index + 1) % LANGUAGE_ORDER.length]
}
