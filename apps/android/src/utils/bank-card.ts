export const REGISTERED_BANK_CARD_STATUSES = ['registered', 'pending_review', 'active'] as const

// These prefixes were assigned to different banks in the historical static
// table. Never suggest a bank for them. A BIN suggestion is convenience only
// and never represents validation by the issuing bank.
export const AMBIGUOUS_BANK_BIN_PREFIXES = new Set(['621285', '621286', '621287', '621662', '622560'])

const BANK_BIN_SUGGESTIONS: Record<string, string> = {
  '622202': '中国工商银行', '622208': '中国工商银行', '621226': '中国工商银行', '621225': '中国工商银行',
  '622848': '中国农业银行', '622849': '中国农业银行', '622836': '中国农业银行', '621336': '中国农业银行',
  '621660': '中国银行', '621669': '中国银行', '621721': '中国银行', '621293': '中国银行',
  '621280': '中国建设银行', '621281': '中国建设银行', '622280': '中国建设银行', '622288': '中国建设银行',
  '622260': '交通银行', '622270': '交通银行', '621002': '交通银行',
  '622580': '招商银行', '622581': '招商银行', '622588': '招商银行', '622589': '招商银行',
  '621799': '中国邮政储蓄银行', '622150': '中国邮政储蓄银行', '955100': '中国邮政储蓄银行',
  '622615': '中国民生银行', '621619': '中国民生银行', '622690': '中信银行', '621768': '中信银行',
  '622516': '上海浦东发展银行', '622517': '上海浦东发展银行', '622909': '兴业银行', '622910': '兴业银行',
  '622630': '华夏银行', '622631': '华夏银行', '622988': '平安银行', '622989': '平安银行',
  '622555': '广发银行', '622556': '广发银行',
}

export function isRegisteredBankCardStatus(status: string) {
  return (REGISTERED_BANK_CARD_STATUSES as readonly string[]).includes(status)
}

export function bankNameSuggestion(cardNumber: string) {
  const digits = cardNumber.replace(/\D/g, '')
  const prefix = digits.slice(0, 6)
  if (prefix.length !== 6 || AMBIGUOUS_BANK_BIN_PREFIXES.has(prefix)) return ''
  return BANK_BIN_SUGGESTIONS[prefix] || ''
}

export function luhnCheckCardNumber(cardNumber: string) {
  const digits = cardNumber.replace(/\D/g, '')
  if (digits.length < 12 || digits.length > 19) return false
  let sum = 0
  for (let index = 0; index < digits.length; index += 1) {
    let digit = Number(digits[digits.length - 1 - index])
    if (index % 2 === 1) {
      digit *= 2
      if (digit > 9) digit -= 9
    }
    sum += digit
  }
  return sum % 10 === 0
}
