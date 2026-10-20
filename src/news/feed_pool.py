"""Runtime-owned bounded RSS transport single-flight/cache, not a news engine."""
from collections import OrderedDict
import threading
import time


class SharedFeedPool:
    def __init__(self, *, limit=4, capacity=128, ttl=120., failure_backoff=120., stop=None, stop_requested=None):
        self.slots = threading.BoundedSemaphore(limit)
        self.capacity, self.ttl, self.failure_backoff = capacity, ttl, failure_backoff
        self.stop = stop or threading.Event()
        self.stop_requested = stop_requested or (lambda:False)
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.pending = {}
        self.hits = self.requests = 0

    def cancelled(self):
        return self.stop.is_set() or self.stop_requested()

    def fetch(self, url, timeout, loader):
        deadline = time.monotonic() + timeout
        while True:
            if self.cancelled():
                raise RuntimeError('news maintenance stopped')
            with self.lock:
                cached = self.cache.get(url)
                if cached and time.monotonic() < cached[0]:
                    self.hits += 1
                    self.cache.move_to_end(url)
                    return {**cached[1], '_response': None, 'transport_cache_hit': True}
                pending = self.pending.get(url)
                if pending is None:
                    pending = self.pending[url] = threading.Event()
                    break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('shared feed wait deadline')
            pending.wait(min(.05, remaining))
        acquired = False
        try:
            while not acquired:
                if self.cancelled():
                    raise RuntimeError('news maintenance stopped')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('shared feed slot deadline')
                acquired = self.slots.acquire(timeout=min(.05, remaining))
            with self.lock:
                self.requests += 1
            result = loader(max(.001, deadline-time.monotonic()))
            cached_result = {**result, '_response': None, 'transport_cache_hit': False}
            with self.lock:
                ttl = self.failure_backoff if result.get('error') is not None else self.ttl
                self.cache[url] = (time.monotonic()+ttl, cached_result)
                self.cache.move_to_end(url)
                while len(self.cache) > self.capacity:
                    self.cache.popitem(last=False)
            return {**result, 'transport_cache_hit': False}
        finally:
            if acquired:
                self.slots.release()
            with self.lock:
                self.pending.pop(url, None)
                pending.set()
