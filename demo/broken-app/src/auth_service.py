"""Auth service — handles user authentication.

BUG: Connection pool is hardcoded to 10 max connections.
Under load (>10 concurrent logins), new connections are rejected
with ConnectionError, causing 500s on POST /api/v1/auth/login.

This is the bug SentinelAI will find and fix.
"""

import time
from dataclasses import dataclass


@dataclass
class ConnectionPool:
    """Database connection pool with a hardcoded limit."""

    max_connections: int = 10  # BUG: too low for production traffic
    active_connections: int = 0
    timeout_seconds: int = 5

    def acquire(self):
        if self.active_connections >= self.max_connections:
            raise ConnectionError(
                f"Connection pool exhausted: {self.active_connections}/{self.max_connections} "
                f"connections in use. Cannot acquire new connection."
            )
        self.active_connections += 1
        return self

    def release(self):
        if self.active_connections > 0:
            self.active_connections -= 1


# Global pool — shared across all request handlers
_pool = ConnectionPool()


def authenticate_user(username: str, password: str) -> dict:
    """Authenticate a user against the database.

    Acquires a connection from the pool, queries the database,
    and returns the user session.
    """
    conn = _pool.acquire()
    try:
        # Simulate database query
        time.sleep(0.1)
        if username == "admin" and password == "secret":
            return {"user_id": 1, "username": "admin", "token": "tok_abc123"}
        raise ValueError("Invalid credentials")
    finally:
        _pool.release()


def get_pool_status() -> dict:
    """Return current connection pool status."""
    return {
        "active_connections": _pool.active_connections,
        "max_connections": _pool.max_connections,
        "utilization": f"{_pool.active_connections / _pool.max_connections:.0%}",
    }
