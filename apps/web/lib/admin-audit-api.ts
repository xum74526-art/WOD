import { apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";
import type { AuditPlatform } from "@/lib/mobile-finance-api";
import type { MobileBuyQuote, MobileBuyRequestDeal, MobileBuyRequestEvent } from "@/lib/mobile-buy-request-api";

export type AdminCounts = { users: number; orders: number; recharge_orders: number; verifications: number; bank_cards: number; withdrawals: number };
export type AdminOverview = { created_platform: AuditPlatform | null; counts: AdminCounts; by_platform: Array<{ created_platform: AuditPlatform; counts: AdminCounts }> };
export type AdminUserItem = {
  id: number;
  username: string;
  phone_masked: string | null;
  phone_bound: boolean;
  role: string;
  supplier_status: string;
  kai_identity_bound: boolean;
  account_status: "active" | "suspended" | "deleting" | "deleted" | string;
  password_set: boolean;
  recovery_email_verified: boolean;
  created_platform: AuditPlatform;
  created_at: string;
};
export type AdminUserActionKind = "send_password_reset" | "freeze" | "unfreeze" | "delete";
export type AdminUserAction = {
  id: number;
  actor_user_id: number;
  target_user_id: number;
  action: AdminUserActionKind;
  reason: string;
  previous_status: string;
  new_status: string;
  result_code: string;
  created_at: string | null;
};
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
export type AdminRechargeItem = {
  id: number;
  order_no: string;
  user: { id: number; username: string | null };
  provider: string;
  provider_trade_no: string | null;
  client_request_id: string | null;
  channel: string | null;
  status: string;
  provider_status: string | null;
  failure_reason: string | null;
  amount_cny: number;
  card_hours: number;
  card_hour_rate: number;
  created_platform: AuditPlatform;
  last_modified_platform: AuditPlatform | "system";
  expires_at: string | null;
  paid_at: string | null;
  credited_at: string | null;
  last_reconciled_at: string | null;
  reconcile_attempts: number;
  created_at: string;
  updated_at: string;
};
export type AdminPaymentEvent = {
  id: number;
  payment_order_id: number;
  event_type: string;
  actor_type: string;
  actor_user_id: number | null;
  source: string;
  from_status: string | null;
  to_status: string | null;
  detail: Record<string, string | number | boolean | null> | null;
  created_at: string;
};
export type AdminPaymentRefund = {
  id: number;
  refund_no: string;
  payment_order_id: number;
  actor_user_id: number;
  client_request_id: string;
  amount_cny: number;
  card_hours: number;
  status: string;
  wallet_hold_status: string;
  previous_payment_status: string;
  reason: string;
  provider_code: string | null;
  provider_message: string | null;
  resolution_note: string | null;
  attempt_count: number;
  requested_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
};
export type AdminPaymentRefundRequest = {
  id: number;
  request_no: string;
  payment_order_id: number;
  order_no: string | null;
  payment_status: string | null;
  user: { id: number; username: string | null };
  client_request_id: string;
  amount_cny: number;
  card_hours: number;
  status: string;
  reason: string;
  created_platform: AuditPlatform;
  reviewed_by: number | null;
  review_note: string | null;
  reviewed_at: string | null;
  payment_refund: AdminPaymentRefund | null;
  created_at: string;
  updated_at: string;
};
export type AdminRechargeDetail = {
  order: AdminRechargeItem;
  events: AdminPaymentEvent[];
  refund: AdminPaymentRefund | null;
  refund_request: AdminPaymentRefundRequest | null;
};
export type AdminPaymentReviewResult = { order_id: number; status: string; credited: boolean } | AdminPaymentRefund;
export type AdminPaymentReviewInput =
  | { action: "credit"; note: string }
  | { action: "refund"; note: string; client_request_id: string };
export type AdminBuyRequestItem = {
  id: number;
  user_id: number;
  buyer_name: string;
  request_type: "online" | "offline";
  gpu_model: string;
  gpu_variant: string | null;
  quantity: number;
  gpu_hours: number | null;
  currency: string;
  region: string | null;
  billing_mode: string | null;
  requirements: Record<string, unknown>;
  contact: string | null;
  phone: string | null;
  status: string;
  quote_count: number;
  targeted_supplier_id: number | null;
  target_supplier?: { id: number; company_name: string | null } | null;
  expires_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  deal?: MobileBuyRequestDeal | null;
};
export type AdminBuyRequestDetail = { request: AdminBuyRequestItem; quotes: MobileBuyQuote[]; deal?: MobileBuyRequestDeal | null; events?: MobileBuyRequestEvent[] };
export type AdminBuyRequestCredential = { host: string; port: number; username: string; auth_type: "password" | "private_key"; secret: string; note?: string | null; fingerprint?: string | null; version?: number | null; status?: string | null; created_at?: string | null; updated_at?: string | null };
export type AdminPage<T> = { total: number; page: number; page_size: number; items: T[] };
export type AdminNotificationBroadcast = {
  id: number;
  client_request_id: string;
  actor_user_id: number;
  title: string;
  content: string;
  title_en: string | null;
  content_en: string | null;
  notification_type: "major_announcement" | "system" | "order" | "device" | "revenue" | "wallet";
  action_url: string | null;
  audience: "all_active" | string;
  status: "processing" | "completed" | string;
  recipient_count: number;
  created_at: string | null;
  completed_at: string | null;
};
export type AdminNotificationBroadcastInput = {
  client_request_id: string;
  title: string;
  content: string;
  title_en?: string | null;
  content_en?: string | null;
  notification_type: AdminNotificationBroadcast["notification_type"];
  action_url?: string | null;
};

function query(input: { platform?: AuditPlatform; keyword?: string; status?: string; orderNo?: string; requestNo?: string; requestType?: string; page?: number; pageSize?: number }) {
  const params = new URLSearchParams({ page: String(input.page ?? 1), page_size: String(input.pageSize ?? 100) });
  if (input.platform) params.set("platform", input.platform);
  if (input.keyword?.trim()) params.set("keyword", input.keyword.trim());
  if (input.status?.trim()) params.set("status", input.status.trim());
  if (input.orderNo?.trim()) params.set("order_no", input.orderNo.trim());
  if (input.requestNo?.trim()) params.set("request_no", input.requestNo.trim());
  if (input.requestType?.trim()) params.set("request_type", input.requestType.trim());
  return `?${params.toString()}`;
}

export function getAdminOverview(platform?: AuditPlatform) {
  const suffix = platform ? `?platform=${encodeURIComponent(platform)}` : "";
  return apiRequest<AdminOverview>(canonicalApiPath(`/admin/overview${suffix}`));
}

export function listAdminNotificationBroadcasts(input: { page?: number; pageSize?: number } = {}) {
  const params = new URLSearchParams({
    page: String(input.page ?? 1),
    page_size: String(input.pageSize ?? 20),
  });
  return apiRequest<AdminPage<AdminNotificationBroadcast>>(
    canonicalApiPath(`/admin/notification-broadcasts?${params.toString()}`),
  );
}

export function createAdminNotificationBroadcast(input: AdminNotificationBroadcastInput) {
  return apiRequest<AdminNotificationBroadcast>(canonicalApiPath("/admin/notification-broadcasts"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminUsers(input: { platform?: AuditPlatform; keyword?: string; status?: string; page?: number; pageSize?: number } = {}) {
  return apiRequest<AdminPage<AdminUserItem>>(canonicalApiPath(`/admin/users${query(input)}`));
}

export function manageAdminUser(id: number, input: {
  action: AdminUserActionKind;
  client_request_id: string;
  reason: string;
  confirm_username?: string;
}) {
  return apiRequest<AdminUserAction>(canonicalApiPath(`/admin/users/${id}/actions`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminUserActions(id: number, input: { page?: number; pageSize?: number } = {}) {
  const params = new URLSearchParams({
    page: String(input.page ?? 1),
    page_size: String(input.pageSize ?? 20),
  });
  return apiRequest<AdminPage<AdminUserAction>>(
    canonicalApiPath(`/admin/users/${id}/actions?${params.toString()}`),
  );
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

export function listAdminRechargeOrders(input: { platform?: AuditPlatform; status?: string; orderNo?: string; page?: number; pageSize?: number } = {}) {
  return apiRequest<AdminPage<AdminRechargeItem>>(canonicalApiPath(`/admin/recharge-orders${query(input)}`));
}

export function getAdminRechargeOrder(id: number) {
  return apiRequest<AdminRechargeDetail>(canonicalApiPath(`/admin/recharge-orders/${id}`));
}

export function reviewAdminRechargeOrder(id: number, input: AdminPaymentReviewInput) {
  return apiRequest<AdminPaymentReviewResult>(canonicalApiPath(`/admin/recharge-orders/${id}/review`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function createAdminPaymentRefund(id: number, input: { client_request_id: string; reason: string }) {
  return apiRequest<AdminPaymentRefund>(canonicalApiPath(`/admin/recharge-orders/${id}/refunds`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminPaymentRefunds(input: { status?: string; page?: number; pageSize?: number } = {}) {
  return apiRequest<AdminPage<AdminPaymentRefund>>(canonicalApiPath(`/admin/payment-refunds${query(input)}`));
}

export function getAdminPaymentRefund(id: number) {
  return apiRequest<AdminPaymentRefund>(canonicalApiPath(`/admin/payment-refunds/${id}`));
}

export function resolveAdminPaymentRefund(id: number, input: { outcome: "succeeded" | "failed"; note: string }) {
  return apiRequest<AdminPaymentRefund>(canonicalApiPath(`/admin/payment-refunds/${id}/resolve`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminPaymentRefundRequests(input: { platform?: AuditPlatform; status?: string; requestNo?: string; orderNo?: string; page?: number; pageSize?: number } = {}) {
  return apiRequest<AdminPage<AdminPaymentRefundRequest>>(canonicalApiPath(`/admin/payment-refund-requests${query(input)}`));
}

export function getAdminPaymentRefundRequest(id: number) {
  return apiRequest<AdminPaymentRefundRequest>(canonicalApiPath(`/admin/payment-refund-requests/${id}`));
}

export function reviewAdminPaymentRefundRequest(id: number, input: { action: "approve" | "reject"; note: string }) {
  return apiRequest<AdminPaymentRefundRequest>(canonicalApiPath(`/admin/payment-refund-requests/${id}/review`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminBuyRequests(input: { status?: string; requestType?: "online" | "offline"; keyword?: string; page?: number; pageSize?: number } = {}) {
  return apiRequest<AdminPage<AdminBuyRequestItem>>(canonicalApiPath(`/admin/buy-requests${query(input)}`));
}

export function getAdminBuyRequest(id: number) {
  return apiRequest<AdminBuyRequestDetail>(canonicalApiPath(`/admin/buy-requests/${id}`));
}

export function approveAdminBuyRequestDeal(requestId: number, dealId: number) {
  return apiRequest<MobileBuyRequestDeal>(canonicalApiPath(`/admin/buy-requests/${requestId}/deals/${dealId}/approve`), { method: "POST" });
}

export function rejectAdminBuyRequestDeal(requestId: number, dealId: number, reason: string) {
  return apiRequest<MobileBuyRequestDeal>(canonicalApiPath(`/admin/buy-requests/${requestId}/deals/${dealId}/reject`), { method: "POST", body: JSON.stringify({ reason }) });
}

export function getAdminBuyRequestCredential(requestId: number, dealId: number) {
  return apiRequest<AdminBuyRequestCredential>(canonicalApiPath(`/admin/buy-requests/${requestId}/deals/${dealId}/credential`));
}

export function releaseAdminBuyRequestCredential(requestId: number, dealId: number) {
  return apiRequest<MobileBuyRequestDeal>(canonicalApiPath(`/admin/buy-requests/${requestId}/deals/${dealId}/credential/release`), { method: "POST" });
}

export function rejectAdminBuyRequestCredential(requestId: number, dealId: number, reason: string) {
  return apiRequest<MobileBuyRequestDeal>(canonicalApiPath(`/admin/buy-requests/${requestId}/deals/${dealId}/credential/reject`), { method: "POST", body: JSON.stringify({ reason }) });
}
