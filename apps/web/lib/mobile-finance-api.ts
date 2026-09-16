import { apiRequest } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";
export type AuditPlatform = "web" | "ios" | "android" | "admin" | "legacy";
export type FinanceVerification = { id: number; user_id: number; username: string; real_name: string; id_card_masked: string; status: "pending" | "verified" | "rejected"; reject_reason?: string | null; front_photo_uploaded: boolean; back_photo_uploaded: boolean; consent_recorded?: boolean; ocr_status?: string | null; ocr_message?: string | null; created_platform?: string; last_modified_platform?: string; created_at?: string | null; updated_at?: string | null };
export type FinanceWithdrawal = { id: number; order_no: string; status: "reviewing" | "manual_payment_pending" | "paid" | "rejected" | "failed" | "canceled"; amount_card_hours: number; locked_rate_cny: number; gross_amount_cny: number; fee_cny: number; net_amount_cny: number; bank_card: { id: number; bank_name: string; card_number: string; card_last4?: string; holder: string }; review_note?: string | null; failure_reason?: string | null; bank_reference?: string | null; paid_at?: string | null; created_platform?: string; last_modified_platform?: string; created_at?: string | null; updated_at?: string | null; user?: { id: number; username?: string } };
export type PaymentInstructions = { holder: string; bank_name: string; card_number: string; phone?: string | null; amount_cny?: number; reveal_token: string; reveal_expires_at: string; notice?: string };
export type FinanceAccess = {
  is_admin: boolean;
  /** Compatibility alias for already-installed clients; access is role-based. */
  is_finance_admin: boolean;
  manual_bank_card_enabled: boolean;
  manual_payout_enabled: boolean;
};
export type FinanceBankCard = { id: number; user_id: number; username?: string | null; bank_name: string; card_number: string; card_last4?: string; holder: string; phone?: string | null; is_default: boolean; status: "registered" | "pending_review" | "active" | "rejected" | "disabled"; verification_mode: "format_only" | "manual_review" | "legacy_unvalidated"; bank_verified: false; reject_reason?: string | null; created_platform?: string; last_modified_platform?: string; reviewed_at?: string | null; created_at?: string | null };
function financeListQuery(status: string, platform?: AuditPlatform) { const q = new URLSearchParams({ page: "1", page_size: "100" }); if (status) q.set("status_filter", status); if (platform) q.set("platform", platform); return `?${q.toString()}`; }
export function getFinanceAccess() { return apiRequest<FinanceAccess>(path("/finance/me")); }
export function listFinanceBankCards(status = "registered", platform?: AuditPlatform) { return apiRequest<{ total: number; items: FinanceBankCard[] }>(path(`/finance/bank-cards${financeListQuery(status, platform)}`)); }
export function reviewFinanceBankCard(id: number, approved: boolean, reason?: string) { return apiRequest<FinanceBankCard>(path(`/finance/bank-cards/${id}/review`), { method: "POST", body: JSON.stringify({ approved, reason }) }); }
export function listFinanceVerifications(status = "pending", platform?: AuditPlatform) { return apiRequest<{ total: number; items: FinanceVerification[] }>(path(`/finance/verifications${financeListQuery(status, platform)}`)); }
export function reviewFinanceVerification(id: number, approved: boolean, reason?: string) { return apiRequest<FinanceVerification>(path(`/finance/verifications/${id}/review`), { method: "POST", body: JSON.stringify({ approved, reason }) }); }
export function financeVerificationPhoto(id: number, side: "front" | "back") { return path(`/finance/verifications/${id}/photo/${side}`); }
export function listFinanceWithdrawals(status = "reviewing", platform?: AuditPlatform) { return apiRequest<{ total: number; items: FinanceWithdrawal[] }>(path(`/finance/withdrawals${financeListQuery(status, platform)}`)); }
export function approveFinanceWithdrawal(id: number, note?: string) { return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/approve`), { method: "POST", body: JSON.stringify({ note }) }); }
export function rejectFinanceWithdrawal(id: number, reason: string) { return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/reject`), { method: "POST", body: JSON.stringify({ reason }) }); }
export function failFinanceWithdrawal(id: number, reason: string) { return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/mark-failed`), { method: "POST", body: JSON.stringify({ reason }) }); }
export function getPaymentInstructions(id: number) { return apiRequest<PaymentInstructions>(path(`/finance/withdrawals/${id}/payment-instructions?reveal=true`)); }
export function markFinanceWithdrawalPaid(id: number, receipt: File, input: { bank_reference: string; paid_amount_cny: string; paid_at: string; reveal_token: string }) { const form = new FormData(); form.set("receipt", receipt); Object.entries(input).forEach(([key, value]) => form.set(key, value)); form.set("payee_confirmed", "true"); return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/mark-paid`), { method: "POST", body: form }); }
