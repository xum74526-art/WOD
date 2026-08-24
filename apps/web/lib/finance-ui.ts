export type RechargeUiState = "pending" | "processing" | "success" | "failed" | "expired" | "canceled";

export type RechargeStateSource = {
  order_no?: string | null;
  status?: string | null;
  credited_at?: string | null;
};

export const REGISTERED_BANK_CARD_STATUSES = ["registered", "pending_review", "active"] as const;

export function rechargeUiState(order?: RechargeStateSource | null): RechargeUiState {
  const status = String(order?.status || "").trim().toLowerCase();
  if (order?.credited_at) return "success";
  if (status === "paid" || status === "review" || status === "late_paid_review") return "processing";
  if (status === "failed") return "failed";
  if (status === "expired") return "expired";
  if (status === "canceled" || status === "cancelled") return "canceled";
  return "pending";
}

export function rechargeBlocksNewOrder(order?: RechargeStateSource | null) {
  if (!order) return false;
  const state = rechargeUiState(order);
  return state === "pending" || state === "processing";
}

export function rechargeCanRestart(order?: RechargeStateSource | null) {
  if (!order) return false;
  const state = rechargeUiState(order);
  return state === "failed" || state === "expired" || state === "canceled";
}

/** Never replace the recovery data for a different checkout that may still be live. */
export function canPrepareRechargeRestart(
  currentOrder: RechargeStateSource | null | undefined,
  storedOrderNo: string | null | undefined,
  restartOrderNo: string,
) {
  if (storedOrderNo && storedOrderNo !== restartOrderNo) return false;
  if (currentOrder?.order_no && currentOrder.order_no !== restartOrderNo && rechargeBlocksNewOrder(currentOrder)) return false;
  return true;
}

export function isRegisteredBankCardStatus(status: string) {
  return (REGISTERED_BANK_CARD_STATUSES as readonly string[]).includes(status);
}

export function luhnCheckCardNumber(cardNumber: string) {
  const digits = cardNumber.replace(/\D/g, "");
  if (digits.length < 12 || digits.length > 19) return false;
  let sum = 0;
  for (let index = 0; index < digits.length; index += 1) {
    let digit = Number(digits[digits.length - 1 - index]);
    if (index % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
  }
  return sum % 10 === 0;
}
