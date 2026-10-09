export const PAYMENT_CACHE_KEYS = [
  'wod-pending-recharge-order',
  'wod-recharge-request-intent',
  'wod-withdrawal-request-intent',
] as const
const OWNER_KEY = 'wod-payment-cache-owner'

interface PaymentStorage {
  getStorageSync(key: string): unknown
  setStorageSync(key: string, value: unknown): void
  removeStorageSync(key: string): void
}

export interface PaymentAccount {
  userId: number | null | undefined
  token: string
}

function validOwner(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

/** Remove local recovery data only. Server orders and balances are untouched. */
export function clearPaymentAccountStorage(storage: PaymentStorage): void {
  const owner = storage.getStorageSync(OWNER_KEY)
  for (const key of PAYMENT_CACHE_KEYS) {
    storage.removeStorageSync(key)
    if (validOwner(owner)) storage.removeStorageSync(`${key}:user:${owner}`)
  }
  storage.removeStorageSync(OWNER_KEY)
}

/** Capture the account before an async operation; never write a late result into its successor. */
export function createPaymentAccountStorage(storage: PaymentStorage, currentAccount: () => PaymentAccount) {
  const account = { ...currentAccount() }
  const isCurrent = () => {
    const current = currentAccount()
    return validOwner(account.userId) && Boolean(account.token)
      && current.userId === account.userId && current.token === account.token
  }
  // Old versions stored unowned global values. Do not adopt them into whichever
  // account happens to sign in after an upgrade.
  for (const key of PAYMENT_CACHE_KEYS) storage.removeStorageSync(key)
  if (isCurrent()) storage.setStorageSync(OWNER_KEY, account.userId)
  const scoped = (key: string) => `${key}:user:${account.userId}`
  return {
    isCurrent,
    getStorageSync: (key: string): unknown => isCurrent() ? storage.getStorageSync(scoped(key)) : null,
    setStorageSync(key: string, value: unknown) {
      if (isCurrent()) storage.setStorageSync(scoped(key), value)
    },
    removeStorageSync(key: string) {
      if (isCurrent()) storage.removeStorageSync(scoped(key))
    },
  }
}
