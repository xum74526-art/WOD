export type AccountDeletionBlocker = { code: string; message: string; count: number };
export type AccountDeletionEligibility = {
  eligible: boolean;
  blockers: AccountDeletionBlocker[];
  automatic_actions: string[];
};
export type AccountDeletionVerification = { ticket: string; expires_at: string; receipt_expires_at?: string };
export type AccountDeletionStatus = {
  status: "verified" | "blocked" | "processing" | "completed";
  blockers: AccountDeletionBlocker[];
  completed_at: string | null;
};

// This is a deletion-only receipt, never a normal login/access token. Store it
// only after the user's final confirmation so an uncertain response is recoverable.
export const DELETION_RECEIPT_KEY = "wod.account-deletion.receipt.v1";
const RECEIPT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
export type DeletionReceipt = { ticket: string; expiresAt: number; verifyExpiresAt?: number };
type ReceiptStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function newDeletionReceipt(verification: AccountDeletionVerification, now = Date.now()): DeletionReceipt {
  const serverExpiry = Date.parse(verification.receipt_expires_at || "");
  const verificationExpiry = Date.parse(verification.expires_at);
  return {
    ticket: verification.ticket,
    expiresAt: Number.isFinite(serverExpiry)
      ? Math.min(serverExpiry, now + RECEIPT_MAX_AGE_MS)
      : now + RECEIPT_MAX_AGE_MS,
    ...(Number.isFinite(verificationExpiry) ? { verifyExpiresAt: verificationExpiry } : {}),
  };
}

export function readDeletionReceipt(storage: ReceiptStorage, now = Date.now()): DeletionReceipt | null {
  const raw = storage.getItem(DELETION_RECEIPT_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<DeletionReceipt>;
    if (typeof value.ticket === "string" && /^[A-Za-z0-9_-]{40,128}$/.test(value.ticket)
      && typeof value.expiresAt === "number" && Number.isFinite(value.expiresAt)
      && value.expiresAt > now && value.expiresAt <= now + RECEIPT_MAX_AGE_MS) {
      return {
        ticket: value.ticket, expiresAt: value.expiresAt,
        ...(typeof value.verifyExpiresAt === "number" && Number.isFinite(value.verifyExpiresAt) ? { verifyExpiresAt: value.verifyExpiresAt } : {}),
      };
    }
  } catch { /* Invalid or expired receipts are removed without exposing their content. */ }
  // Another tab may have replaced the value after this read. Do not remove a
  // newer receipt while cleaning up an invalid/expired snapshot.
  if (storage.getItem(DELETION_RECEIPT_KEY) === raw) storage.removeItem(DELETION_RECEIPT_KEY);
  return null;
}

export function saveDeletionReceipt(storage: ReceiptStorage, receipt: DeletionReceipt) {
  storage.setItem(DELETION_RECEIPT_KEY, JSON.stringify(receipt));
}

export function clearDeletionReceipt(storage: ReceiptStorage, ticket: string) {
  const raw = storage.getItem(DELETION_RECEIPT_KEY);
  if (!raw || !ticket) return;
  try {
    const saved = JSON.parse(raw) as { ticket?: unknown };
    if (saved?.ticket === ticket && storage.getItem(DELETION_RECEIPT_KEY) === raw) {
      storage.removeItem(DELETION_RECEIPT_KEY);
    }
  } catch { /* Invalid receipt cleanup belongs to readDeletionReceipt, not a different request's result. */ }
}

export function deletionRevokesNormalSession(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const status = (value as { status?: unknown }).status;
  return status === "processing" || status === "completed";
}

/** A timeout is not failure or success: ask the server using the same receipt.
 * Never automatically re-submit a destructive operation when checking status. */
export async function submitDeletionWithRecovery(
  ticket: string,
  submit: (ticket: string) => Promise<AccountDeletionStatus>,
  status: (ticket: string) => Promise<AccountDeletionStatus>,
): Promise<AccountDeletionStatus> {
  try {
    return await submit(ticket);
  } catch {
    return await status(ticket);
  }
}
