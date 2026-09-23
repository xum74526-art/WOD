export type RechargeUiState =
  | "pending"
  | "processing"
  | "success"
  | "refund_pending"
  | "refund_unknown"
  | "refunded"
  | "failed"
  | "expired"
  | "canceled";

export type RechargeStateSource = {
  order_no?: string | null;
  status?: string | null;
  credited_at?: string | null;
  amount_cny?: number | string | null;
  channel?: string | null;
  can_pay?: boolean | null;
  can_query?: boolean | null;
  can_cancel?: boolean | null;
  provider?: string | null;
};

export type RechargeRefundRequestState = {
  status?: string | null;
};

export const REGISTERED_BANK_CARD_STATUSES = ["registered", "pending_review", "active"] as const;
export const MIN_RECHARGE_AMOUNT_CNY = 10;
export const MIN_WITHDRAWAL_CARD_HOURS = 10;

function configuredMinimum(value: unknown, floor: number) {
  const configured = Number(value);
  return Number.isFinite(configured) ? Math.max(floor, configured) : floor;
}

export function minimumRechargeAmountCny(value?: number | null) {
  return configuredMinimum(value, MIN_RECHARGE_AMOUNT_CNY);
}

export function minimumWithdrawalCardHours(value?: number | null) {
  return configuredMinimum(value, MIN_WITHDRAWAL_CARD_HOURS);
}

export function rechargeUiState(order?: RechargeStateSource | null): RechargeUiState {
  const status = String(order?.status || "").trim().toLowerCase();
  if (status === "refund_pending") return "refund_pending";
  if (status === "refund_unknown") return "refund_unknown";
  if (status === "refunded") return "refunded";
  if (order?.credited_at) return "success";
  if (status === "paid" || status === "review" || status === "late_paid_review") return "processing";
  if (status === "failed") return "failed";
  if (status === "expired") return "expired";
  if (status === "canceled" || status === "cancelled") return "canceled";
  return "pending";
}

export function rechargeUiLabel(order?: RechargeStateSource | null) {
  const state = rechargeUiState(order);
  if (state === "processing" && String(order?.status || "").trim().toLowerCase() === "late_paid_review") {
    return "超时到账复核中";
  }
  return {
    pending: "等待支付",
    processing: "支付确认中",
    success: "充值成功",
    refund_pending: "退款提交中",
    refund_unknown: "结果待核验",
    refunded: "已退款",
    expired: "支付已过期",
    failed: "支付失败",
    canceled: "已取消",
  }[state];
}

export function rechargeCanPay(order?: RechargeStateSource | null) {
  return order?.can_pay === true && rechargeUiState(order) === "pending";
}

export function rechargeCanQuery(order?: RechargeStateSource | null) {
  if (order?.can_query !== true) return false;
  const state = rechargeUiState(order);
  return state !== "success"
    && state !== "refund_pending"
    && state !== "refund_unknown"
    && state !== "refunded"
    && state !== "canceled";
}

export function rechargeCanCancel(order?: RechargeStateSource | null) {
  if (order?.can_cancel !== true || order.credited_at) return false;
  const status = String(order.status || "").trim().toLowerCase();
  return status !== "paid"
    && status !== "review"
    && status !== "late_paid_review"
    && status !== "refund_pending"
    && status !== "refund_unknown"
    && status !== "refunded"
    && status !== "canceled"
    && status !== "cancelled";
}

export function rechargeBlocksNewOrder(order?: RechargeStateSource | null) {
  if (!order) return false;
  const state = rechargeUiState(order);
  return state === "pending" || state === "processing";
}

/** Only the same amount and payment channel count as a duplicate active recharge. */
export function rechargeMatchesActiveOrder(
  order: RechargeStateSource | null | undefined,
  amountCny: number,
  paymentType: "alipay" | "wxpay",
) {
  if (!rechargeBlocksNewOrder(order)) return false;
  const existingAmount = Number(order?.amount_cny);
  return Number.isFinite(existingAmount)
    && Math.round(existingAmount * 100) === Math.round(amountCny * 100)
    && String(order?.channel || "").trim().toLowerCase() === paymentType;
}

export function rechargeCanRestart(order?: RechargeStateSource | null) {
  if (!order) return false;
  const state = rechargeUiState(order);
  return state === "failed" || state === "expired" || state === "canceled";
}

export function rechargeCanRequestRefund(order?: RechargeStateSource | null) {
  if (!order || String(order.provider || "").trim().toLowerCase() !== "qixiangpay") return false;
  const status = String(order.status || "").trim().toLowerCase();
  if (status === "review" || status === "late_paid_review") return true;
  return status === "paid" && Boolean(order.credited_at);
}

export function rechargeRefundRequestLabel(request?: RechargeRefundRequestState | null) {
  return {
    pending_review: "待平台审核",
    approved: "审核已通过",
    processing: "退款处理中",
    rejected: "申请已驳回",
    canceled: "申请已取消",
    succeeded: "退款已完成",
    failed: "退款失败",
  }[String(request?.status || "").trim().toLowerCase()] || "状态未知";
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
