export const PAYOUT_RECEIPT_MIME_TYPES = ["image/jpeg", "image/png", "application/pdf"] as const;
export const PAYOUT_RECEIPT_ACCEPT = PAYOUT_RECEIPT_MIME_TYPES.join(",");
export const PAYOUT_RECEIPT_HELP_TEXT = "支持 JPG、PNG、PDF，最大 5MB";

export function canViewPayoutReceipt(withdrawal: { status: string; receipt_available: boolean }) {
  return withdrawal.status === "paid" && withdrawal.receipt_available;
}
