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

export function webRequestId(kind: "order" | "renew", uuid: string) {
  return `web-${kind}-${uuid}`.slice(0, 64);
}
