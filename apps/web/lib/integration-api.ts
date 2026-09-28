import { apiRequest } from "@/lib/api";

export type ProviderDescriptor = {
  kind: "payment" | "kyc" | "object_storage";
  provider: string;
  status: "disabled" | "adapter_missing" | "configured" | "degraded";
  configured: boolean;
  capabilities: string[];
  reason: string | null;
};

export type PaymentIntent = {
  id: number;
  payment_no: string;
  order_id: number | null;
  purpose: string;
  amount: string;
  currency: string;
  status: string;
  provider: string;
  checkout_url: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
};

export type WalletSnapshot = {
  provider: ProviderDescriptor;
  balances: Array<{ currency: string; available: string; frozen: string }>;
  payment_intents: PaymentIntent[];
  ledger_mode: "mobile_ledger";
};

export type KycSnapshot = {
  status: "unverified" | "draft" | "pending" | "approved" | "rejected" | "expired";
  application: null | {
    id: number;
    status: string;
    verification_type: "individual" | "business";
    country_code: string;
    provider: string;
    subject: null | {
      legal_name: string | null;
      identifier_type: "national_id" | "business_registration" | null;
      identifier_number: string | null;
      representative_name: string | null;
    };
    review_note: string | null;
    submitted_at: string | null;
    reviewed_at: string | null;
    declaration_accepted_at: string | null;
    expires_at: string | null;
    updated_at: string;
    version: number;
  };
  provider: ProviderDescriptor;
};

export type ManualKycApplication = NonNullable<KycSnapshot["application"]> & {
  applicant?: {
    id: number;
    display_name: string;
    email: string | null;
    phone: string | null;
    role: string;
  };
};

export function getWalletSnapshot() {
  return apiRequest<WalletSnapshot>("/api/v1/account/wallet");
}

export function getKycSnapshot() {
  return apiRequest<KycSnapshot>("/api/v1/account/kyc");
}

export function startKyc(verificationType: "individual" | "business") {
  return apiRequest<{ application_id: number; status: string; verification_url: string }>(
    "/api/v1/account/kyc/start",
    {
      method: "POST",
      body: JSON.stringify({ verification_type: verificationType, country_code: "CN" }),
    },
  );
}

export function submitManualKyc(input: {
  verification_type: "individual" | "business";
  country_code: "CN";
  legal_name: string;
  identifier_type: "national_id" | "business_registration";
  identifier_number: string;
  representative_name?: string;
  declaration_accepted: boolean;
}) {
  return apiRequest<ManualKycApplication>("/api/v1/account/kyc/manual", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listAdminKyc(status?: string) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<ManualKycApplication[]>(`/api/v1/admin/kyc${query}`);
}

export function approveAdminKyc(id: number, version: number, note?: string) {
  return apiRequest<ManualKycApplication>(`/api/v1/admin/kyc/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ version, note }),
  });
}

export function rejectAdminKyc(id: number, version: number, note: string) {
  return apiRequest<ManualKycApplication>(`/api/v1/admin/kyc/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ version, note }),
  });
}
