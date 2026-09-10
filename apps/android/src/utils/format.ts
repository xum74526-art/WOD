import { ref } from 'vue'
import { languageLocale, normalizeStoredLanguage, type AppLanguage } from './language.ts'

type FormatLang = AppLanguage

function storedLang(): FormatLang {
  try { return normalizeStoredLanguage(uni.getStorageSync('xod-lang')) } catch { return 'zh-Hant' }
}

// Keep the unit language reactive. Reading storage directly inside a formatter
// is not tracked by Vue, so an in-page language switch used to update labels
// while leaving already-rendered "卡时" units unchanged until a reload.
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

function finiteNumber(value: NumericValue): number {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

/**
 * `Number#toLocaleString` 在部分 Android App Webview / JSCore 中会忽略
 * maximumFractionDigits，導致同一份數據在 H5 是兩位小數、APK 卻展示完整
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

  // ZTW 用户可见数值远小于 1e21；超出时保留安全的整数表达，避免 toFixed
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
 * 默认最多显示两位小数，不改变调用方持有的原始值或计算精度。
 */
export function formatNumber(
  value: NumericValue,
  options: { minimumFractionDigits?: number; maximumFractionDigits?: number; useGrouping?: boolean; locale?: string } = {},
): string {
  const maximumFractionDigits = Math.max(0, Math.min(options.maximumFractionDigits ?? 2, 20))
  const minimumFractionDigits = Math.max(0, Math.min(options.minimumFractionDigits ?? 0, maximumFractionDigits))
  // 保留 locale 參數以兼容現有調用；當前支持的中英文數字分隔規則相同。
  void (options.locale || currentLocale())
  return stableDecimal(
    finiteNumber(value),
    minimumFractionDigits,
    maximumFractionDigits,
    options.useGrouping ?? true,
  )
}

/** 表单输入框中的数值：最多两位小数，且不插入千分位分隔符。 */
export function formatNumberInput(value: NumericValue): string {
  return formatNumber(value, { maximumFractionDigits: 2, useGrouping: false })
}

export function formatMoney(n: number | string | undefined | null): string {
  return formatNumber(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatMoneyShort(n: number | string | undefined | null): string {
  return formatNumber(n)
}

// === 卡时（算力货币单位） ===
// 1 卡时 = 1.002 人民币
export const CARD_HOUR_RATE = 1.002

/** 人民币 → 卡时 */
export function toCardHours(rmb: number | string | undefined | null): number {
  return finiteNumber(rmb) / CARD_HOUR_RATE
}

/** 卡时 -> 人民币，仅用于向仍以 CNY 记账的后端提交数据 */
export function fromCardHours(cardHours: number | string | undefined | null): number {
  return finiteNumber(cardHours) * CARD_HOUR_RATE
}

/** 格式化为 "1,423.3卡时" */
export function fmtCH(rmb: number | string | undefined | null): string {
  const num = toCardHours(rmb)
  const unit = currentLang() === 'en' ? ' CH' : currentLang() === 'zh-Hant' ? '卡時' : '卡时'
  return formatNumber(num) + unit
}

/** 格式化为 "1.98卡时/h"（小时费率） */
export function fmtCHr(rmb: number | string | undefined | null): string {
  const num = toCardHours(rmb)
  const unit = currentLang() === 'en' ? ' CH/h' : currentLang() === 'zh-Hant' ? '卡時/h' : '卡时/h'
  return formatNumber(num) + unit
}

/** 短格式卡时（不带单位，用于模板拼接） */
export function fmtCHn(rmb: number | string | undefined | null): string {
  return formatNumber(toCardHours(rmb))
}

/** 已经以卡时为单位的数值，仅格式化展示，不再执行汇率换算。 */
export function fmtCardHours(value: NumericValue): string {
  return formatNumber(value)
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
