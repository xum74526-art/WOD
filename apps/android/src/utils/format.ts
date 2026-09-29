import { ref } from 'vue'
import { languageLocale, normalizeStoredLanguage, type AppLanguage } from './language.ts'

type FormatLang = AppLanguage

function storedLang(): FormatLang {
  try { return normalizeStoredLanguage(uni.getStorageSync('xod-lang')) } catch { return 'zh-Hant' }
}

// Keep the unit language reactive. Reading storage directly inside a formatter
// is not tracked by Vue, so an in-page language switch used to update labels
// while leaving already-rendered money units unchanged until a reload.
const formatLang = ref<FormatLang>(storedLang())

export function setFormatLanguage(lang: FormatLang): void {
  formatLang.value = lang
}

function currentLang(): FormatLang {
  return formatLang.value
}

function currentLocale(): string {
  return languageLocale(currentLang())
}

type NumericValue = number | string | undefined | null

export type DisplayCurrencyCode = 'CNY' | 'HKD' | 'USD'
export type DisplayCurrencyConfig = {
  card_hour_cny_rate: number
  rates: Record<DisplayCurrencyCode, number>
}

export const DEFAULT_DISPLAY_CURRENCY_CONFIG: Readonly<DisplayCurrencyConfig> = Object.freeze({
  card_hour_cny_rate: 1,
  rates: Object.freeze({ CNY: 1, HKD: 1.169032900251, USD: 0.149020326907 }),
})

const displayCurrencyConfig = ref<DisplayCurrencyConfig>({
  card_hour_cny_rate: DEFAULT_DISPLAY_CURRENCY_CONFIG.card_hour_cny_rate,
  rates: { ...DEFAULT_DISPLAY_CURRENCY_CONFIG.rates },
})

/** Apply the server-owned display rates while keeping the ledger directly in CNY. */
export function setDisplayCurrencyConfig(config?: Partial<DisplayCurrencyConfig> | null): void {
  const positiveRate = (candidate: unknown, fallback: number) => {
    const parsed = Number(candidate)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
  }
  displayCurrencyConfig.value = {
    card_hour_cny_rate: 1,
    rates: {
      CNY: 1,
      HKD: positiveRate(config?.rates?.HKD, DEFAULT_DISPLAY_CURRENCY_CONFIG.rates.HKD),
      USD: positiveRate(config?.rates?.USD, DEFAULT_DISPLAY_CURRENCY_CONFIG.rates.USD),
    },
  }
}

export function displayCurrencyCode(lang: FormatLang = currentLang()): DisplayCurrencyCode {
  if (lang === 'en') return 'USD'
  return lang === 'zh-Hant' ? 'HKD' : 'CNY'
}

export function displayCurrencySymbol(lang: FormatLang = currentLang()): string {
  const currency = displayCurrencyCode(lang)
  if (currency === 'HKD') return 'HK$'
  if (currency === 'USD') return 'US$'
  return '¥'
}

export function cnyToDisplayCurrency(value: NumericValue, lang: FormatLang = currentLang()): number {
  const rate = displayCurrencyConfig.value.rates[displayCurrencyCode(lang)]
  return finiteNumber(value) * (rate > 0 ? rate : 1)
}

export function displayCurrencyToCny(value: NumericValue, lang: FormatLang = currentLang()): number {
  const rate = displayCurrencyConfig.value.rates[displayCurrencyCode(lang)]
  return finiteNumber(value) / (rate > 0 ? rate : 1)
}

export function normalizeDisplayInputToCny(
  value: NumericValue,
  options: { fractionDigits?: number; displayFractionDigits?: number; minimum?: number; maximum?: number } = {},
  lang: FormatLang = currentLang(),
): number {
  const fractionDigits = Math.max(0, Math.min(options.fractionDigits ?? 3, 6))
  const displayFractionDigits = Math.max(0, Math.min(options.displayFractionDigits ?? 3, 6))
  const raw = displayCurrencyToCny(value, lang)
  const halfDisplayStep = 0.5 * (10 ** -displayFractionDigits)
  const tolerance = Math.abs(displayCurrencyToCny(halfDisplayStep, lang)) + Number.EPSILON
  if (Number.isFinite(options.minimum) && raw < Number(options.minimum) && Number(options.minimum) - raw <= tolerance) {
    return Number(options.minimum)
  }
  if (Number.isFinite(options.maximum) && raw > Number(options.maximum) && raw - Number(options.maximum) <= tolerance) {
    return Number(options.maximum)
  }
  return Number(raw.toFixed(fractionDigits))
}

export function cardHoursToDisplayCurrency(value: NumericValue, lang: FormatLang = currentLang()): number {
  return cnyToDisplayCurrency(value, lang)
}

export function displayCurrencyToCardHours(value: NumericValue, lang: FormatLang = currentLang()): number {
  return displayCurrencyToCny(value, lang)
}

export function formatCnyCurrency(value: NumericValue, lang: FormatLang = currentLang()): string {
  return `${displayCurrencySymbol(lang)}${formatAmount(cnyToDisplayCurrency(value, lang))}`
}

export function formatCardHourCurrency(value: NumericValue, lang: FormatLang = currentLang()): string {
  return `${displayCurrencySymbol(lang)}${formatAmount(cardHoursToDisplayCurrency(value, lang))}`
}

function finiteNumber(value: NumericValue): number {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

/**
 * `Number#toLocaleString` 在部分 Android App Webview / JSCore 中会忽略
 * maximumFractionDigits，导致同一份数据在 H5 是两位小数、APK 却展示完整
 * 浮点尾数。这里仅使用项目实际需要的中英文数字规则（千分位逗号、小数点）
 * 手工生成结果，保证 H5、Android 与小程序输出一致。
 */
function stableDecimal(
  value: number,
  minimumFractionDigits: number,
  maximumFractionDigits: number,
  useGrouping: boolean,
): string {
  const normalized = Object.is(value, -0) ? 0 : value
  const negative = normalized < 0
  const absolute = Math.abs(normalized)

  // KAI星算用户可见数值远小于 1e21；超出时保留安全的整数表达，避免 toFixed
  // 返回科学计数法后被误当成小数拆分。
  const scale = 10 ** maximumFractionDigits
  // 先在目标精度上取整，抵消 1.005 这类二进制浮点值直接
  // `toFixed(2)` 得到 1.00 的边界误差。这里只改变展示值，不会回写计算值。
  const rounded = maximumFractionDigits > 0 && absolute < 1e21
    ? Math.round((absolute + Number.EPSILON) * scale) / scale
    : absolute
  let fixed = absolute >= 1e21
    ? Math.round(absolute).toString()
    : rounded.toFixed(maximumFractionDigits)

  const parts = fixed.split('.')
  let integerPart = parts[0]
  let fractionPart = parts[1] || ''
  while (fractionPart.length > minimumFractionDigits && fractionPart.endsWith('0')) {
    fractionPart = fractionPart.slice(0, -1)
  }

  if (useGrouping && !/[eE]/.test(integerPart)) {
    integerPart = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  }

  const isRoundedZero = /^0+$/.test(parts[0]) && (!fractionPart || /^0+$/.test(fractionPart))
  const sign = negative && !isRoundedZero ? '-' : ''
  return `${sign}${integerPart}${fractionPart ? `.${fractionPart}` : ''}`
}

/**
 * 用户界面数值的统一格式化入口。
 * 默认最多显示三位小数，不改变调用方持有的原始值或计算精度。
 */
export function formatNumber(
  value: NumericValue,
  options: { minimumFractionDigits?: number; maximumFractionDigits?: number; useGrouping?: boolean; locale?: string } = {},
): string {
  const maximumFractionDigits = Math.max(0, Math.min(options.maximumFractionDigits ?? 3, 20))
  const minimumFractionDigits = Math.max(0, Math.min(options.minimumFractionDigits ?? 0, maximumFractionDigits))
  // 保留 locale 参数以兼容现有调用；当前支持的 zh-CN / en-US 数字分隔规则相同。
  void (options.locale || currentLocale())
  return stableDecimal(
    finiteNumber(value),
    minimumFractionDigits,
    maximumFractionDigits,
    options.useGrouping ?? true,
  )
}

/** 表单输入框中的数值：最多三位小数，且不插入千分位分隔符。 */
export function formatNumberInput(value: NumericValue): string {
  return formatNumber(value, { maximumFractionDigits: 3, useGrouping: false })
}

export function formatMoney(n: number | string | undefined | null): string {
  return formatAmount(n)
}

export function formatMoneyShort(n: number | string | undefined | null): string {
  return formatNumber(n)
}

/** 法币、兼容账本金额、汇率与商品价格统一显示三位小数。 */
export function formatAmount(value: NumericValue, useGrouping = true): string {
  return formatNumber(value, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
    useGrouping,
  })
}

// === Historical API compatibility ===
// These helpers keep installed clients and legacy field names readable. The
// account itself settles CNY directly, so the compatibility rate is 1:1.
export const CARD_HOUR_RATE = 1
export const LEGACY_CARD_HOUR_CNY_RATE = 1.002

/** CNY → legacy ledger field value. */
export function toCardHours(rmb: number | string | undefined | null): number {
  return finiteNumber(rmb) / CARD_HOUR_RATE
}

/** Legacy ledger field value → CNY. */
export function fromCardHours(cardHours: number | string | undefined | null): number {
  return finiteNumber(cardHours) * CARD_HOUR_RATE
}

/** Convert values embedded in pre-migration text; never use for ledger fields. */
export function legacyCardHoursToCny(cardHours: number | string | undefined | null): number {
  return finiteNumber(cardHours) * LEGACY_CARD_HOUR_CNY_RATE
}

export function formatLegacyCardHourCurrency(
  cardHours: number | string | undefined | null,
  lang: FormatLang = currentLang(),
): string {
  return formatCnyCurrency(legacyCardHoursToCny(cardHours), lang)
}

/** 将 CNY 原始价格格式化为当前语言对应的法币。 */
export function fmtCH(rmb: number | string | undefined | null): string {
  return formatCnyCurrency(rmb)
}

/** 将 CNY 小时费率格式化为当前语言对应的法币。 */
export function fmtCHr(rmb: number | string | undefined | null): string {
  return `${formatCnyCurrency(rmb)}/h`
}

/** CNY 的本地法币数值（不带单位，用于模板拼接）。 */
export function fmtCHn(rmb: number | string | undefined | null): string {
  return formatAmount(cnyToDisplayCurrency(rmb))
}

/** 将兼容账本字段中的 CNY 数值转换为当前语言对应的法币数值。 */
export function fmtCardHours(value: NumericValue): string {
  return formatAmount(cardHoursToDisplayCurrency(value))
}

export function formatDate(s?: string): string {
  if (!s) return ''
  return s.slice(0, 10)
}

/** Format API deadlines in the platform's Asia/Shanghai business timezone. */
export function formatDeadline(s?: string | null): string {
  if (!s) return ''
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(s) ? s : `${s}Z`
  const timestamp = new Date(normalized).getTime()
  if (!Number.isFinite(timestamp)) return s.replace('T', ' ').slice(0, 16)

  const cst = new Date(timestamp + 8 * 60 * 60 * 1000)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${cst.getUTCFullYear()}-${pad(cst.getUTCMonth() + 1)}-${pad(cst.getUTCDate())} ${pad(cst.getUTCHours())}:${pad(cst.getUTCMinutes())} UTC+8`
}
