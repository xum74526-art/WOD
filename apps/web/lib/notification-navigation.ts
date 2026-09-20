const ORDER_ACTION = /^\/pages\/order\/detail\?id=([1-9][0-9]*)$/;
const ASSET_ACTION = /^\/pages\/asset\/detail\?id=([1-9][0-9]*)$/;
const UNSAFE_ACTION_CHARACTERS = /[\u0000-\u001f\u007f\\]/;

function positiveSafeInteger(value: string): number | null {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/**
 * Maps the small, trusted set of mobile notification targets onto Web routes.
 * Matching the raw value is intentional: URL parsing would normalize some
 * encoded, traversal, or authority-like inputs before the allowlist check.
 */
export function notificationActionPath(value: unknown): string | null {
  if (typeof value !== "string" || UNSAFE_ACTION_CHARACTERS.test(value)) return null;

  if (value === "/pages/supplier/orders") return "/supplier/orders";
  if (value === "/pages/revenue/index") return "/account/revenue";
  if (value === "/pages/wallet/index") return "/account/wallet";

  const orderMatch = ORDER_ACTION.exec(value);
  if (orderMatch?.[0] === value) {
    const orderId = positiveSafeInteger(orderMatch[1]);
    return orderId === null ? null : `/account/orders?order=${orderId}`;
  }

  const assetMatch = ASSET_ACTION.exec(value);
  if (assetMatch?.[0] === value) {
    const assetId = positiveSafeInteger(assetMatch[1]);
    return assetId === null ? null : `/account/assets/${assetId}`;
  }

  return null;
}
