"""Conservative local-account pacing; this is quota state, never an article cache.

Every cooperating lookup process uses one user-level ledger, including different
keys/worktrees. Other applications, OS users and machines cannot be observed.
429 responses therefore impose a shared cooldown. No entitlement is inferred.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import sqlite3
import time


class MassiveRateLimiter:
    requests_per_minute = 5

    def __init__(self, path: Path | None = None, *, clock=None, monotonic=None, sleep=None):
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state"))
        self.path = Path(path) if path is not None else base / "ibkr-trading-system" / "massive-rate.sqlite3"
        self._clock = clock or time.time
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep

    def _connect(self, remaining):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=max(0.0, min(0.1, remaining)), isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS starts (at REAL NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS cooldown (id INTEGER PRIMARY KEY, until_at REAL NOT NULL)")
            return connection
        except BaseException:
            connection.close()
            raise

    def acquire(self, deadline_s: float) -> str | None:
        """Atomically charge a request immediately before HTTP; never refund errors."""
        while True:
            remaining = deadline_s - self._monotonic()
            if remaining <= 0:
                return "rate_limit_deadline"
            connection = None
            try:
                connection = self._connect(remaining)
                now = float(self._clock())
                if not math.isfinite(now):
                    return "rate_limiter_unavailable"
                # Future records are retained after a clock rollback: fail closed.
                connection.execute("DELETE FROM starts WHERE at <= ?", (now - 60.001,))
                starts = [row[0] for row in connection.execute("SELECT at FROM starts ORDER BY at")]
                cooldown = connection.execute("SELECT until_at FROM cooldown WHERE id=1").fetchone()
                ready = max(now, cooldown[0] if cooldown else now)
                if len(starts) >= self.requests_per_minute:
                    ready = max(ready, starts[-self.requests_per_minute] + 60.001)
                if ready <= now:
                    if self._monotonic() >= deadline_s:
                        return "rate_limit_deadline"
                    connection.execute("INSERT INTO starts(at) VALUES(?)", (now,))
                    connection.commit()
                    return None
                delay = ready - now
                connection.rollback()
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    return "rate_limiter_unavailable"
                delay = 0.05
            except (OSError, sqlite3.Error, ValueError):
                return "rate_limiter_unavailable"
            finally:
                if connection is not None:
                    connection.close()
            remaining = deadline_s - self._monotonic()
            if delay >= remaining:
                return "rate_limit_deadline"
            self._sleep(min(delay, 0.1))

    def cooldown(self, seconds: float = 60.0) -> bool:
        """Persist a 429 cooldown for all cooperating local account clients."""
        connection = None
        try:
            connection = self._connect(0.1)
            duration = max(60.001, float(seconds))
            if not math.isfinite(duration):
                duration = 60.001
            until = self._clock() + duration
            connection.execute("INSERT INTO cooldown(id,until_at) VALUES(1,?) "
                               "ON CONFLICT(id) DO UPDATE SET until_at=MAX(until_at,excluded.until_at)", (until,))
            connection.commit()
            return True
        except (OSError, sqlite3.Error, ValueError):
            return False
        finally:
            if connection is not None:
                connection.close()
