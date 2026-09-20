import assert from "node:assert/strict";
import test from "node:test";

import { createStaleTtlCache } from "../lib/stale-ttl-cache.ts";

test("stale TTL cache coalesces concurrent cold loads and serves a fresh value", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], string>({
    key: (identity) => identity,
    load: async (identity) => {
      loads += 1;
      await Promise.resolve();
      return `${identity}-${loads}`;
    },
    ttlMs: 120,
    maxEntries: 4,
    now: () => clock,
  });

  const values = await Promise.all([read("gpu"), read("gpu"), read("gpu")]);
  assert.deepEqual(values, ["gpu-1", "gpu-1", "gpu-1"]);
  assert.equal(await read("gpu"), "gpu-1");
  assert.equal(loads, 1);
  clock += 100;
  assert.equal(await read("gpu"), "gpu-1");
  assert.equal(loads, 1);
});

test("stale TTL cache returns stale data while one refresh updates the value", async () => {
  let clock = 0;
  let loads = 0;
  let finishRefresh: ((value: number) => void) | undefined;
  const read = createStaleTtlCache<[string], number>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      if (loads === 1) return 10;
      return new Promise<number>((resolve) => { finishRefresh = resolve; });
    },
    ttlMs: 120,
    maxEntries: 4,
    now: () => clock,
  });

  assert.equal(await read("gpu"), 10);
  clock = 121;
  assert.equal(await read("gpu"), 10);
  assert.equal(await read("gpu"), 10);
  assert.equal(loads, 2);
  finishRefresh?.(11);
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(await read("gpu"), 11);
  assert.equal(loads, 2);
});

test("stale TTL cache keeps the last success after a failed refresh and permits retry", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], number>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      if (loads === 2) throw new Error("temporary failure");
      return loads;
    },
    ttlMs: 120,
    maxEntries: 4,
    now: () => clock,
  });

  assert.equal(await read("gpu"), 1);
  clock = 121;
  assert.equal(await read("gpu"), 1);
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(await read("gpu"), 1);
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(await read("gpu"), 3);
  assert.equal(loads, 3);
});

test("stale TTL cache does not replace a good value with an incomplete refresh", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], { complete: boolean; value: number }>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      return { complete: loads !== 2, value: loads };
    },
    ttlMs: 100,
    staleMs: 500,
    retryDelayMs: 25,
    shouldStore: (value) => value.complete,
    maxEntries: 4,
    now: () => clock,
  });

  assert.deepEqual(await read("gpu"), { complete: true, value: 1 });
  clock = 101;
  assert.deepEqual(await read("gpu"), { complete: true, value: 1 });
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(loads, 2);
  assert.deepEqual(await read("gpu"), { complete: true, value: 1 });
  assert.equal(loads, 2);
  clock += 26;
  assert.deepEqual(await read("gpu"), { complete: true, value: 1 });
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(await read("gpu"), { complete: true, value: 3 });
  assert.equal(loads, 3);
});

test("stale TTL cache stops serving a value after its stale window", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], number>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      if (loads > 1) throw new Error("offline");
      return 1;
    },
    ttlMs: 100,
    staleMs: 200,
    maxEntries: 4,
    now: () => clock,
  });

  assert.equal(await read("gpu"), 1);
  clock = 301;
  await assert.rejects(() => read("gpu"), /offline/);
  assert.equal(loads, 2);
});

test("stale TTL cache backs off after an incomplete cold load without storing it as fresh", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], { complete: boolean; value: number }>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      return { complete: loads > 1, value: loads };
    },
    ttlMs: 100,
    retryDelayMs: 25,
    shouldStore: (value) => value.complete,
    maxEntries: 4,
    now: () => clock,
  });

  assert.deepEqual(await read("gpu"), { complete: false, value: 1 });
  assert.deepEqual(await read("gpu"), { complete: false, value: 1 });
  assert.equal(loads, 1);
  clock = 26;
  assert.deepEqual(await read("gpu"), { complete: true, value: 2 });
  assert.equal(loads, 2);
});

test("stale TTL cache backs off after a cold error and retries later", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], number>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      if (loads === 1) throw new Error("offline");
      return 2;
    },
    ttlMs: 100,
    retryDelayMs: 25,
    maxEntries: 4,
    now: () => clock,
  });

  await assert.rejects(() => read("gpu"), /offline/);
  await assert.rejects(() => read("gpu"), /offline/);
  assert.equal(loads, 1);
  clock = 26;
  assert.equal(await read("gpu"), 2);
  assert.equal(loads, 2);
});

test("blocking refresh mode coalesces an expired refresh and falls back only on failure", async () => {
  let clock = 0;
  let loads = 0;
  let finishRefresh: ((value: number) => void) | undefined;
  const read = createStaleTtlCache<[string], number>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      if (loads === 1) return 1;
      if (loads === 2) return new Promise<number>((resolve) => { finishRefresh = resolve; });
      throw new Error("offline");
    },
    ttlMs: 100,
    staleMs: 500,
    retryDelayMs: 25,
    refreshMode: "blocking",
    maxEntries: 4,
    now: () => clock,
  });

  assert.equal(await read("gpu"), 1);
  clock = 101;
  const first = read("gpu");
  const second = read("gpu");
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(loads, 2);
  finishRefresh?.(2);
  assert.deepEqual(await Promise.all([first, second]), [2, 2]);

  clock = 202;
  assert.equal(await read("gpu"), 2);
  assert.equal(loads, 3);
  assert.equal(await read("gpu"), 2);
  assert.equal(loads, 3);
});

test("blocking refresh mode rechecks the stale deadline after a failed refresh", async () => {
  let clock = 0;
  let loads = 0;
  const read = createStaleTtlCache<[string], number>({
    key: (identity) => identity,
    load: async () => {
      loads += 1;
      if (loads === 1) return 1;
      clock = 301;
      throw new Error("late failure");
    },
    ttlMs: 100,
    staleMs: 200,
    retryDelayMs: 25,
    refreshMode: "blocking",
    maxEntries: 4,
    now: () => clock,
  });

  assert.equal(await read("gpu"), 1);
  clock = 299;
  await assert.rejects(() => read("gpu"), /late failure/);
  await assert.rejects(() => read("gpu"), /late failure/);
  assert.equal(loads, 2);
  clock = 327;
  await assert.rejects(() => read("gpu"), /late failure/);
  assert.equal(loads, 3);
});

test("stale TTL cache bounds distinct-key loader concurrency and its FIFO queue", async () => {
  const started: string[] = [];
  const running = new Set<string>();
  const finish = new Map<string, () => void>();
  let peakConcurrency = 0;
  const read = createStaleTtlCache<[string], string>({
    key: (identity) => identity,
    load: (identity) => new Promise<string>((resolve) => {
      started.push(identity);
      running.add(identity);
      peakConcurrency = Math.max(peakConcurrency, running.size);
      finish.set(identity, () => {
        running.delete(identity);
        resolve(identity);
      });
    }),
    ttlMs: 100,
    maxEntries: 8,
    maxConcurrentLoads: 2,
    maxQueuedLoads: 2,
    queueWaitMs: 60_000,
  });

  const first = read("first");
  const second = read("second");
  const third = read("third");
  const fourth = read("fourth");
  const overflow = assert.rejects(read("overflow"), /load queue is full/);
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.deepEqual(started, ["first", "second"]);
  assert.equal(peakConcurrency, 2);
  await overflow;

  finish.get("second")?.();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(started, ["first", "second", "third"]);
  assert.equal(peakConcurrency, 2);

  finish.get("first")?.();
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(started, ["first", "second", "third", "fourth"]);
  assert.equal(peakConcurrency, 2);

  finish.get("third")?.();
  finish.get("fourth")?.();
  assert.deepEqual(await Promise.all([first, second, third, fourth]), ["first", "second", "third", "fourth"]);
  assert.equal(running.size, 0);
});

test("stale TTL cache keeps serving stale data when the cross-key queue is saturated", async () => {
  let clock = 0;
  let staleLoads = 0;
  let finishBusy: (() => void) | undefined;
  const read = createStaleTtlCache<[string], string>({
    key: (identity) => identity,
    load: async (identity) => {
      if (identity === "stale") {
        staleLoads += 1;
        return `stale-${staleLoads}`;
      }
      return new Promise<string>((resolve) => {
        finishBusy = () => resolve(identity);
      });
    },
    ttlMs: 10,
    staleMs: 100,
    maxEntries: 4,
    maxConcurrentLoads: 1,
    maxQueuedLoads: 0,
    now: () => clock,
  });

  assert.equal(await read("stale"), "stale-1");
  clock = 11;
  const busy = read("busy");
  await new Promise<void>((resolve) => setImmediate(resolve));

  assert.equal(await read("stale"), "stale-1");
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(staleLoads, 1);

  finishBusy?.();
  assert.equal(await busy, "busy");
});

test("stale TTL cache bounds how long a distinct-key load may wait in the queue", async () => {
  let finishActive: ((value: string) => void) | undefined;
  const read = createStaleTtlCache<[string], string>({
    key: (identity) => identity,
    load: (identity) => identity === "active"
      ? new Promise<string>((resolve) => { finishActive = resolve; })
      : Promise.resolve(identity),
    ttlMs: 100,
    maxEntries: 4,
    maxConcurrentLoads: 1,
    maxQueuedLoads: 1,
    queueWaitMs: 10,
  });

  const active = read("active");
  await new Promise<void>((resolve) => setImmediate(resolve));
  await assert.rejects(read("waiting"), /load queue wait timed out/);

  finishActive?.("active");
  assert.equal(await active, "active");
  assert.equal(await read("waiting"), "waiting");
});
