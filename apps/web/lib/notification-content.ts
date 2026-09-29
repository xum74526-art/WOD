import { formatCnyForLocale, type DisplayCurrencyConfig } from "./display-currency.ts";
import type { KaiLocale } from "./language.ts";
import { toTraditionalChinese } from "./traditional-chinese.ts";

type LocalizableNotice = {
  body: string;
  body_en: string | null;
  template_key: string | null;
  amount_cny: string | null;
};

export function localizedNotificationBody(
  notice: LocalizableNotice,
  locale: KaiLocale,
  currencyConfig: DisplayCurrencyConfig,
): string {
  if (notice.template_key === "daily_revenue_recorded" && notice.amount_cny !== null) {
    const amount = formatCnyForLocale(notice.amount_cny, locale, currencyConfig);
    if (locale === "en") return `${amount} of revenue has been recorded today. View details in Revenue Center.`;
    const content = `今日已记录 ${amount} 收益，可在收益中心查看明细。`;
    return locale === "zh-Hant" ? toTraditionalChinese(content) : content;
  }
  if (locale === "en" && notice.body_en) return notice.body_en;
  return locale === "zh-Hant" ? toTraditionalChinese(notice.body) : notice.body;
}
