import { apiRequest } from "@/lib/api";
import { canonicalApiPath } from "@/lib/canonical-api";
import type { AccountDeletionEligibility, AccountDeletionStatus, AccountDeletionVerification } from "@/lib/account-deletion-flow";

export function getAccountDeletionEligibility() {
  return apiRequest<AccountDeletionEligibility>(canonicalApiPath("/user/account-deletion/eligibility"));
}

export function verifyAccountDeletion(password: string) {
  return apiRequest<AccountDeletionVerification>(canonicalApiPath("/user/account-deletion/verify"), {
    method: "POST", body: JSON.stringify({ password }),
  });
}

export function submitAccountDeletion(ticket: string) {
  return apiRequest<AccountDeletionStatus>(canonicalApiPath("/user/account-deletion/submit"), {
    method: "POST", body: JSON.stringify({ ticket, confirm: true }),
  });
}

export function getAccountDeletionStatus(ticket: string) {
  // Does not use getCurrentUser or navigate on 401: normal sessions have already
  // been revoked while this deletion-only receipt can still return the result.
  return apiRequest<AccountDeletionStatus>(canonicalApiPath("/user/account-deletion/status"), {
    method: "POST", body: JSON.stringify({ ticket }),
  });
}
