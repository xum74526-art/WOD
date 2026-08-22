import { apiRequest } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";
export type MobileBuyRequest = { id: number; user_id: number; buyer_name: string; request_type: "online" | "offline"; gpu_model: string; gpu_variant?: string; quantity: number; gpu_hours?: number; max_unit_price?: number; budget?: number; currency: string; region?: string; billing_mode?: string; requirements: Record<string, unknown>; contact?: string; phone?: string; status: string; quote_count: number; expires_at?: string; created_at?: string; updated_at?: string; legacy: boolean };
export type MobileBuyQuote = { id: number; buy_request_id: number; supplier_id: number; supplier_name: string; supplier_rating?: number; unit_price?: number; total_price: number; currency: string; available_at?: string; message?: string; status: string; expires_at?: string; created_at?: string };
export type MobileBuyRequestSummary = { active: number; new_quotes: number; pending_confirmation: number };
export function getMobileBuyRequestSummary() { return apiRequest<MobileBuyRequestSummary>(path("/buy-requests/summary")); }
export function listMobileBuyRequests(type: "online" | "offline", view: "buyer" | "seller") { return apiRequest<MobileBuyRequest[]>(path(`/buy-requests?request_type=${type}&view=${view}`)); }
export function getMobileBuyRequest(id: number) { return apiRequest<{ request: MobileBuyRequest; quotes: MobileBuyQuote[] }>(path(`/buy-requests/${id}`)); }
export function createMobileBuyRequest(input: Record<string, unknown>) { return apiRequest<MobileBuyRequest>(path("/buy-requests"), { method: "POST", body: JSON.stringify(input) }); }
export function createMobileBuyQuote(id: number, input: { unit_price?: number; total_price: number; currency: string; message?: string; expires_in_hours: number }) { return apiRequest<MobileBuyQuote>(path(`/buy-requests/${id}/quotes`), { method: "POST", body: JSON.stringify(input) }); }
export function selectMobileBuyQuote(requestId: number, quoteId: number) { return apiRequest<{ request_id: number; quote_id: number; status: string }>(path(`/buy-requests/${requestId}/quotes/${quoteId}/select`), { method: "POST" }); }
