export type RequestSearchParams = Record<string, string | string[] | undefined>;

// Bridges bookmarks created before Web moved request creation into the authenticated
// workspace. Remove this whitelist once supported releases and access logs no longer
// reference `/requests/new`; its regression coverage lives in request-navigation.test.ts.
const REQUEST_PREFILL_KEYS = [
  "product_id",
  "supplier_id",
  "source",
  "product_name",
  "seller_name",
  "gpu_model",
  "gpu_variant",
  "quantity",
  "gpu_hours",
  "region",
] as const;

const POSITIVE_NUMBER_PREFILL_KEYS = new Set<string>(["product_id", "supplier_id", "quantity", "gpu_hours"]);

const REGION_REQUIREMENT_LABELS: Record<string, string> = {
  north_china: "华北",
  east_china: "华东",
  central_china: "华中",
  south_china: "华南",
  northeast_china: "东北",
  northwest_china: "西北",
  southwest_china: "西南",
  china_unspecified: "中国大陆",
  asia_pacific: "亚太",
  north_america: "北美",
  europe: "欧洲",
  middle_east: "中东",
  south_america: "南美",
  africa: "非洲",
};

const NON_SPECIFIC_REGION_KEYS = new Set([
  "global_unspecified",
  "global/undisclosed",
  "global",
  "undisclosed",
  "unspecified",
  "全球/未披露",
  "全球/未公开",
  "全球",
  "未披露",
  "未标注",
  "地区待确认",
  "-",
  "—",
]);

export type RequestCreatePrefill = Partial<Record<(typeof REQUEST_PREFILL_KEYS)[number], string | number | null>>;

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function regionRequirementKey(value: string) {
  return value.trim().toLowerCase().replace(/／/g, "/").replace(/\s+/g, "");
}

export function normalizeInquiryRegionRequirement(value: string | number | null | undefined) {
  const source = String(value ?? "").trim();
  const key = regionRequirementKey(source);
  if (!key || NON_SPECIFIC_REGION_KEYS.has(key)) return "";
  return REGION_REQUIREMENT_LABELS[key] ?? source;
}

export function requestCreateHref(prefill: RequestCreatePrefill = {}) {
  const query = new URLSearchParams({ create: "1" });
  for (const key of REQUEST_PREFILL_KEYS) {
    const rawValue = prefill[key];
    if (rawValue == null) continue;
    const value = key === "region"
      ? normalizeInquiryRegionRequirement(rawValue)
      : String(rawValue).trim();
    if (!value) continue;
    if (POSITIVE_NUMBER_PREFILL_KEYS.has(key)) {
      const number = Number(value);
      if (!Number.isFinite(number) || number <= 0) continue;
    }
    query.set(key, value);
  }
  return `/account/requests?${query.toString()}`;
}

export function legacyRequestCreateHref(searchParams: RequestSearchParams = {}) {
  const prefill: RequestCreatePrefill = {};
  for (const key of REQUEST_PREFILL_KEYS) {
    const value = first(searchParams[key]);
    if (value) prefill[key] = value;
  }
  return requestCreateHref(prefill);
}
