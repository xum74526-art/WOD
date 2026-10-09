type PaymentStorage = Pick<Storage, "getItem" | "setItem" | "removeItem" | "key" | "length">;
const OWNER_KEY = "wod-web-payment-owner";
const CACHE_KEYS = [
  "wod-web-pending-recharge",
  "wod-web-recharge-request-intent",
  "wod-web-withdrawal-request-intent",
  "wod-web-refund-request-intent",
];
let generation = 0;

function clearPaymentValues(storage: PaymentStorage | null, legacyOnly = false) {
  if (!storage) return;
  const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index));
  for (const key of keys) {
    if (key && CACHE_KEYS.some((prefix) => key === prefix || key.startsWith(`${prefix}:`))
      && (!legacyOnly || !key.includes(":user:"))) storage.removeItem(key);
  }
}

function browserStorage(kind: "localStorage" | "sessionStorage"): PaymentStorage | null {
  try { return typeof window === "undefined" ? null : window[kind]; } catch { return null; }
}

/** Clear recovery pointers, never server orders or balances. Invalidate late responses first. */
export function clearPaymentAccountStorage(
  local = browserStorage("localStorage"), session = browserStorage("sessionStorage"),
) {
  generation += 1;
  for (const storage of [local, session]) {
    try { clearPaymentValues(storage); storage?.removeItem(OWNER_KEY); } catch { /* Storage may be disabled. */ }
  }
}

export function createPaymentAccountStorage(
  userId: number,
  local = browserStorage("localStorage"), session = browserStorage("sessionStorage"),
  newSession: () => string = () => crypto.randomUUID(),
) {
  let owner: { userId: number; session: string } | null = null;
  try { owner = JSON.parse(local?.getItem(OWNER_KEY) || "null"); } catch { /* Discard unreadable ownership. */ }
  if (owner?.userId !== userId || typeof owner?.session !== "string" || !owner.session) {
    clearPaymentAccountStorage(local, session);
    owner = { userId, session: newSession() };
  }
  const marker = JSON.stringify(owner);
  let ownerPersisted = false;
  try {
    clearPaymentValues(local, true);
    clearPaymentValues(session, true);
    local?.setItem(OWNER_KEY, marker);
    ownerPersisted = Boolean(local && local.getItem(OWNER_KEY) === marker);
  } catch { /* In-memory operation remains possible without persistent storage. */ }
  const accountGeneration = generation;
  let disposed = false;
  const isCurrent = () => {
    if (disposed || generation !== accountGeneration || !Number.isSafeInteger(userId) || userId <= 0) return false;
    try { return !ownerPersisted || local?.getItem(OWNER_KEY) === marker; } catch { return false; }
  };
  const scoped = (storage: PaymentStorage | null) => {
    // Include the login generation so a different tab cannot revive an intent
    // from before logout, even when the same user signs in again.
    const keyFor = (key: string) => `${key}:user:${userId}:${owner.session}`;
    return {
      getItem(key: string) { try { return isCurrent() ? storage?.getItem(keyFor(key)) ?? null : null; } catch { return null; } },
      setItem(key: string, value: string) { try { if (isCurrent()) storage?.setItem(keyFor(key), value); } catch { /* Optional cache. */ } },
      removeItem(key: string) { try { if (isCurrent()) storage?.removeItem(keyFor(key)); } catch { /* Optional cache. */ } },
    };
  };
  return { local: scoped(ownerPersisted ? local : null), session: scoped(ownerPersisted ? session : null), isCurrent, dispose: () => { disposed = true; } };
}

export type PaymentAccountStorage = ReturnType<typeof createPaymentAccountStorage>;
