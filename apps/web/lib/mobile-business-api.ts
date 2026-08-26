import { ApiError, apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";
import type { RebateTier } from "@/lib/product-purchase";
import {
  normalizeInviteRecordBundle,
  normalizeInviteSummary,
  type InviteRecord,
  type InviteRecordBundle,
  type InviteSummary,
  type InviteTier,
} from "@/lib/invite-v2";

export type { InviteRecord, InviteRecordBundle, InviteSummary, InviteTier } from "@/lib/invite-v2";


export type MobileAsset = {
  id: number;
  product_id: number;
  order_id?: number;
  quantity: number;
  value: number;
  unit_value?: number;
  daily_rate: number;
  status: string;
  start_at?: string;
  end_at?: string;
  created_at?: string;
  product_name?: string;
  gpu_model?: string;
  today_revenue?: number;
  accumulated_revenue?: number;
  remaining_days?: number;
  purchase_type?: string;
  current_price?: number;
  pnl?: number;
  pnl_pct?: number;
  can_sell?: boolean;
  rebate_status?: string;
  rebate_amount?: number;
  trading_unavailable_reason?: string;
};

export type MobileAssetSummary = {
  total_value: number;
  wallet_balance: number;
  pending_revenue: number;
  revenue_rate: number;
  revenue_settlement_enabled: boolean;
  historical_test_revenue: number;
  items: MobileAsset[];
};

export type OnboardingItem = {
  id: number;
  entity_type: "personal" | "company";
  contact: string;
  phone: string;
  device_model: string;
  device_count: number;
  location?: string;
  remark?: string;
  status: string;
  created_at?: string;
};

export type RevenueSummary = {
  today: number;
  total: number;
  rate: number;
  revenue_settlement_enabled: boolean;
  historical_test_total: number;
};

export type RevenuePoint = { date: string; amount: number };
export type RevenueRecord = { id: number; asset_id?: number; amount: number; date?: string; created_at?: string };

export type RebateSummary = {
  program_code: "consumer_purchase_rebate";
  policy_version: string;
  period_key: string;
  month_spent: number;
  month_rebated: number;
  month_entitled: number;
  current_rate: number;
  minimum_order_amount: number;
  tiers: RebateTier[];
  next_tier_hint: string;
  pending_rebate: number;
  monthly_cap: number;
  cap_used: number;
  cap_remaining: number;
  rewards_enabled: boolean;
  reward_mode: "disabled" | "test_card_hours" | "live";
};

export type Coupon = { id: number; name: string; amount: number; min_amount: number; status: string; expires_at?: string };

export type BankCard = {
  id: number;
  bank_name: string;
  card_number: string;
  card_last4?: string;
  holder: string;
  phone?: string;
  is_default: boolean;
  status: "registered" | "pending_review" | "active" | "rejected" | "disabled";
  verification_mode: "format_only" | "manual_review" | "legacy_unvalidated";
  reject_reason?: string | null;
  created_at?: string | null;
};

export type BankCardConfig = {
  binding_enabled: boolean;
  mode: "format_only" | "manual_review";
  bank_verified: false;
  notice?: string;
};

export type VerificationInfo = {
  status: "unverified" | "pending" | "verified" | "rejected" | string;
  real_name?: string;
  id_card_masked?: string;
  consent_recorded?: boolean;
  reject_reason?: string;
  front_photo_uploaded?: boolean;
  back_photo_uploaded?: boolean;
  ocr_status?: string | null;
  ocr_message?: string | null;
  ocr_summary?: Record<string, boolean> | null;
  ocr_error_code?: string | null;
  ocr_updated_at?: string | null;
};

export type MobileWallet = {
  balance: number;
  total_available_balance?: number;
  frozen: number;
  withdrawable_balance: number;
  withdraw_frozen: number;
  total_income: number;
  has_bank_card?: boolean;
  payment_service_enabled?: boolean;
  recharge_service_enabled?: boolean;
  withdraw_service_enabled?: boolean;
  revenue_settlement_enabled?: boolean;
  historical_test_revenue?: number;
  reward_service_enabled?: boolean;
  historical_test_rewards?: number;
};

export type MobileLedgerItem = {
  id: number;
  type: string;
  direction: string;
  amount: number;
  balance_after: number;
  remark?: string;
  created_at?: string;
};

export type WithdrawalConfig = {
  enabled: boolean;
  manual_transfer: true;
  rate_cny_per_card_hour: number;
  fee_rate: number;
  min_card_hours: number;
  max_card_hours: number;
  notice?: string;
};

export type RechargePaymentConfig = {
  provider: "mapay" | "qixiangpay";
  enabled: boolean;
  card_hour_rmb_rate: number;
  min_amount_cny: number;
  max_amount_cny: number;
  checkout_mode: "hosted_page";
  checkout_ttl_seconds?: number;
  payment_types?: Array<"alipay" | "wxpay">;
};

export type RechargePaymentOrder = {
  order_no: string;
  provider?: "qixiangpay" | "mapay" | string;
  channel?: string | null;
  status: "pending" | "paid" | "expired" | "failed" | "review" | "late_paid_review" | string;
  amount_cny: number;
  card_hours: number;
  checkout_url?: string | null;
  expires_at?: string | null;
  remaining_seconds?: number | null;
  can_pay?: boolean;
  can_query?: boolean;
  can_cancel?: boolean;
  failure_reason?: string | null;
  paid_at?: string | null;
  credited_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type RechargePaymentPage = {
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  items: RechargePaymentOrder[];
};

export type WithdrawalOrder = {
  id: number;
  order_no: string;
  status: string;
  amount_card_hours: number;
  locked_rate_cny: number;
  gross_amount_cny: number;
  fee_cny: number;
  net_amount_cny: number;
  bank_card: { id: number; bank_name: string; card_last4?: string; card_number?: string; holder: string };
  created_at?: string | null;
};

export type WithdrawalPage = {
  total: number;
  page: number;
  page_size: number;
  items: WithdrawalOrder[];
};

export type SupplierWallet = {
  total_revenue: number;
  pending_amount: number;
  withdrawn: number;
  available: number;
  today_revenue: number;
  payment_service_enabled: boolean;
};

export type SupplierRevenueRecord = {
  order_no: string;
  product_name: string;
  buyer_name: string;
  amount: number;
  service_fee: number;
  net_income: number;
  status: string;
  purchase_type?: string | null;
  created_at?: string | null;
};

export type SupplierStats = {
  device_stats: Array<{ name: string; gpu_model: string; order_count: number; price: number; utilization: number }>;
  revenue_trend: Array<{ date: string; amount: number }>;
  total_products: number;
  total_orders: number;
  attention_count: number;
};

export type MobileStore = {
  supplier: SupplierProfile & { rating?: number; order_count?: number };
  products: Array<{ id: number; name: string; gpu_model: string; memory: string; price: number; stock?: number; region_name?: string; region_code?: string; purchasable?: boolean }>;
};

export type SupplierRebate = {
  program_code: "supplier_sales_rebate";
  policy_version: string;
  period_key: string;
  month_sales: number;
  month_rebated: number;
  month_entitled: number;
  pending_rebate: number;
  current_rate: number;
  tiers: RebateTier[];
  monthly_target: number;
  est_total_rebate: number;
  next_tier_hint: string;
  monthly_cap: number;
  cap_used: number;
  cap_remaining: number;
  rewards_enabled: boolean;
  reward_mode: "disabled" | "test_card_hours" | "live";
};

export type SupplierProfile = {
  id?: number;
  company_name?: string;
  contact?: string;
  phone?: string;
  region?: string;
  desc?: string;
  status: string;
};

export type MobileUserProfile = {
  id: number;
  username: string;
  phone?: string | null;
  phone_bound?: boolean;
  avatar?: string | null;
  role?: "personal" | "supplier" | "admin" | string;
  supplier_status?: string | null;
  created_at?: string | null;
};

export function mobileAvatarUrl(avatar?: string | null) {
  if (!avatar) return "";
  if (avatar.startsWith("/user/avatars/")) return canonicalApiPath(avatar);
  return avatar;
}

export function getMobileUserProfile() {
  return apiRequest<MobileUserProfile>(canonicalApiPath("/user/profile"));
}

export function updateMobileUserProfile(username: string) {
  return apiRequest<MobileUserProfile>(canonicalApiPath("/user/profile"), {
    method: "PUT",
    body: JSON.stringify({ username }),
  });
}

export function uploadMobileAvatar(file: File) {
  const form = new FormData();
  form.set("avatar", file);
  return apiRequest<{ avatar: string }>(canonicalApiPath("/user/avatar"), { method: "POST", body: form });
}

export function changeMobilePassword(old_password: string, new_password: string) {
  return apiRequest<{ changed: boolean }>(canonicalApiPath("/user/password"), {
    method: "POST",
    body: JSON.stringify({ old_password, new_password }),
  });
}

export function switchMobileRole() {
  return apiRequest<{ role: string }>(canonicalApiPath("/user/role/switch"), { method: "POST" });
}

export function getMobileAssets(status?: string) {
  const query = status && status !== "all" ? `?status_filter=${encodeURIComponent(status)}` : "";
  return apiRequest<MobileAssetSummary>(canonicalApiPath(`/assets${query}`));
}

export function getMobileAsset(id: number) {
  return apiRequest<MobileAsset>(canonicalApiPath(`/assets/${id}`));
}

export function getOnboardingMine() {
  return apiRequest<OnboardingItem[]>(canonicalApiPath("/onboarding/mine"));
}

export function submitOnboarding(input: Omit<OnboardingItem, "id" | "status" | "created_at">) {
  return apiRequest<OnboardingItem>(canonicalApiPath("/onboarding"), { method: "POST", body: JSON.stringify(input) });
}

export function sellMobileAsset(id: number) {
  return apiRequest<{ id: number; status: string; sell_price: number; pnl: number }>(canonicalApiPath(`/assets/${id}/sell`), { method: "POST" });
}

export function getRevenueBundle(range = 30) {
  return Promise.all([
    apiRequest<RevenueSummary>(canonicalApiPath("/revenue")),
    apiRequest<RevenuePoint[]>(canonicalApiPath(`/revenue/chart?range_days=${range}`)),
    apiRequest<RevenueRecord[]>(canonicalApiPath("/revenue/records")),
    getUserRebate(),
  ]);
}

export function getUserRebate() {
  return apiRequest<RebateSummary>(canonicalApiPath("/user/rebate"));
}

export async function getInviteBundle(): Promise<readonly [InviteSummary, InviteRecordBundle]> {
  const [summaryResult, recordsResult, commissionsResult] = await Promise.allSettled([
    apiRequest<unknown>(canonicalApiPath("/invite/summary")),
    apiRequest<unknown>(canonicalApiPath("/invite/records")),
    apiRequest<unknown>(canonicalApiPath("/invite/commissions?page=1&page_size=50")),
  ]);
  if (summaryResult.status === "rejected") throw summaryResult.reason;
  if (recordsResult.status === "rejected") throw recordsResult.reason;

  const summary = normalizeInviteSummary(summaryResult.value);
  let commissions: unknown;
  if (commissionsResult.status === "fulfilled") {
    commissions = commissionsResult.value;
  } else if (!summary.isV2 && commissionsResult.reason instanceof ApiError && commissionsResult.reason.status === 404) {
    commissions = { total: 0, items: [] };
  } else {
    throw commissionsResult.reason;
  }

  return [summary, normalizeInviteRecordBundle(recordsResult.value, commissions)] as const;
}

export function listCoupons(status = "") {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<Coupon[]>(canonicalApiPath(`/coupons${query}`));
}

export function redeemCoupon(code: string) {
  return apiRequest<Coupon>(canonicalApiPath("/coupons/redeem"), { method: "POST", body: JSON.stringify({ code }) });
}

export function getBankCardBundle() {
  return Promise.all([
    apiRequest<BankCard[]>(canonicalApiPath("/bank-cards")),
    apiRequest<BankCardConfig>(canonicalApiPath("/bank-cards/config")),
  ]);
}

export function addBankCard(input: { bank_name?: string; card_number: string; holder: string; phone?: string; is_default?: boolean }) {
  return apiRequest<BankCard>(canonicalApiPath("/bank-cards"), { method: "POST", body: JSON.stringify(input) });
}

export function setDefaultBankCard(id: number) {
  return apiRequest<unknown>(canonicalApiPath(`/bank-cards/${id}/default`), { method: "POST" });
}

export function deleteBankCard(id: number) {
  return apiRequest<unknown>(canonicalApiPath(`/bank-cards/${id}`), { method: "DELETE" });
}

export function getVerification() {
  return apiRequest<VerificationInfo>(canonicalApiPath("/verification"));
}

export function submitVerification(input: { real_name: string; id_card: string; sensitive_consent: boolean }) {
  return apiRequest<VerificationInfo>(canonicalApiPath("/verification"), { method: "POST", body: JSON.stringify(input) });
}

export function uploadVerificationPhotos(front?: File | null, back?: File | null) {
  const form = new FormData();
  if (front) form.set("front", front);
  if (back) form.set("back", back);
  return apiRequest<VerificationInfo>(canonicalApiPath("/verification/upload"), { method: "POST", body: form });
}

export function getMobileWallet() {
  return apiRequest<MobileWallet>(canonicalApiPath("/wallet"));
}

export function getMobileLedger() {
  return apiRequest<{ total: number; page: number; page_size: number; items: MobileLedgerItem[] }>(canonicalApiPath("/wallet/ledger?page=1&page_size=20"));
}

export function listWithdrawals(params: { page?: number; page_size?: number; status_filter?: string } = {}) {
  const query = new URLSearchParams({
    page: String(params.page || 1),
    page_size: String(params.page_size || 20),
  });
  if (params.status_filter) query.set("status_filter", params.status_filter);
  return apiRequest<WithdrawalPage>(canonicalApiPath(`/withdrawals?${query.toString()}`));
}

export function getWithdrawalBundle(params: { page?: number; page_size?: number; status_filter?: string } = {}) {
  return Promise.all([
    apiRequest<WithdrawalConfig>(canonicalApiPath("/withdrawals/config")),
    listWithdrawals(params),
    apiRequest<BankCard[]>(canonicalApiPath("/bank-cards")),
  ]);
}

export function getRechargePaymentConfig() {
  return apiRequest<RechargePaymentConfig>(canonicalApiPath("/payments/qixiang/config"));
}

export function createRechargePayment(amount_cny: number, payment_type: "alipay" | "wxpay") {
  return apiRequest<RechargePaymentOrder>(canonicalApiPath("/payments/qixiang/recharge-orders"), {
    method: "POST",
    body: JSON.stringify({ amount_cny, payment_type }),
  });
}

export function getRechargePayment(orderNo: string) {
  return apiRequest<RechargePaymentOrder>(canonicalApiPath(`/payments/qixiang/orders/${encodeURIComponent(orderNo)}`));
}

export function listRechargePayments(params: { page?: number; page_size?: number; status?: string; order_no?: string } = {}) {
  const query = new URLSearchParams({
    page: String(params.page || 1),
    page_size: String(params.page_size || 20),
  });
  if (params.status) query.set("status", params.status);
  if (params.order_no) query.set("order_no", params.order_no);
  return apiRequest<RechargePaymentPage>(canonicalApiPath(`/payments/qixiang/orders?${query.toString()}`));
}

export function queryRechargePayment(orderNo: string) {
  return apiRequest<RechargePaymentOrder>(canonicalApiPath(`/payments/qixiang/orders/${encodeURIComponent(orderNo)}/query`), { method: "POST" });
}

export function cancelRechargePayment(orderNo: string) {
  return apiRequest<RechargePaymentOrder>(canonicalApiPath(`/payments/qixiang/orders/${encodeURIComponent(orderNo)}/cancel`), { method: "POST" });
}

export function createWithdrawal(input: { amount_card_hours: number; bank_card_id: number; client_request_id: string }) {
  return apiRequest<WithdrawalOrder>(canonicalApiPath("/withdrawals"), { method: "POST", body: JSON.stringify(input) });
}

export function cancelWithdrawal(id: number) {
  return apiRequest<WithdrawalOrder>(canonicalApiPath(`/withdrawals/${id}/cancel`), { method: "POST" });
}

export function getSupplierRevenueBundle() {
  return Promise.all([
    apiRequest<SupplierWallet>(canonicalApiPath("/supplier/wallet")),
    apiRequest<SupplierRevenueRecord[]>(canonicalApiPath("/supplier/revenue/detail")),
  ]);
}

export function getSupplierStats() {
  return apiRequest<SupplierStats>(canonicalApiPath("/supplier/stats"));
}

export function getSupplierRebate() {
  return apiRequest<SupplierRebate>(canonicalApiPath("/supplier/rebate"));
}

export function getSupplierProfile() {
  return apiRequest<SupplierProfile>(canonicalApiPath("/supplier/mine"));
}

export function getMobileStore(id: number) {
  return apiRequest<MobileStore>(canonicalApiPath(`/supplier/${id}`));
}

export function updateSupplierProfile(input: Partial<Pick<SupplierProfile, "company_name" | "contact" | "phone" | "region" | "desc">>) {
  return apiRequest<SupplierProfile>(canonicalApiPath("/supplier/profile"), { method: "PUT", body: JSON.stringify(input) });
}
