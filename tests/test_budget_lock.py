from datetime import datetime, timedelta, timezone

from tools.validate_budget_lock import is_fresh_open


NOW = datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc)


def test_accepts_only_fresh_open_lock():
    assert is_fresh_open('open:2026-07-30T00:00:00Z', now=NOW)
    assert not is_fresh_open('locked:2026-07-30T00:00:00Z', now=NOW)
    assert not is_fresh_open('throttled:2026-07-30T00:00:00Z', now=NOW)
    assert not is_fresh_open('open', now=NOW)
    assert not is_fresh_open('', now=NOW)


def test_rejects_stale_naive_and_future_lock():
    assert not is_fresh_open(
        f'open:{(NOW - timedelta(hours=31)).isoformat()}',
        now=NOW,
    )
    assert not is_fresh_open('open:2026-07-30T00:00:00', now=NOW)
    assert not is_fresh_open(
        f'open:{(NOW + timedelta(minutes=3)).isoformat()}',
        now=NOW,
    )
