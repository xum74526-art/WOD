type StaleTtlCacheOptions<Arguments extends unknown[], Value> = {
  key: (...args: Arguments) => string;
  load: (...args: Arguments) => Promise<Value>;
  ttlMs: number;
  maxEntries: number;
  maxConcurrentLoads?: number;
  maxQueuedLoads?: number;
  queueWaitMs?: number;
  staleMs?: number;
  retryDelayMs?: number;
  shouldStore?: (value: Value) => boolean;
  refreshMode?: "background" | "blocking";
  now?: () => number;
};

type CacheEntry<Value> = {
  value: Value;
  expiresAt: number;
  staleUntil: number;
};

type RetryOutcome<Value> =
  | { ok: true; value: Value }
  | { ok: false; error: unknown };

type RetryEntry<Value> = {
  until: number;
  outcome?: RetryOutcome<Value>;
};

type QueuedLoad<Value> = {
  load: () => Promise<Value>;
  resolve: (value: Value) => void;
  reject: (error: unknown) => void;
  timeout?: ReturnType<typeof setTimeout>;
};

const DEFAULT_MAX_CONCURRENT_LOADS = 16;
const DEFAULT_QUEUE_WAIT_MS = 10_000;

function boundedInteger(value: number | undefined, fallback: number, minimum: number) {
  if (value == null) return fallback;
  const rounded = Math.floor(value);
  return Number.isFinite(rounded) ? Math.max(minimum, rounded) : fallback;
}

function loadCapacityError(reason: "full" | "timeout") {
  const error = new Error(
    reason === "full"
      ? "stale TTL cache load queue is full"
      : "stale TTL cache load queue wait timed out",
  );
  error.name = "StaleTtlCacheLoadCapacityError";
  return error;
}

export function createStaleTtlCache<Arguments extends unknown[], Value>({
  key: keyFor,
  load,
  ttlMs,
  maxEntries,
  maxConcurrentLoads,
  maxQueuedLoads,
  queueWaitMs,
  staleMs = Number.POSITIVE_INFINITY,
  retryDelayMs = 0,
  shouldStore = () => true,
  refreshMode = "background",
  now = Date.now,
}: StaleTtlCacheOptions<Arguments, Value>) {
  const values = new Map<string, CacheEntry<Value>>();
  const refreshes = new Map<string, Promise<Value>>();
  const retries = new Map<string, RetryEntry<Value>>();
  const capacity = Math.max(1, Math.floor(maxEntries));
  const freshFor = Math.max(0, ttlMs);
  const staleFor = Math.max(0, staleMs);
  const retryAfterFailure = Math.max(0, retryDelayMs);
  const concurrentLoadLimit = boundedInteger(
    maxConcurrentLoads,
    Math.min(DEFAULT_MAX_CONCURRENT_LOADS, capacity),
    1,
  );
  const queuedLoadLimit = boundedInteger(maxQueuedLoads, capacity, 0);
  const queueWaitFor = boundedInteger(queueWaitMs, DEFAULT_QUEUE_WAIT_MS, 0);
  const queuedLoads: QueuedLoad<Value>[] = [];
  let activeLoads = 0;

  function startLoad(queued: QueuedLoad<Value>) {
    if (queued.timeout) clearTimeout(queued.timeout);
    activeLoads += 1;
    void Promise.resolve()
      .then(queued.load)
      .then(queued.resolve, queued.reject)
      .finally(() => {
        activeLoads -= 1;
        const next = queuedLoads.shift();
        if (next) startLoad(next);
      });
  }

  function scheduleLoad(loadValue: () => Promise<Value>) {
    return new Promise<Value>((resolve, reject) => {
      const queued: QueuedLoad<Value> = { load: loadValue, resolve, reject };
      if (activeLoads < concurrentLoadLimit) {
        startLoad(queued);
        return;
      }
      if (queuedLoadLimit === 0 || queuedLoads.length >= queuedLoadLimit) {
        reject(loadCapacityError("full"));
        return;
      }
      queuedLoads.push(queued);
      queued.timeout = setTimeout(() => {
        const index = queuedLoads.indexOf(queued);
        if (index < 0) return;
        queuedLoads.splice(index, 1);
        reject(loadCapacityError("timeout"));
      }, queueWaitFor);
    });
  }

  function store(key: string, value: Value) {
    const expiresAt = now() + freshFor;
    values.delete(key);
    values.set(key, { value, expiresAt, staleUntil: expiresAt + staleFor });
    retries.delete(key);
    while (values.size > capacity) {
      const oldestKey = values.keys().next().value;
      if (oldestKey == null) break;
      values.delete(oldestKey);
      retries.delete(oldestKey);
    }
  }

  function delayRetry(key: string, outcome?: RetryOutcome<Value>) {
    if (retryAfterFailure <= 0) return;
    retries.delete(key);
    retries.set(key, { until: now() + retryAfterFailure, outcome });
    while (retries.size > capacity) {
      const oldestKey = retries.keys().next().value;
      if (oldestKey == null) break;
      retries.delete(oldestKey);
    }
  }

  return async function read(...args: Arguments): Promise<Value> {
    const key = keyFor(...args);
    const currentTime = now();
    let cached = values.get(key);
    if (cached && cached.staleUntil <= currentTime) {
      values.delete(key);
      cached = undefined;
    }
    if (cached && cached.expiresAt > currentTime) {
      values.delete(key);
      values.set(key, cached);
      return cached.value;
    }
    const delayed = retries.get(key);
    if (delayed && delayed.until > currentTime) {
      if (cached) return cached.value;
      if (delayed.outcome?.ok) return delayed.outcome.value;
      if (delayed.outcome) throw delayed.outcome.error;
    } else if (delayed) {
      retries.delete(key);
    }

    const activeRefresh = refreshes.get(key);
    if (activeRefresh) {
      if (!cached) return activeRefresh;
      if (refreshMode === "blocking") {
        try {
          const refreshed = await activeRefresh;
          return shouldStore(refreshed) ? refreshed : cached.value;
        } catch (error) {
          if (cached.staleUntil > now()) return cached.value;
          if (values.get(key) === cached) values.delete(key);
          delayRetry(key, { ok: false, error });
          throw error;
        }
      }
      return cached.value;
    }

    const refresh = scheduleLoad(() => load(...args))
      .then((value) => {
        if (shouldStore(value)) store(key, value);
        else delayRetry(key, values.has(key) ? undefined : { ok: true, value });
        return value;
      })
      .catch((error) => {
        delayRetry(key, values.has(key) ? undefined : { ok: false, error });
        throw error;
      });
    const trackedRefresh = refresh.finally(() => {
      if (refreshes.get(key) === trackedRefresh) refreshes.delete(key);
    });
    refreshes.set(key, trackedRefresh);

    if (cached) {
      if (refreshMode === "blocking") {
        try {
          const refreshed = await trackedRefresh;
          return shouldStore(refreshed) ? refreshed : cached.value;
        } catch (error) {
          if (cached.staleUntil > now()) return cached.value;
          if (values.get(key) === cached) values.delete(key);
          delayRetry(key, { ok: false, error });
          throw error;
        }
      }
      void trackedRefresh.catch(() => undefined);
      return cached.value;
    }
    return trackedRefresh;
  };
}
