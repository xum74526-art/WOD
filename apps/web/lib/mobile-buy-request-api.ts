import { apiRequest } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";

export type MobileBuyRequest = {
  id: number;
  user_id?: number;
  buyer_name?: string;
  request_type: "online" | "offline";
  gpu_model: string;
  gpu_variant?: string;
  quantity: number;
  gpu_hours?: number;
  max_unit_price?: number;
  budget?: number;
  currency: string;
  region?: string;
  billing_mode?: string;
  requirements: Record<string, unknown>;
  contact?: string;
  phone?: string;
  status: string;
  quote_count: number;
  is_own?: boolean;
  targeted_supplier_id?: number | null;
  targeted_to_me?: boolean;
  expires_at?: string;
  created_at?: string;
  updated_at?: string;
  legacy: boolean;
};

export type MobileBuyQuoteRevision = {
  id: number;
  quote_id?: number;
  revision_no: number;
  actor_role: "buyer" | "supplier" | string;
  unit_price?: number;
  total_price: number;
  currency: string;
  available_at?: string;
  message?: string;
  expires_at?: string;
  created_at?: string;
};

export type MobileBuyQuote = {
  id: number;
  buy_request_id: number;
  supplier_id: number;
  supplier_name: string;
  supplier_rating?: number;
  unit_price?: number;
  total_price: number;
  currency: string;
  available_at?: string;
  message?: string;
  status: string;
  expires_at?: string;
  created_at?: string;
  updated_at?: string;
  revision_count?: number;
  latest_revision?: MobileBuyQuoteRevision | null;
  revisions?: MobileBuyQuoteRevision[];
  can_counter?: boolean;
  can_withdraw?: boolean;
};

export type MobileBuyRequestDeal = {
  id: number;
  buy_request_id?: number;
  quote_id: number;
  selected_revision_id?: number | null;
  supplier_id: number;
  supplier_name?: string;
  status: string;
  credential_status?: string | null;
  credential_fingerprint?: string | null;
  credential_version?: number | null;
  credential?: { status?: string | null; fingerprint?: string | null; envelope_version?: number | null; credential_version?: number | null; submitted_at?: string | null; inspected_at?: string | null; released_at?: string | null } | null;
  can_supplier_confirm?: boolean;
  can_supplier_decline?: boolean;
  can_submit_credential?: boolean;
  can_buyer_view_credential?: boolean;
  can_buyer_confirm?: boolean;
  can_report?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type MobileBuyRequestEvent = {
  id: number;
  event_type?: string;
  status?: string;
  label?: string;
  actor_role?: string;
  message?: string;
  created_at?: string;
};

export type MobileBuyRequestCredential = {
  host: string;
  port: number;
  username: string;
  auth_type: "password" | "private_key";
  secret?: string;
  note?: string;
  fingerprint?: string;
  version?: number;
  released_at?: string;
};

export type MobileBuyRequestDetail = {
  request: MobileBuyRequest;
  quotes: MobileBuyQuote[];
  deal?: MobileBuyRequestDeal | null;
  events?: MobileBuyRequestEvent[];
};

export type MobileBuyQuoteInput = {
  unit_price?: number;
  total_price: number;
  currency: string;
  available_at?: string;
  message?: string;
  expires_in_hours: number;
};

export type MobileBuyRequestSummary = { active: number; new_quotes: number; pending_confirmation: number };

export function getMobileBuyRequestSummary() {
  return apiRequest<MobileBuyRequestSummary>(path("/buy-requests/summary"));
}

export function listMobileBuyRequests(type: "online" | "offline", view: "buyer" | "seller") {
  return apiRequest<MobileBuyRequest[]>(path(`/buy-requests?request_type=${type}&view=${view}`));
}

export function getMobileBuyRequest(id: number) {
  return apiRequest<MobileBuyRequestDetail>(path(`/buy-requests/${id}`));
}

export function createMobileBuyRequest(input: Record<string, unknown>) {
  return apiRequest<MobileBuyRequest>(path("/buy-requests"), { method: "POST", body: JSON.stringify(input) });
}

export function createMobileBuyQuote(id: number, input: MobileBuyQuoteInput) {
  return apiRequest<MobileBuyQuote>(path(`/buy-requests/${id}/quotes`), { method: "POST", body: JSON.stringify(input) });
}

export function counterMobileBuyQuote(requestId: number, quoteId: number, input: MobileBuyQuoteInput) {
  return apiRequest<MobileBuyQuote>(path(`/buy-requests/${requestId}/quotes/${quoteId}/counter`), { method: "POST", body: JSON.stringify(input) });
}

export function withdrawMobileBuyQuote(requestId: number, quoteId: number) {
  return apiRequest<{ request_id: number; quote_id: number; status: string }>(path(`/buy-requests/${requestId}/quotes/${quoteId}/withdraw`), { method: "POST" });
}

export function selectMobileBuyQuote(requestId: number, quoteId: number) {
  return apiRequest<{ request_id: number; quote_id: number; deal_id?: number; deal?: MobileBuyRequestDeal; status: string; quote_status: string; commerce_mode: "direct_trade" | "matchmaking" | "history_only" }>(path(`/buy-requests/${requestId}/quotes/${quoteId}/select`), { method: "POST" });
}

export function confirmMobileBuyRequestDeal(requestId: number, dealId: number) {
  return apiRequest<MobileBuyRequestDeal>(path(`/buy-requests/${requestId}/deals/${dealId}/supplier-confirm`), { method: "POST" });
}

export function declineMobileBuyRequestDeal(requestId: number, dealId: number) {
  return apiRequest<MobileBuyRequestDeal>(path(`/buy-requests/${requestId}/deals/${dealId}/supplier-decline`), { method: "POST" });
}

export function submitMobileBuyRequestCredential(requestId: number, dealId: number, input: { host: string; port: number; username: string; auth_type: "password" | "private_key"; secret: string; note?: string }) {
  return apiRequest<{ status: string; credential_status?: string }>(path(`/buy-requests/${requestId}/deals/${dealId}/credential`), { method: "POST", body: JSON.stringify(input) });
}

export function getMobileBuyRequestCredential(requestId: number, dealId: number) {
  return apiRequest<MobileBuyRequestCredential>(path(`/buy-requests/${requestId}/deals/${dealId}/credential`));
}

export function confirmMobileBuyRequestDelivery(requestId: number, dealId: number) {
  return apiRequest<MobileBuyRequestDeal>(path(`/buy-requests/${requestId}/deals/${dealId}/confirm-delivery`), { method: "POST" });
}

export function reportMobileBuyRequestDelivery(requestId: number, dealId: number, reason: string) {
  return apiRequest<MobileBuyRequestDeal>(path(`/buy-requests/${requestId}/deals/${dealId}/report-delivery`), { method: "POST", body: JSON.stringify({ reason }) });
}
