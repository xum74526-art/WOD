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

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export function legacyRequestCreateHref(searchParams: RequestSearchParams = {}) {
  const query = new URLSearchParams({ create: "1" });
  for (const key of REQUEST_PREFILL_KEYS) {
    const value = first(searchParams[key]);
    if (!value) continue;
    if (POSITIVE_NUMBER_PREFILL_KEYS.has(key)) {
      const number = Number(value);
      if (!Number.isFinite(number) || number <= 0) continue;
    }
    query.set(key, value);
  }
  return `/account/requests?${query.toString()}`;
}
