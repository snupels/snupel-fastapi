import time
from collections import OrderedDict


class RateLimiter:
    # ponytail: process-local limits; use a shared store when running multiple API instances.
    def __init__(self, limit: int, window: int = 60, capacity: int = 10_000) -> None:
        self.limit = limit
        self.window = window
        self.capacity = capacity
        self.buckets: OrderedDict[str, tuple[int, float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        current = self.buckets.pop(key, None)
        if current and current[1] > now:
            if current[0] >= self.limit:
                self.buckets[key] = current
                return False
            value = (current[0] + 1, current[1])
        else:
            value = (1, now + self.window)
        if len(self.buckets) >= self.capacity:
            self.buckets.popitem(last=False)
        self.buckets[key] = value
        return True
