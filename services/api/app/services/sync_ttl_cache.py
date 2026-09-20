from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import Condition, RLock
import time
from typing import Callable, Generic, Hashable, TypeVar, cast


_Key = TypeVar("_Key", bound=Hashable)
_Value = TypeVar("_Value")


class SyncTtlCacheOverloadedError(RuntimeError):
    """Raised when the bounded loader queue has no remaining capacity."""


class SyncTtlCache(Generic[_Key, _Value]):
    """Bounded process-local TTL cache with synchronous single-flight.

    The leader runs the loader in its current request thread. Followers wait on
    the same Future and never use the leader's database session. Leaders for
    different keys share a bounded execution pool and wait in a bounded queue,
    preventing a request burst from starting an unbounded number of loaders.
    Values are copied at the cache boundary so callers cannot mutate a shared
    snapshot.
    """

    def __init__(
        self,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
        max_concurrent_loads: int = 16,
        max_pending_loads: int = 64,
        max_queue_wait_seconds: float = 10.0,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self.max_concurrent_loads = max(1, int(max_concurrent_loads))
        self.max_pending_loads = max(0, int(max_pending_loads))
        self.max_queue_wait_seconds = max(0.0, float(max_queue_wait_seconds))
        self._clock = clock
        self._lock = RLock()
        self._load_capacity = Condition(self._lock)
        self._entries: OrderedDict[_Key, tuple[float, _Value]] = OrderedDict()
        self._inflight: dict[_Key, Future[_Value]] = {}
        self._active_loads = 0
        self._pending_loads = 0

    def _acquire_load_slot(self) -> None:
        with self._load_capacity:
            if self._active_loads < self.max_concurrent_loads:
                self._active_loads += 1
                return
            if self._pending_loads >= self.max_pending_loads:
                raise SyncTtlCacheOverloadedError(
                    "cache loader capacity is full; retry shortly"
                )

            self._pending_loads += 1
            try:
                available = self._load_capacity.wait_for(
                    lambda: self._active_loads < self.max_concurrent_loads,
                    timeout=self.max_queue_wait_seconds,
                )
                if not available:
                    raise SyncTtlCacheOverloadedError(
                        "cache loader queue wait timed out; retry shortly"
                    )
                self._active_loads += 1
            finally:
                self._pending_loads -= 1

    def _release_load_slot(self) -> None:
        with self._load_capacity:
            self._active_loads -= 1
            self._load_capacity.notify()

    def get_or_load(
        self,
        key: _Key,
        ttl_seconds: float,
        loader: Callable[[], _Value],
    ) -> _Value:
        missing = object()
        cached_snapshot: object = missing
        flight: Future[_Value] | None = None
        leader = False
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > self._clock():
                self._entries.move_to_end(key)
                cached_snapshot = cached[1]
            elif cached:
                self._entries.pop(key, None)

            if cached_snapshot is missing:
                flight = self._inflight.get(key)
                leader = flight is None
                if flight is None:
                    flight = Future()
                    self._inflight[key] = flight

        if cached_snapshot is not missing:
            return deepcopy(cast(_Value, cached_snapshot))

        assert flight is not None
        if not leader:
            return deepcopy(flight.result())

        load_slot_acquired = False
        try:
            self._acquire_load_slot()
            load_slot_acquired = True
            snapshot = deepcopy(loader())
        except BaseException as error:
            with self._lock:
                if self._inflight.get(key) is flight:
                    self._inflight.pop(key, None)
            flight.set_exception(error)
            raise
        else:
            with self._lock:
                self._entries[key] = (self._clock() + max(float(ttl_seconds), 0.1), snapshot)
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
                if self._inflight.get(key) is flight:
                    self._inflight.pop(key, None)
            flight.set_result(snapshot)
            return deepcopy(snapshot)
        finally:
            if load_slot_acquired:
                self._release_load_slot()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
