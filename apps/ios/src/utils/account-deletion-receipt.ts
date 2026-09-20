import { DELETION_RECEIPT_KEY, validDeletionReceipt, type DeletionReceipt, type DeletionResult } from './account-deletion'

// One-shot, in-memory server-confirmed completion notice. No capability or
// identity is retained here; it survives only the reLaunch that clears pages.
let completedNotice: Pick<DeletionResult, 'status' | 'completed_at'> | null = null

export function rememberDeletionCompletion(result: DeletionResult) {
  if (result.status === 'completed') completedNotice = { status: 'completed', completed_at: result.completed_at }
}

export function consumeDeletionCompletion() {
  const result = completedNotice
  completedNotice = null
  return result
}

export function readDeletionReceipt(): DeletionReceipt | null {
  const receipt = validDeletionReceipt(uni.getStorageSync(DELETION_RECEIPT_KEY))
  if (!receipt) clearDeletionReceipt()
  return receipt
}

export function saveDeletionReceipt(receipt: DeletionReceipt) {
  uni.setStorageSync(DELETION_RECEIPT_KEY, receipt)
}

export function clearDeletionReceipt(ticket?: string) {
  // A delayed response for account A must not erase account B's newer receipt.
  if (ticket && uni.getStorageSync(DELETION_RECEIPT_KEY)?.ticket !== ticket) return
  uni.removeStorageSync(DELETION_RECEIPT_KEY)
}
