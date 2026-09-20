export type ClientRequestIntent = {
  fingerprint: string;
  requestId: string;
};

type IntentStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const CLIENT_REQUEST_ID = /^[A-Za-z0-9._:-]{8,64}$/;

export function clientRequestFingerprint(parts: readonly (string | number)[]) {
  return JSON.stringify(parts);
}

export function ensureClientRequestIntent(
  current: ClientRequestIntent | null,
  fingerprint: string,
  prefix: string,
  createUuid: () => string = () => crypto.randomUUID(),
): ClientRequestIntent {
  if (
    current?.fingerprint === fingerprint
    && CLIENT_REQUEST_ID.test(current.requestId)
  ) {
    return current;
  }
  const requestId = `${prefix}-${createUuid()}`;
  if (!CLIENT_REQUEST_ID.test(requestId)) {
    throw new Error("无法生成有效的请求标识，请刷新页面后重试");
  }
  return { fingerprint, requestId };
}

export function readClientRequestIntent(storage: IntentStorage, key: string): ClientRequestIntent | null {
  try {
    const value = JSON.parse(storage.getItem(key) || "null") as Partial<ClientRequestIntent> | null;
    if (
      typeof value?.fingerprint === "string"
      && typeof value.requestId === "string"
      && CLIENT_REQUEST_ID.test(value.requestId)
    ) {
      return { fingerprint: value.fingerprint, requestId: value.requestId };
    }
  } catch {
    // A malformed or unavailable session value is treated as absent. The
    // in-memory intent still protects retries during the current render.
  }
  return null;
}

export function saveClientRequestIntent(storage: IntentStorage, key: string, intent: ClientRequestIntent) {
  try {
    storage.setItem(key, JSON.stringify(intent));
  } catch {
    // Some privacy modes disable session storage. The caller also keeps the
    // same intent in a ref, so a retry during this render remains idempotent.
  }
}

export function clearClientRequestIntent(storage: IntentStorage, key: string) {
  try {
    storage.removeItem(key);
  } catch {
    // Clearing best-effort browser state must not turn a successful mutation
    // into a visible failure.
  }
}
