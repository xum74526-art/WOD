import type { KaiLocale } from "./language.ts";
import { toTraditionalChinese } from "./traditional-chinese.ts";

const supplierNames: Record<string, string> = {
  "北京智算中心": "Beijing Intelligent Computing Center",
  "成都西部算力": "Chengdu West Compute",
  "上海云算力": "Shanghai Cloud Compute",
  "西安智链科技": "Xi'an Intelligent Chain Technology",
  "第三方商家": "Third-party Merchant",
  "KAI 自营": "KAI Self-operated",
  "KAI自营": "KAI Self-operated",
  "KAI星算自营": "KAI Star Self-operated",
};

const regionNames: Record<string, string> = {
  "华北": "North China",
  "华东": "East China",
  "华中": "Central China",
  "华南": "South China",
  "东北": "Northeast China",
  "西北": "Northwest China",
  "西南": "Southwest China",
  "中国大陆": "Mainland China",
  "亚太": "Asia Pacific",
  "北美": "North America",
  "欧洲": "Europe",
  "中东": "Middle East",
  "南美": "South America",
  "非洲": "Africa",
  "海外": "Overseas",
  "全球/未披露": "Global / Undisclosed",
  "未披露": "Undisclosed",
  "未标注": "Not specified",
  north_china: "North China",
  east_china: "East China",
  central_china: "Central China",
  south_china: "South China",
  northeast_china: "Northeast China",
  northwest_china: "Northwest China",
  southwest_china: "Southwest China",
  china_unspecified: "Mainland China",
  asia_pacific: "Asia Pacific",
  north_america: "North America",
  europe: "Europe",
  middle_east: "Middle East",
  south_america: "South America",
  africa: "Africa",
  global_unspecified: "Global / Undisclosed",
};

export function localizeSupplierName(value: string | null | undefined, locale: KaiLocale) {
  const source = value?.trim() || "第三方商家";
  if (locale === "en") return supplierNames[source] ?? source;
  return locale === "zh-Hant" ? toTraditionalChinese(source) : source;
}

export function localizeMarketRegion(value: string | null | undefined, locale: KaiLocale) {
  const source = value?.trim() || "—";
  if (locale === "zh-Hant") return toTraditionalChinese(source);
  if (locale !== "en") return source;
  const normalized = source.replace(/\s*\/\s*/g, "/").toLowerCase();
  return regionNames[source] ?? regionNames[normalized] ?? source;
}

export function localizeMarketProductName(value: string, locale: KaiLocale) {
  if (locale === "zh-Hant") return toTraditionalChinese(value);
  if (locale !== "en") return value;
  return value
    .replace("独占训练节点", "Dedicated Training Node")
    .replace("错误型号资源", "Legacy Test Resource");
}
