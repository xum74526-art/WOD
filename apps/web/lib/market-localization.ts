import type { KaiLocale } from "@/components/locale-root";

const supplierNames: Record<string, string> = {
  "北京智算中心": "Beijing Intelligent Computing Center",
  "成都西部算力": "Chengdu West Compute",
  "上海云算力": "Shanghai Cloud Compute",
  "西安智链科技": "Xi'an Intelligent Chain Technology",
  "已审核商家": "Verified Supplier",
};

const regionNames: Record<string, string> = {
  "华北": "North China",
  "华东": "East China",
  "华南": "South China",
  "东北": "Northeast China",
  "西北": "Northwest China",
  "西南": "Southwest China",
  "海外": "Overseas",
};

export function localizeSupplierName(value: string | null | undefined, locale: KaiLocale) {
  const source = value?.trim() || "已审核商家";
  return locale === "en" ? supplierNames[source] ?? source : source;
}

export function localizeMarketRegion(value: string | null | undefined, locale: KaiLocale) {
  const source = value?.trim() || "—";
  return locale === "en" ? regionNames[source] ?? source : source;
}

export function localizeMarketProductName(value: string, locale: KaiLocale) {
  if (locale !== "en") return value;
  return value
    .replace("独占训练节点", "Dedicated Training Node")
    .replace("错误型号资源", "Legacy Test Resource");
}
