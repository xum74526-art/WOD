import { apiRequest } from "@/lib/api";
import { canonicalApiPath as path } from "@/lib/canonical-api";
export type AuditPlatform = "web" | "ios" | "android" | "admin" | "legacy";
export type FinancePage<T> = { total: number; page: number; page_size: number; items: T[] };
export type FinanceListInput = { status?: string; platform?: AuditPlatform; page?: number; pageSize?: number };
export type FinanceVerification = { id: number; user_id: number; username: string; real_name: string; id_card_masked: string; status: "pending" | "verified" | "rejected"; reject_reason?: string | null; front_photo_uploaded: boolean; back_photo_uploaded: boolean; consent_recorded?: boolean; ocr_status?: string | null; ocr_message?: string | null; created_platform?: string; last_modified_platform?: string; created_at?: string | null; updated_at?: string | null };
export type FinanceWithdrawal = { id: number; order_no: string; status: "reviewing" | "manual_payment_pending" | "paid" | "rejected" | "failed" | "canceled"; amount_card_hours: number; locked_rate_cny: number; gross_amount_cny: number; fee_cny: number; net_amount_cny: number; bank_card: { id: number; bank_name: string; card_number: string; card_last4?: string; holder: string }; review_note?: string | null; failure_reason?: string | null; bank_reference?: string | null; paid_at?: string | null; receipt_available: boolean; created_platform?: string; last_modified_platform?: string; created_at?: string | null; updated_at?: string | null; user?: { id: number; username?: string } };
export type PaymentInstructions = { holder: string; bank_name: string; card_number: string; phone?: string | null; amount_cny?: number; reveal_token: string; reveal_expires_at: string; notice?: string };
export type FinanceAccess = {
  is_admin: boolean;
  /** Compatibility alias for already-installed clients; access is role-based. */
  is_finance_admin: boolean;
  manual_bank_card_enabled: boolean;
  manual_payout_enabled: boolean;
};
export type FinanceBankCard = { id: number; user_id: number; username?: string | null; bank_name: string; card_number: string; card_last4?: string; holder: string; phone?: string | null; is_default: boolean; status: "registered" | "pending_review" | "active" | "rejected" | "disabled"; verification_mode: "format_only" | "manual_review" | "legacy_unvalidated"; bank_verified: false; reject_reason?: string | null; created_platform?: string; last_modified_platform?: string; reviewed_at?: string | null; created_at?: string | null };
function boundedPositiveInteger(value: number | undefined, fallback: number, maximum: number) { const normalized = typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : fallback; return Math.min(maximum, Math.max(1, normalized)); }
export function financeListQuery(input: FinanceListInput = {}) {
  const page = boundedPositiveInteger(input.page, 1, Number.MAX_SAFE_INTEGER);
  const pageSize = boundedPositiveInteger(input.pageSize, 20, 100);
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (input.status) query.set("status_filter", input.status);
  if (input.platform) query.set("platform", input.platform);
  return `?${query.toString()}`;
}
export function getFinanceAccess() { return apiRequest<FinanceAccess>(path("/finance/me")); }
export function listFinanceBankCards(input: FinanceListInput = {}) { return apiRequest<FinancePage<FinanceBankCard>>(path(`/finance/bank-cards${financeListQuery({ ...input, status: input.status ?? "registered" })}`)); }
export function reviewFinanceBankCard(id: number, approved: boolean, reason?: string) { return apiRequest<FinanceBankCard>(path(`/finance/bank-cards/${id}/review`), { method: "POST", body: JSON.stringify({ approved, reason }) }); }
export function listFinanceVerifications(input: FinanceListInput = {}) { return apiRequest<FinancePage<FinanceVerification>>(path(`/finance/verifications${financeListQuery({ ...input, status: input.status ?? "pending" })}`)); }
export function reviewFinanceVerification(id: number, approved: boolean, reason?: string) { return apiRequest<FinanceVerification>(path(`/finance/verifications/${id}/review`), { method: "POST", body: JSON.stringify({ approved, reason }) }); }
export function financeVerificationPhoto(id: number, side: "front" | "back") { return path(`/finance/verifications/${id}/photo/${side}`); }
export function listFinanceWithdrawals(input: FinanceListInput = {}) { return apiRequest<FinancePage<FinanceWithdrawal>>(path(`/finance/withdrawals${financeListQuery({ ...input, status: input.status ?? "reviewing" })}`)); }
export function approveFinanceWithdrawal(id: number, note?: string) { return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/approve`), { method: "POST", body: JSON.stringify({ note }) }); }
export function rejectFinanceWithdrawal(id: number, reason: string) { return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/reject`), { method: "POST", body: JSON.stringify({ reason }) }); }
export function failFinanceWithdrawal(id: number, reason: string) { return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/mark-failed`), { method: "POST", body: JSON.stringify({ reason }) }); }
export function getPaymentInstructions(id: number) { return apiRequest<PaymentInstructions>(path(`/finance/withdrawals/${id}/payment-instructions?reveal=true`)); }
export function financeWithdrawalReceipt(id: number) { return path(`/finance/withdrawals/${id}/receipt`); }
export function markFinanceWithdrawalPaid(id: number, receipt: File, input: { bank_reference: string; paid_amount_cny: string; paid_at: string; reveal_token: string }) { const form = new FormData(); form.set("receipt", receipt); Object.entries(input).forEach(([key, value]) => form.set(key, value)); form.set("payee_confirmed", "true"); return apiRequest<FinanceWithdrawal>(path(`/finance/withdrawals/${id}/mark-paid`), { method: "POST", body: form }); }
