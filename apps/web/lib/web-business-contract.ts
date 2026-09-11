export const KAI_REALTIME_SOURCE = "kai" as const;

export function kaiPricingQuery(input: Record<string, string | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(input)) if (value) params.set(key, value);
  params.set("sources", KAI_REALTIME_SOURCE);
  return params.toString();
}

export function hourlyOrderBody(hours: number, clientRequestId: string) {
  if (!Number.isInteger(hours) || hours < 1 || hours > 720) throw new Error("购买时长必须是 1 至 720 的整数小时");
  if (clientRequestId.length < 12 || clientRequestId.length > 64) throw new Error("订单请求编号长度无效");
  return { hours, client_request_id: clientRequestId };
}

export function webRequestId(kind: "order" | "renew" | "buy-request", uuid: string) {
  return `web-${kind}-${uuid}`.slice(0, 64);
}

export type DirectOrderIntent = Readonly<{
  signature: string;
  requestId: string;
}>;

export function directOrderIntentSignature(input: {
  product_id: number;
  quantity: number;
  hours: number;
  purchase_type: "usage";
  expected_unit_price_card_hours: number;
}) {
  return JSON.stringify([
    input.product_id,
    input.quantity,
    input.hours,
    input.purchase_type,
    input.expected_unit_price_card_hours,
  ]);
}

export function ensureDirectOrderIntent(
  current: DirectOrderIntent | null,
  signature: string,
  createUuid: () => string,
): DirectOrderIntent {
  if (current?.signature === signature) return current;
  return { signature, requestId: webRequestId("order", createUuid()) };
}

export type BuyRequestIntent = Readonly<{
  signature: string;
  requestId: string;
}>;

export function buyRequestIntentSignature(input: Readonly<Record<string, unknown>>) {
  return JSON.stringify(input);
}

export function ensureBuyRequestIntent(
  current: BuyRequestIntent | null,
  signature: string,
  createUuid: () => string,
): BuyRequestIntent {
  if (current?.signature === signature) return current;
  return { signature, requestId: webRequestId("buy-request", createUuid()) };
}

export function normalizeBuyRequestContactPhone(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length > 32 || !/^[+0-9 ()-]+$/.test(trimmed)) return null;
  const normalized = trimmed.replace(/[ ()-]/g, "");
  return /^(?:[0-9]{6,20}|\+[1-9][0-9]{5,14})$/.test(normalized) ? normalized : null;
}
