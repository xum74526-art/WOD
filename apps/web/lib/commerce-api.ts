import { apiEnvelopeRequest, apiRequest, publicApiEnvelopeRequest, type ApiEnvelope } from "@/lib/api";

export type PageMeta = { page: number; page_size: number; total: number; total_pages: number };
export type RequestStatus = "draft" | "reviewing" | "published" | "negotiating" | "matched" | "completed" | "closed" | "expired" | "rejected";
export type QuoteStatus = "draft" | "submitted" | "shortlisted" | "accepted" | "rejected" | "withdrawn" | "expired";
export type OrderStatus = "pending_confirmation" | "confirmed" | "delivering" | "delivered" | "completed" | "cancelled";
export type ResourceStatus = "draft" | "pending_review" | "approved" | "published" | "rejected" | "archived";
export type ReservationStatus = "reserved" | "allocated" | "released";

export type Money = { amount: string | null; currency: string; unit: string };
export type CloudDetails = {
  min_cpu_cores: number | null;
  min_ram_gb: number | null;
  min_disk_gb: number | null;
  min_download_mbps: number | null;
  public_ip_required: boolean;
  container_image: string | null;
  software_stack: string[];
  special_requirements: string | null;
};
export type BuyRequest = {
  id?: number;
  version?: number;
  request_no: string;
  request_type: "cloud_compute" | "offline_device";
  title: string;
  status: RequestStatus;
  visibility: "public" | "invited" | "private";
  gpu_model: string;
  min_gpu_memory_gb: number | null;
  gpu_quantity: number;
  region_codes: string[];
  delivery_mode: "remote" | "dedicated" | "negotiable";
  budget: Money;
  quote_deadline_at: string;
  expected_start_at: string | null;
  expected_duration_hours: number | null;
  requirements: string;
  published_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  cloud_details?: CloudDetails;
  contact?: { contact_name: string; visible_after: string } | null;
  events?: Array<{ event_type: string; from_status: string | null; to_status: string | null; created_at: string }>;
};

export type Quote = {
  id: number;
  resource_id: number | null;
  quote_no: string;
  buy_request_id: number;
  status: QuoteStatus;
  price: { amount: string; currency: string; unit: string };
  available_quantity: number;
  delivery_time_hours: number | null;
  valid_until: string;
  is_expired: boolean;
  service_description: string;
  buyer_note: string | null;
  submitted_at: string | null;
  accepted_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  supplier?: { id: number; display_name: string; company_name: string | null };
  request?: Pick<BuyRequest, "request_no" | "title" | "status" | "gpu_model" | "gpu_quantity" | "quote_deadline_at"> & { id: number };
};

export type SupplierApplication = {
  id: number;
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
  cycle_days?: number;
  end_at?: string | null;
  remaining_days?: number;
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
  created_at: string;
  updated_at: string;
  version: number;
  buyer: { display_name: string };
  supplier: { display_name: string; company_name: string | null };
  available_actions: Array<"confirm" | "cancel" | "start_delivery" | "mark_delivered" | "complete" | "renew">;
  events?: OrderEvent[];
};

export type PublicProduct = {
  id: number;
  supplier_id?: number;
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
  server_online: boolean;
  purchasable: boolean;
  purchase_unavailable_reason: string | null;
  cycle: number[];
  image_url: string | null;
  market_source: string;
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

export type ServerLease = {
  id: number;
  lease_no: string;
  order_id: number;
  order_no: string;
  product_id: number;
  server_name: string;
  gpu_model: string;
  region: string;
  status: "pending_authorization" | "active" | "grace" | "expired" | "revoked" | "failed";
  duration_hours: number;
  amount: string;
  currency: string;
  ssh_key: { id: number; name: string; fingerprint: string };
  connection: { host: string; port: number; username: string; ssh_command: string } | null;
  starts_at: string | null;
  expires_at: string | null;
  grace_expires_at: string | null;
  authorized_at: string | null;
  access_revoked_at: string | null;
  failure_reason: string | null;
  created_at: string;
  version: number;
  renewable: boolean;
  payment_mode: "placeholder" | "local_placeholder" | "pingxx";
  payment?: RentalPayment;
};

export type RentalPayment = {
  payment_no: string;
  status: string;
  provider: "local_placeholder" | "pingxx" | string;
  checkout_url: string | null;
};

export type AgentHardware = {
  status: "pending" | "verified" | "mismatch" | "stale" | "unavailable";
  observed_at: string | null;
  verified_at: string | null;
  inventory_hash: string | null;
  stale_after_seconds: number;
  is_simulated: boolean;
  inventory: {
    collected_at?: string;
    source?: "host" | "docker" | "local_simulator";
    os_name?: string;
    os_version?: string;
    kernel_version?: string;
    cpu_model?: string;
    cpu_logical_cores?: number;
    memory_total_mb?: number;
    disk_total_gb?: number;
    disk_available_gb?: number;
    gpus?: Array<{ index: number; name: string; memory_total_mb: number; uuid?: string; driver_version?: string }>;
    collection_errors?: string[];
  };
  mismatches: Array<{ field: string; declared: unknown; detected: unknown; message: string }>;
};

export type AgentServices = {
  status: "pending" | "healthy" | "unhealthy" | "stale" | "unavailable";
  observed_at: string | null;
  checks: { ssh?: { reachable: boolean; port: number; error?: string | null } };
  stale_after_seconds: number;
  is_simulated: boolean;
};

export type Resource = {
  id: number;
  resource_no: string;
  name: string;
  gpu_model: string;
  gpu_memory_gb: number;
  memory: string;
  region: string;
  cpu_cores: number | null;
  ram_gb: number | null;
  disk_gb: number | null;
  bandwidth_mbps: number | null;
  description: string;
  price: { amount: string; currency: string; unit: string };
  total_quantity: number;
  reserved_quantity: number;
  available_quantity: number;
  status: ResourceStatus;
  review_note: string | null;
  reviewed_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  server: {
    id: number;
    server_no: string;
    public_host: string;
    ssh_port: number;
    ssh_username: string;
    status: "registered" | "online" | "offline" | "maintenance" | "retired";
    agent_mode: "local_simulator" | "mtls";
    agent_version: string | null;
    agent_device_id?: string | null;
    agent_platform?: "linux" | "windows" | null;
    agent_arch?: "amd64" | "arm64" | null;
    agent_hostname?: string | null;
    agent_enrolled_at?: string | null;
    last_seen_at: string | null;
    hardware?: AgentHardware;
    services?: AgentServices;
  } | null;
  supplier?: { display_name: string; company_name: string | null };
};

export type ResourceDetail = {
  resource: Resource;
  price_versions: Array<{ id: number; version: number; amount: string; currency: string; unit: string; change_note: string | null; created_at: string }>;
  events: Array<{ id: number; actor_role: string; event_type: string; from_status: ResourceStatus | null; to_status: ResourceStatus; note: string | null; created_at: string }>;
};

export type InventoryReservation = {
  id: number;
  reservation_no: string;
  product_id: number;
  resource_no: string;
  resource_name: string;
  order_id: number;
  order_no: string;
  quantity: number;
  status: ReservationStatus;
  release_reason: string | null;
  reserved_at: string;
  allocated_at: string | null;
  released_at: string | null;
  version: number;
};

function queryString(values: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") query.set(key, String(value)); });
  const text = query.toString();
  return text ? `?${text}` : "";
}

export function listPublicRequests(filters: { gpu_model?: string; region?: string; sort?: string } = {}) {
  return apiEnvelopeRequest<BuyRequest[], PageMeta>(`/api/v1/public/buy-requests${queryString(filters)}`);
}
export function getPublicRequest(requestNo: string) { return apiRequest<BuyRequest>(`/api/v1/public/buy-requests/${encodeURIComponent(requestNo)}`); }
export function listBuyerRequests(status?: string) { return apiEnvelopeRequest<BuyRequest[], PageMeta>(`/api/v1/account/buy-requests${queryString({ status })}`); }
export function getBuyerRequest(id: number) { return apiRequest<BuyRequest>(`/api/v1/account/buy-requests/${id}`); }
export function createBuyRequest(input: Record<string, unknown>) { return apiRequest<BuyRequest>("/api/v1/buy-requests", { method: "POST", body: JSON.stringify(input) }); }
export function updateBuyRequest(id: number, input: Record<string, unknown>) { return apiRequest<BuyRequest>(`/api/v1/account/buy-requests/${id}`, { method: "PATCH", body: JSON.stringify(input) }); }
export function deleteBuyRequest(id: number, version: number) { return apiRequest<{ deleted: boolean }>(`/api/v1/account/buy-requests/${id}?version=${version}`, { method: "DELETE" }); }
export function publishBuyRequest(id: number, version: number) { return apiRequest<BuyRequest>(`/api/v1/account/buy-requests/${id}/publish`, { method: "POST", body: JSON.stringify({ version }) }); }
export function closeBuyRequest(id: number, version: number, reason: string) { return apiRequest<BuyRequest>(`/api/v1/account/buy-requests/${id}/close`, { method: "POST", body: JSON.stringify({ version, reason }) }); }
export function extendBuyRequest(id: number, version: number, quoteDeadlineAt: string) { return apiRequest<BuyRequest>(`/api/v1/account/buy-requests/${id}/extend`, { method: "POST", body: JSON.stringify({ version, quote_deadline_at: quoteDeadlineAt }) }); }
export function listBuyerQuotes(id: number) { return apiEnvelopeRequest<{ request: Pick<BuyRequest, "request_no" | "title" | "status" | "gpu_model" | "gpu_quantity" | "quote_deadline_at"> & { id: number }; quotes: Quote[] }, PageMeta>(`/api/v1/account/buy-requests/${id}/quotes`); }
export function decideQuote(requestId: number, quoteId: number, action: "shortlist" | "reject", quoteVersion: number, note?: string) { return apiRequest<Quote>(`/api/v1/account/buy-requests/${requestId}/quotes/${quoteId}/${action}`, { method: "POST", body: JSON.stringify({ quote_version: quoteVersion, note: note || null }) }); }
export function acceptQuote(requestId: number, quoteId: number, requestVersion: number, quoteVersion: number, note?: string) { return apiRequest<{ id: number; order_no: string; status: string }>(`/api/v1/account/buy-requests/${requestId}/quotes/${quoteId}/accept`, { method: "POST", body: JSON.stringify({ request_version: requestVersion, quote_version: quoteVersion, note: note || null }) }); }

export function listSupplierRequests(filters: { gpu_model?: string; region?: string; sort?: string } = {}) { return apiEnvelopeRequest<(BuyRequest & { id: number })[], PageMeta>(`/api/v1/supplier/buy-requests${queryString(filters)}`); }
export function getSupplierRequest(id: number) { return apiRequest<{ request: BuyRequest; own_quotes: Quote[] }>(`/api/v1/supplier/buy-requests/${id}`); }
export function createSupplierQuote(requestId: number, input: Record<string, unknown>) { return apiRequest<Quote>(`/api/v1/supplier/buy-requests/${requestId}/quotes`, { method: "POST", body: JSON.stringify(input) }); }
export function updateSupplierQuote(id: number, input: Record<string, unknown>) { return apiRequest<Quote>(`/api/v1/supplier/quotes/${id}`, { method: "PATCH", body: JSON.stringify(input) }); }
export function listSupplierQuotes(status?: string) { return apiEnvelopeRequest<Quote[], PageMeta>(`/api/v1/supplier/quotes${queryString({ status })}`); }
export function submitSupplierQuote(id: number, version: number) { return apiRequest<Quote>(`/api/v1/supplier/quotes/${id}/submit`, { method: "POST", body: JSON.stringify({ version }) }); }
export function withdrawSupplierQuote(id: number, version: number, reason?: string) { return apiRequest<Quote>(`/api/v1/supplier/quotes/${id}/withdraw`, { method: "POST", body: JSON.stringify({ version, reason: reason || null }) }); }

export function listOrders(scope: "account" | "supplier", status?: string) { return apiEnvelopeRequest<Order[], PageMeta>(`/api/v1/${scope}/orders${queryString({ status })}`); }
export function getOrder(scope: "account" | "supplier", id: number) { return apiRequest<Order>(`/api/v1/${scope}/orders/${id}`); }
export function confirmOrder(scope: "account" | "supplier", id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/${scope}/orders/${id}/confirm`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function cancelOrder(scope: "account" | "supplier", id: number, version: number, reason: string) { return apiRequest<Order>(`/api/v1/${scope}/orders/${id}/cancel`, { method: "POST", body: JSON.stringify({ version, reason }) }); }
export function startOrderDelivery(id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/supplier/orders/${id}/start-delivery`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function markOrderDelivered(id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/supplier/orders/${id}/mark-delivered`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function completeOrder(id: number, version: number, note?: string) { return apiRequest<Order>(`/api/v1/account/orders/${id}/complete`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function renewOrder(id: number, cycleDays: number) { return apiRequest<Order>(`/api/v1/account/orders/${id}/renew`, { method: "POST", body: JSON.stringify({ cycle_days: cycleDays }) }); }
export function createDirectOrder(input: { product_id: number; quantity: number; cycle_days: number; purchase_type: "usage" | "holding" }) { return apiRequest<{ order: Order }>("/api/v1/account/orders/direct", { method: "POST", headers: { "Idempotency-Key": `wod-order-${crypto.randomUUID()}` }, body: JSON.stringify(input) }); }

export function listSshKeys() { return apiEnvelopeRequest<SshKey[], { private_keys_accepted: false; usage: "server_login_only" }>("/api/v1/account/ssh-keys"); }
export function createSshKey(input: { name: string; public_key: string }) { return apiRequest<SshKey>("/api/v1/account/ssh-keys", { method: "POST", body: JSON.stringify(input) }); }
export function updateSshKey(id: number, input: { version: number; name: string }) { return apiRequest<SshKey>(`/api/v1/account/ssh-keys/${id}`, { method: "PATCH", body: JSON.stringify(input) }); }
export function revokeSshKey(id: number, version: number) { return apiRequest<SshKey>(`/api/v1/account/ssh-keys/${id}?version=${version}`, { method: "DELETE" }); }
export function listServerLeases() { return apiEnvelopeRequest<ServerLease[], { renewal_grace_hours: number; payment_mode: "local_placeholder" | "pingxx" }>("/api/v1/account/leases"); }
export function renewServerLease(id: number, version: number, durationHours: number, paymentChannel = "alipay_pc_direct") { return apiRequest<ServerLease>(`/api/v1/account/leases/${id}/renew`, { method: "POST", headers: { "Idempotency-Key": `lease-renew-${crypto.randomUUID()}` }, body: JSON.stringify({ version, duration_hours: durationHours, payment_channel: paymentChannel }) }); }
export function listSupplierLeases() { return apiEnvelopeRequest<ServerLease[], { buyer_connection_details_exposed: false }>("/api/v1/supplier/leases"); }
export type AgentDownload = { platform: "linux" | "windows" | "docker"; arch: "amd64" | "arm64" | "multi"; filename: string; url: string; available: boolean; size_bytes: number | null; sha256: string | null };
export type AgentEnrollment = { server_id: number; server_no: string; enrollment_token: string; expires_at: string; api_base_url: string; linux_install_command: string; windows_install_command: string; docker_install_command: string; downloads: AgentDownload[]; security: { token_single_use: true; device_identity: string; transport: string; mtls_proxy_supported: true } };
export type SupplierServer = { id: number; server_no: string; product_id: number; product_name: string; resource_status: ResourceStatus; public_host: string; ssh_port: number; ssh_username_prefix: string; status: string; agent_mode: string; agent_version: string | null; agent_device_id: string | null; agent_platform: "linux" | "windows" | null; agent_arch: "amd64" | "arm64" | null; agent_hostname: string | null; agent_capabilities: string[]; agent_enrolled_at: string | null; last_seen_at: string | null; hardware?: AgentHardware; services?: AgentServices; created_at: string; version: number };
export function listSupplierServers() { return apiEnvelopeRequest<SupplierServer[], { production_agent_auth: string; local_agent_mode: "simulator" }>("/api/v1/supplier/servers"); }
export function createAgentEnrollment(serverId: number) { return apiRequest<AgentEnrollment>(`/api/v1/supplier/servers/${serverId}/enrollment-token`, { method: "POST", body: JSON.stringify({ expires_in_minutes: 20 }) }); }

export type RefundRequest = { id: number; refund_no: string; payment_no: string; order_id: number; order_no: string; purpose: "server_rental" | "lease_renewal"; buyer_id: number; supplier_id: number; amount: string; currency: string; provider: string; status: "requested" | "requires_manual" | "processing" | "completed" | "rejected"; reason_code: string; reason: string; provider_reference: string | null; admin_note: string | null; requested_at: string; processed_at: string | null; created_at: string; updated_at: string; version: number };
export function listAdminRefunds(status?: string) { return apiRequest<RefundRequest[]>(`/api/v1/admin/refunds${queryString({ status })}`); }
export function initiateAdminRefund(id: number, version: number, note?: string) { return apiRequest<RefundRequest>(`/api/v1/admin/refunds/${id}/initiate`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }

export type SupplierWithdrawal = {
  id: number;
  withdrawal_no: string;
  supplier_id: number;
  amount: string;
  currency: "CNY";
  status: "requested" | "approved" | "rejected" | "paid" | "cancelled";
  payout: { method: "manual_bank_transfer"; beneficiary_name: string; bank_name: string; account_no: string };
  review_note: string | null;
  payment_reference: string | null;
  requested_at: string;
  reviewed_at: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  supplier?: { display_name: string; email: string; company_name: string | null };
};
export type SupplierRevenue = {
  balances: Array<{ currency: string; available: string; frozen: string }>;
  summary: { requested: string; paid: string };
  withdrawals: SupplierWithdrawal[];
  settlement_mode: "manual_bank_transfer";
  policy: { commission_rate: string; settlement_hold_hours: number; dispute_holds_settlement: boolean };
};
export function getSupplierRevenue() { return apiRequest<SupplierRevenue>("/api/v1/supplier/revenue"); }
export function createSupplierWithdrawal(input: { amount: string; beneficiary_name: string; bank_name: string; bank_account_no: string }) { return apiRequest<SupplierWithdrawal>("/api/v1/supplier/withdrawals", { method: "POST", headers: { "Idempotency-Key": `supplier-withdrawal-${crypto.randomUUID()}` }, body: JSON.stringify({ ...input, currency: "CNY" }) }); }
export function cancelSupplierWithdrawal(id: number, version: number) { return apiRequest<SupplierWithdrawal>(`/api/v1/supplier/withdrawals/${id}/cancel`, { method: "POST", body: JSON.stringify({ version }) }); }
export function listAdminWithdrawals(status?: string) { return apiRequest<SupplierWithdrawal[]>(`/api/v1/admin/withdrawals${queryString({ status })}`); }
export function approveAdminWithdrawal(id: number, version: number, note?: string) { return apiRequest<SupplierWithdrawal>(`/api/v1/admin/withdrawals/${id}/approve`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function rejectAdminWithdrawal(id: number, version: number, note: string) { return apiRequest<SupplierWithdrawal>(`/api/v1/admin/withdrawals/${id}/reject`, { method: "POST", body: JSON.stringify({ version, note }) }); }
export function completeAdminWithdrawal(id: number, version: number, paymentReference: string, note?: string) { return apiRequest<SupplierWithdrawal>(`/api/v1/admin/withdrawals/${id}/complete`, { method: "POST", body: JSON.stringify({ version, payment_reference: paymentReference, note: note || null }) }); }

export function listPublicProducts() { return publicApiEnvelopeRequest<PublicProduct[], { count: number; real_data_only: boolean; server_rental_available: boolean; payment_mode: "local_placeholder" | "pingxx" }>("/api/v1/public/products", 15_000); }
export function getPublicProduct(id: number) { return apiEnvelopeRequest<PublicProduct, { real_data_only: boolean; server_rental_available: boolean; payment_mode: "local_placeholder" | "pingxx" }>(`/api/v1/public/products/${id}`); }

export function listSupplierResources(status?: ResourceStatus) { return apiEnvelopeRequest<Resource[], PageMeta>(`/api/v1/supplier/resources${queryString({ status })}`); }
export function getSupplierResource(id: number) { return apiRequest<ResourceDetail>(`/api/v1/supplier/resources/${id}`); }
export function createSupplierResource(input: Record<string, unknown>) { return apiRequest<Resource>("/api/v1/supplier/resources", { method: "POST", body: JSON.stringify(input) }); }
export function updateSupplierResource(id: number, input: Record<string, unknown>) { return apiRequest<Resource>(`/api/v1/supplier/resources/${id}`, { method: "PATCH", body: JSON.stringify(input) }); }
export function deleteSupplierResource(id: number, version: number) { return apiRequest<{ deleted: boolean }>(`/api/v1/supplier/resources/${id}?version=${version}`, { method: "DELETE" }); }
export function transitionSupplierResource(id: number, action: "submit-review" | "withdraw-review" | "publish" | "unpublish", version: number, note?: string) { return apiRequest<Resource>(`/api/v1/supplier/resources/${id}/${action}`, { method: "POST", body: JSON.stringify({ version, note: note || null }) }); }
export function listInventoryReservations(status?: ReservationStatus) { return apiEnvelopeRequest<InventoryReservation[], PageMeta>(`/api/v1/supplier/inventory-reservations${queryString({ status })}`); }
export function releaseInventoryReservation(id: number, version: number, reason: string) { return apiRequest<InventoryReservation>(`/api/v1/supplier/inventory-reservations/${id}/release`, { method: "POST", body: JSON.stringify({ version, reason }) }); }

export function listAdminResources(filters: { status?: ResourceStatus; search?: string } = {}) { return apiEnvelopeRequest<Resource[], PageMeta>(`/api/v1/admin/resources${queryString(filters)}`); }
export function reviewResource(id: number, action: "approve" | "reject", version: number, note: string) { return apiRequest<Resource>(`/api/v1/admin/resources/${id}/${action}`, { method: "POST", body: JSON.stringify({ version, note: note || (action === "reject" ? "资源资料不完整" : null) }) }); }

export function listSupplierApplications(filters: { status?: string; search?: string } = {}) { return apiEnvelopeRequest<SupplierApplication[], PageMeta>(`/api/v1/admin/supplier-applications${queryString(filters)}`); }
export function reviewSupplierApplication(id: number, action: "approve" | "reject", version: number, note: string) { return apiRequest<SupplierApplication>(`/api/v1/admin/supplier-applications/${id}/${action}`, { method: "POST", body: JSON.stringify({ version, note: note || (action === "reject" ? "资料不符合要求" : null) }) }); }

export type { ApiEnvelope };
