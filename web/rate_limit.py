"""An in-memory sliding-window rate limiter, bounded in size."""

import time
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable

Clock = Callable[[], float]


class RateLimiter:
    """Allows `limit` hits per `window` seconds for each key. At most `max_keys` keys are
    remembered (the least recently used is dropped first), so memory stays bounded."""

    def __init__(
        self,
        limit: int,
        window: float = 60.0,
        *,
        clock: Clock = time.monotonic,
        max_keys: int = 4096,
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._max_keys = max_keys
        self._hits: OrderedDict[Hashable, deque[float]] = OrderedDict()

    def allow(self, key: Hashable = None) -> bool:
        """Count a hit; False when the key is over its limit (the hit is not counted)."""
        now = self._clock()
        hits = self._hits.pop(key, None)
        if hits is None:
            hits = deque()
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        allowed = len(hits) < self._limit
        if allowed:
            hits.append(now)
        self._hits[key] = hits
        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)
        return allowed

    def __len__(self) -> int:
        return len(self._hits)
