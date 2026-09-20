const reviewStatuses = new Set(["review", "late_paid_review"]);

const paymentStatusLabels: Record<string, string> = {
  pending: "等待支付",
  paid: "已支付并入账",
  expired: "已过期",
  failed: "支付失败",
  review: "待支付复核",
  late_paid_review: "超时到账复核",
  canceled: "已取消",
  refund_pending: "原路退款提交中",
  refund_unknown: "原路退款结果待核验",
  refunded: "已原路退款",
};

const refundStatusLabels: Record<string, string> = {
  preparing: "退款准备中",
  submitting: "已提交支付渠道",
  unknown: "渠道结果待核验",
  succeeded: "原路退款成功",
  failed: "原路退款失败",
};

const refundRequestStatusLabels: Record<string, string> = {
  pending_review: "待审核",
  approved: "已批准",
  processing: "退款处理中",
  rejected: "已驳回",
  canceled: "已取消",
  succeeded: "退款成功",
  failed: "退款失败",
};

const activeRefundRequestStatuses = new Set(["pending_review", "approved", "processing"]);

export function paymentStatusLabel(status: string) {
  return paymentStatusLabels[status] || status;
}

export function paymentRefundStatusLabel(status: string) {
  return refundStatusLabels[status] || status;
}

export function paymentRefundRequestStatusLabel(status: string) {
  return refundRequestStatusLabels[status] || status;
}

export function paymentStatusTone(status: string) {
  if (["paid", "refunded", "succeeded"].includes(status)) return "approved";
  if (["failed", "expired", "canceled", "rejected"].includes(status)) return "rejected";
  return "pending_review";
}

export function adminRechargeActions(status: string, refundStatus?: string | null, provider = "qixiangpay", refundRequestStatus?: string | null) {
  const reviewable = reviewStatuses.has(status);
  const hasActiveRefundRequest = refundRequestStatus ? activeRefundRequestStatuses.has(refundRequestStatus) : false;
  const refundable = provider === "qixiangpay"
    && (reviewable || status === "paid")
    && (!refundStatus || refundStatus === "failed")
    && !hasActiveRefundRequest;
  return { canCredit: reviewable, canRefund: refundable };
}

export function canResolveUnknownPaymentRefund(status: string) {
  return status === "unknown";
}

export function canReviewPaymentRefundRequest(status: string) {
  return status === "pending_review";
}
