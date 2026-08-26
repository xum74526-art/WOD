import { apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";
import type { AuditPlatform } from "@/lib/mobile-finance-api";

export type AdminCounts = { users: number; orders: number; recharge_orders: number; verifications: number; bank_cards: number; withdrawals: number };
export type AdminOverview = { created_platform: AuditPlatform | null; counts: AdminCounts; by_platform: Array<{ created_platform: AuditPlatform; counts: AdminCounts }> };
export type AdminUserItem = { id: number; username: string; phone_masked: string | null; phone_bound: boolean; role: string; supplier_status: string; kai_identity_bound: boolean; created_platform: AuditPlatform; created_at: string };
export type AdminOrderItem = {
  id: number;
  order_no: string;
  user: { id: number; username: string | null };
  product: { id: number; name: string | null; gpu_model: string | null };
  quantity: number;
  purchase_hours: number | null;
  cycle_days: number | null;
  purchase_type: string;
  amount_card_hours: number;
  status: string;
  created_platform: AuditPlatform;
  last_modified_platform: AuditPlatform;
  start_at: string | null;
  end_at: string | null;
  created_at: string;
  updated_at?: string;
  dispute_reason?: string | null;
  disputed_at?: string | null;
  dispute_due_at?: string | null;
  dispute_resolution?: string | null;
  dispute_resolution_note?: string | null;
  dispute_resolved_at?: string | null;
  seller_type?: "kai_self_operated" | "merchant";
  seller_name?: string | null;
  fulfillment_mode?: "platform_manual" | "merchant_manual";
  delivered_at?: string | null;
  confirmation_due_at?: string | null;
  ssh_info_present?: boolean | null;
  ssh_fingerprint?: string | null;
  ssh_info_fingerprint?: string | null;
  product_snapshot?: {
    id?: number | null;
    name?: string | null;
    product_name?: string | null;
    gpu_model?: string | null;
    memory?: string | null;
    region?: string | null;
    region_code?: string | null;
    region_name?: string | null;
    city?: string | null;
    quantity?: number | null;
    purchase_hours?: number | null;
    unit_price_card_hours?: number | string | null;
    confirmed_unit_price_card_hours?: number | string | null;
  } | null;
};
export type AdminRechargeItem = { id: number; order_no: string; user: { id: number; username: string | null }; provider: string; provider_trade_no: string | null; channel: string; status: string; amount_cny: number; card_hours: number; card_hour_rate: number; created_platform: AuditPlatform; last_modified_platform: AuditPlatform; expires_at: string | null; paid_at: string | null; credited_at: string | null; created_at: string; updated_at: string };
export type AdminPage<T> = { total: number; page: number; page_size: number; items: T[] };

function query(input: { platform?: AuditPlatform; keyword?: string; status?: string; orderNo?: string; page?: number; pageSize?: number }) {
  const params = new URLSearchParams({ page: String(input.page ?? 1), page_size: String(input.pageSize ?? 100) });
  if (input.platform) params.set("platform", input.platform);
  if (input.keyword?.trim()) params.set("keyword", input.keyword.trim());
  if (input.status?.trim()) params.set("status", input.status.trim());
  if (input.orderNo?.trim()) params.set("order_no", input.orderNo.trim());
  return `?${params.toString()}`;
}

export function getAdminOverview(platform?: AuditPlatform) {
  const suffix = platform ? `?platform=${encodeURIComponent(platform)}` : "";
  return apiRequest<AdminOverview>(canonicalApiPath(`/admin/overview${suffix}`));
}

export function listAdminUsers(input: { platform?: AuditPlatform; keyword?: string } = {}) {
  return apiRequest<AdminPage<AdminUserItem>>(canonicalApiPath(`/admin/users${query(input)}`));
}

export function listAdminOrders(input: { platform?: AuditPlatform; status?: string; orderNo?: string; page?: number; pageSize?: number } = {}) {
  return apiRequest<AdminPage<AdminOrderItem>>(canonicalApiPath(`/admin/orders${query(input)}`));
}

export function resolveAdminOrderDispute(id: number, input: { action: "refund" | "release"; note: string }) {
  return apiRequest<AdminOrderItem>(canonicalApiPath(`/orders/${id}/dispute/resolve`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminRechargeOrders(input: { platform?: AuditPlatform; status?: string; orderNo?: string } = {}) {
  return apiRequest<AdminPage<AdminRechargeItem>>(canonicalApiPath(`/admin/recharge-orders${query(input)}`));
}
