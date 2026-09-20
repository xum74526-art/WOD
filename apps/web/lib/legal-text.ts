import { toTraditionalChinese } from "./traditional-chinese.ts";

export const LEGAL_VERSION = "1.3";
export const LEGAL_EFFECTIVE_DATE = "2026-09-20";
export const LEGAL_OPERATOR = "锆芯期算人工智能科技（上海）有限公司";
export const LEGAL_OPERATOR_ADDRESS = "上海市浦东新区川南奉公路5058号3幢一层（集中登记地）";
export const LEGAL_ICP_FILING = "沪ICP备2026046279号-1";

const protectedLegalValues = [LEGAL_OPERATOR, LEGAL_OPERATOR_ADDRESS, LEGAL_ICP_FILING] as const;

export function toTraditionalLegalText(value: string): string {
  let converted = toTraditionalChinese(value);
  for (const legalValue of protectedLegalValues) {
    converted = converted.replaceAll(toTraditionalChinese(legalValue), legalValue);
  }
  return converted;
}
