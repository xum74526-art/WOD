import { formatCnyCurrency, formatLegacyCardHourCurrency } from './format.ts'

function hintMoney(source: string, raw: string): string {
  const value = Number(raw.replace(/,/g, ''))
  return /卡时|卡時/.test(source)
    ? formatLegacyCardHourCurrency(value, 'en')
    : formatCnyCurrency(value, 'en')
}

export function translateDynamicEnglishText(source: string): string | null {
  let match = source.match(/^再(?:消费|购买)\s*(?:¥\s*)?([\d,.]+)(?:\s*卡时)?\s*可升至\s*([\d.]+)%\s*返佣$/)
  if (match) return `Spend ${hintMoney(source, match[1])} more to reach the ${match[2]}% personal purchase rebate tier.`

  match = source.match(/^再销售\s*(?:¥\s*)?([\d,.]+)(?:\s*卡时)?\s*可升至\s*([\d.]+)%\s*返佣$/)
  if (match) return `Confirm ${hintMoney(source, match[1])} more in sales to reach the ${match[2]}% seller sales rebate tier.`

  match = source.match(/^已达最高返佣等级\s*([\d.]+)%$/)
  if (match) return `Highest rebate tier reached: ${match[1]}%`

  match = source.match(/^再邀请\s*([\d,.]+)\s*人升级至\s*([\d.]+)%\s*返利$/)
  if (match) return `Invite ${match[1]} more people to reach a ${match[2]}% reward rate`

  if (source === '已达最高返利等级') return 'Highest invitation reward tier reached'

  return null
}
