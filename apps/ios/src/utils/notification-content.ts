import type { NotificationItem } from '@/api/notification'
import { formatCnyCurrency } from './format.ts'
import type { AppLanguage } from './language.ts'
import { toTraditionalChinese } from './traditional-chinese.ts'

export function localizedNotificationContent(
  notification: NotificationItem,
  lang: AppLanguage,
  translateFallback: (value: string) => string,
): string {
  if (notification.template_key === 'daily_revenue_recorded' && notification.amount_cny != null) {
    const amount = formatCnyCurrency(notification.amount_cny, lang)
    if (lang === 'en') return `${amount} of revenue has been recorded today. View details in Revenue Center.`
    const content = `今日已记录 ${amount} 收益，可在收益中心查看明细。`
    return lang === 'zh-Hant' ? toTraditionalChinese(content) : content
  }
  if (lang === 'en' && notification.content_en) return notification.content_en
  return translateFallback(notification.content || '')
}
