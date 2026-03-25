"""Rate limiter — protects API endpoints from abuse.

BUG: The sliding window counter never resets expired entries,
causing memory to grow unbounded and the rate limiter to
incorrectly block legitimate requests after running for hours.
"""

import time
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter with a sliding window."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if a request from client_id is allowed.

        BUG: Never cleans up old entries. Over time, the list grows
        unbounded and the len() check counts expired timestamps,
        eventually blocking all clients.
        """
        now = time.time()
        self._requests[client_id].append(now)

        # BUG: should filter to only count requests within the window
        # but instead counts ALL historical requests
        return len(self._requests[client_id]) <= self.max_requests

    def get_remaining(self, client_id: str) -> int:
        """Return remaining requests allowed for this client."""
        used = len(self._requests[client_id])
        return max(0, self.max_requests - used)
