import { apiEnvelopeRequest, apiRequest, publicApiEnvelopeRequest, type ApiEnvelope } from "@/lib/api";
import { hourlyOrderBody } from "@/lib/web-business-contract";
import type { ProductPurchaseType } from "@/lib/product-purchase";

export type PageMeta = { page: number; page_size: number; total: number; total_pages: number };
export type OrderStatus = "paid" | "delivering" | "disputed" | "completed" | "running" | "done" | "canceled";

export type SupplierApplication = {
  id: number;
  identity_verified: boolean;
  company_name: string;
  contact_name: string;
  contact_phone: string;
  region: string | null;
  description: string | null;
  status: "pending" | "approved" | "rejected";
  review_note: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  reviewed_by: number | null;
  applicant: { id: number; display_name: string; email: string | null; role: string; status: string; created_at: string };
};

export type OrderEvent = {
  id: number;
  actor_role: string;
  event_type: string;
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  payload: { note?: string; [key: string]: unknown };
  created_at: string;
};

export type Order = {
  id: number;
  order_no: string;
  status: OrderStatus;
  buyer_id: number;
  supplier_id: number;
  buy_request_id: number | null;
  accepted_quote_id: number | null;
  product_id: number | null;
  order_source: "quote" | "direct";
  environment: "live" | "sandbox";
  payment_status: "not_required" | "pending" | "paid" | "refunded";
  duration_hours: number | null;
  amount: string;
  currency: string;
  price_unit: string;
  quantity: number;
  purchase_type?: "usage" | "holding";
  coupon_id?: number | null;
  coupon_discount?: number;
  payable_amount_card_hours?: number;
  purchase_hours?: number | null;
  market_source?: "kai" | "wod" | null;
  cycle_days?: number | null;
  end_at?: string | null;
  remaining_days?: number;
  remaining_hours?: number | null;
  created_platform?: string;
  last_modified_platform?: string;
  snapshot: {
    payment_mode?: "local_placeholder" | "pingxx";
    pricing_semantics?: string;
    request?: { request_no: string; title: string; gpu_model: string; gpu_quantity: number; region_codes?: string[]; delivery_mode?: string; expected_start_at?: string | null; expected_duration_hours?: number | null; requirements?: string };
    quote?: { quote_no: string; delivery_time_hours?: number | null; service_description?: string };
    supplier?: { display_name?: string; company_name?: string | null };
    product?: { resource_no: string; name: string; gpu_model: string; region: string; unit_price: string };
  };
  buyer_confirmed_at: string | null;
  supplier_confirmed_at: string | null;
  confirmed_at: string | null;
  delivery_started_at: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  delivery_note: string | null;
  fulfillment_status?: string | null;
  seller_type?: "kai_self_operated" | "merchant";
  seller_name?: string;
  fulfillment_mode?: "platform_manual" | "merchant_manual";
  delivery_due_at: string | null;
  confirmation_due_at: string | null;
  disputed_at: string | null;
  dispute_due_at: string | null;
  dispute_reason: string | null;
  dispute_resolution: "refund" | "release" | string | null;
  dispute_resolution_note: string | null;
  dispute_resolved_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  buyer: { display_name: string };
  supplier: { display_name: string; company_name: string | null };
  available_actions: Array<"confirm" | "cancel" | "dispute" | "start_delivery" | "mark_delivered" | "complete" | "renew">;
  events?: OrderEvent[];
};

export type PublicProduct = {
  id: number;
  supplier_id: number | null;
  supplier_name: string | null;
  supplier_rating: number | null;
  supplier_order_count: number | null;
  seller_type: "kai_self_operated" | "merchant";
  seller_name: string;
  fulfillment_mode: "platform_manual" | "merchant_manual";
  resource_claim_source: "kai_published" | "merchant_declared";
  assurance_label: string;
  assurance_description: string;
  name: string;
  gpu_model: string;
  memory: string;
  gpu_memory_gb: number;
  region: string;
  description: string;
  cpu_cores: number | null;
  ram_gb: number | null;
  disk_gb: number | null;
  bandwidth_mbps: number | null;
  unit_price_ch: number;
  price: { amount: string; currency: string; unit: string };
  total_quantity: number;
  available_quantity: number;
  source_name: string | null;
  source_observed_at: string | null;
  inquiry_available: boolean;
  interaction_mode: "direct_trade" | "matchmaking" | "history_only";
  purchasable: boolean;
  purchase_unavailable_reason: string | null;
  cycle: number[];
  purchase_unit: "hour" | "day" | string;
  purchase_hour_options: number[];
  billing_unit: string;
  image_url: string | null;
  market_source: "kai" | "wod";
};

export type SshKey = {
  id: number;
  name: string;
  algorithm: string;
  fingerprint: string;
  public_key_preview: string;
  status: "active" | "revoked";
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
};

function queryString(values: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") query.set(key, String(value)); });
  const text = query.toString();
  return text ? `?${text}` : "";
}

export function listOrders(scope: "account" | "supplier", status?: string) { return apiEnvelopeRequest<Order[], PageMeta>(`/api/v1/${scope}/orders${queryString({ status })}`); }
export function getOrder(scope: "account" | "supplier", id: number) { return apiRequest<Order>(`/api/v1/${scope}/orders/${id}`); }
export function confirmOrder(scope: "account" | "supplier", id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/${scope}/orders/${id}/confirm`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function cancelOrder(scope: "account" | "supplier", id: number, version: number, reason: string) { return apiRequest<Order>(`/api/v1/${scope}/orders/${id}/cancel`, { method: "POST", body: JSON.stringify({ version, reason }) }); }
export function startOrderDelivery(id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/supplier/orders/${id}/start-delivery`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function markOrderDelivered(id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/supplier/orders/${id}/mark-delivered`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function completeOrder(id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/account/orders/${id}/complete`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function disputeOrder(id: number, reason: string) { return apiRequest<Order>(`/api/v1/account/orders/${id}/dispute`, { method: "POST", body: JSON.stringify({ reason }) }); }
export function renewOrder(id: number, hours: number, clientRequestId: string) {
  return apiRequest<Order>(`/api/v1/account/orders/${id}/renew`, {
    method: "POST",
    headers: { "Idempotency-Key": clientRequestId },
    body: JSON.stringify(hourlyOrderBody(hours, clientRequestId)),
  });
}
export function createDirectOrder(input: { product_id: number; quantity: number; hours: number; purchase_type: ProductPurchaseType; expected_unit_price_card_hours: number; coupon_id?: number }, clientRequestId: string) {
  return apiRequest<{ order: Order }>("/api/v1/account/orders/direct", {
    method: "POST",
    headers: { "Idempotency-Key": clientRequestId },
    body: JSON.stringify({ ...input, ...hourlyOrderBody(input.hours, clientRequestId) }),
  });
}

export function listSshKeys() { return apiEnvelopeRequest<SshKey[], { private_keys_accepted: false; usage: "server_login_only" }>("/api/v1/account/ssh-keys"); }
export function createSshKey(input: { name: string; public_key: string }) { return apiRequest<SshKey>("/api/v1/account/ssh-keys", { method: "POST", body: JSON.stringify(input) }); }
export function updateSshKey(id: number, input: { version: number; name: string }) { return apiRequest<SshKey>(`/api/v1/account/ssh-keys/${id}`, { method: "PATCH", body: JSON.stringify(input) }); }
export function revokeSshKey(id: number, version: number) { return apiRequest<SshKey>(`/api/v1/account/ssh-keys/${id}?version=${version}`, { method: "DELETE" }); }

export function listPublicProducts(marketSource?: "kai" | "wod", page = 1, pageSize = 24) {
  return publicApiEnvelopeRequest<PublicProduct[], PageMeta & { count: number; real_data_only: boolean; server_rental_available: boolean; payment_mode: "local_placeholder" | "pingxx" | "mobile_wallet" }>(
    `/api/v1/public/products${queryString({ market_source: marketSource, page, page_size: pageSize })}`,
    15_000,
  );
}
export function getPublicProduct(id: number) { return apiEnvelopeRequest<PublicProduct, { real_data_only: boolean; server_rental_available: boolean; payment_mode: "local_placeholder" | "pingxx" }>(`/api/v1/public/products/${id}`); }

export function listSupplierApplications(filters: { status?: string; search?: string; page?: number; page_size?: number } = {}) { return apiEnvelopeRequest<SupplierApplication[], PageMeta>(`/api/v1/admin/supplier-applications${queryString(filters)}`); }
export function reviewSupplierApplication(id: number, action: "approve" | "reject", version: number, note: string) { return apiRequest<SupplierApplication>(`/api/v1/admin/supplier-applications/${id}/${action}`, { method: "POST", body: JSON.stringify({ version, note: note || (action === "reject" ? "资料不符合要求" : null) }) }); }

export type { ApiEnvelope };
