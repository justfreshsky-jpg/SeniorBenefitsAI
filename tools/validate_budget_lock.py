#!/usr/bin/env python3
"""Validate one fresh, authoritative FreshSky budget-lock value."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone


MAX_AGE = timedelta(hours=30)
MAX_FUTURE_SKEW = timedelta(minutes=2)


def is_fresh_open(value: str, *, now: datetime | None = None) -> bool:
    raw = str(value or "").strip()
    if not raw.startswith("open:"):
        return False
    try:
        opened_at = datetime.fromisoformat(
            raw.removeprefix("open:").replace("Z", "+00:00")
        )
    except ValueError:
        return False
    if opened_at.tzinfo is None or opened_at.utcoffset() is None:
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed = opened_at.astimezone(timezone.utc)
    return (
        observed <= current + MAX_FUTURE_SKEW
        and current - observed <= MAX_AGE
    )


def main() -> int:
    if is_fresh_open(sys.stdin.read()):
        return 0
    print(
        "Budget lock is closed, malformed, stale, or future-dated.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
