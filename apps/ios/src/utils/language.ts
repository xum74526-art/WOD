export type AppLanguage = 'zh-Hant' | 'zh-Hans' | 'en'

export interface AppLanguageOption {
  language: AppLanguage
  label: string
  shortLabel: string
  locale: 'zh-TW' | 'zh-CN' | 'en-US'
  mark: string
}

export const DEFAULT_LANGUAGE: AppLanguage = 'zh-Hant'
export const LANGUAGE_ORDER: readonly AppLanguage[] = ['zh-Hant', 'zh-Hans', 'en']
export const LANGUAGE_OPTIONS: readonly AppLanguageOption[] = [
  { language: 'zh-Hant', label: '繁體中文', shortLabel: '繁中', locale: 'zh-TW', mark: '繁' },
  { language: 'zh-Hans', label: '简体中文', shortLabel: '简中', locale: 'zh-CN', mark: '简' },
  { language: 'en', label: 'English', shortLabel: 'EN', locale: 'en-US', mark: 'EN' },
]

export function languageOption(language: AppLanguage): AppLanguageOption {
  return LANGUAGE_OPTIONS.find((option) => option.language === language) ?? LANGUAGE_OPTIONS[0]
}

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
