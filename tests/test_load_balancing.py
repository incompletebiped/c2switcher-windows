"""Scoring and selection rules in core.load_balancing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from c2switcher.constants import FIVE_HOUR_ROTATION_CAP
from c2switcher.core.load_balancing import (
    build_candidate,
    needs_refresh,
    select_best_candidate,
    select_top_similar_candidates,
)
from c2switcher.core.models import Account, UsageSnapshot, UsageWindow


def _resets_in(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _account(index: int = 0) -> Account:
    return Account(
        uuid=f'uuid-{index}',
        index_num=index,
        email=f'user{index}@example.com',
        credentials_json='{}',
    )


def _usage(
    *,
    five_hour: float | None = 0.0,
    seven_day: float | None = 0.0,
    sonnet: float | None = 0.0,
    reset_hours: float = 100.0,
    cache_source: str = 'cache',
    cache_age: float = 0.0,
) -> UsageSnapshot:
    resets_at = _resets_in(reset_hours)
    return UsageSnapshot(
        account_uuid='uuid-0',
        five_hour=UsageWindow(utilization=five_hour, resets_at=resets_at),
        seven_day=UsageWindow(utilization=seven_day, resets_at=resets_at),
        seven_day_opus=UsageWindow(utilization=0.0, resets_at=resets_at),
        seven_day_sonnet=UsageWindow(utilization=sonnet, resets_at=resets_at),
        queried_at=datetime.now(timezone.utc).isoformat(),
        cache_source=cache_source,
        cache_age_seconds=cache_age,
    )


def _candidate(index=0, **usage_kwargs):
    return build_candidate(_account(index), _usage(**usage_kwargs), burst_buffer=4.0, active_sessions=0, recent_sessions=0)


# ── build_candidate ──────────────────────────────────────────────────────────


def test_fully_exhausted_account_is_not_a_candidate():
    assert _candidate(seven_day=99.5, sonnet=99.5) is None


def test_sonnet_exhausted_falls_back_to_overall_window():
    candidate = _candidate(seven_day=40.0, sonnet=99.5)
    assert candidate.window == 'overall'
    assert candidate.tier == 2


def test_overall_exhausted_falls_back_to_sonnet_window():
    candidate = _candidate(seven_day=99.5, sonnet=40.0)
    assert candidate.window == 'sonnet'
    assert candidate.tier == 1


def test_null_utilization_is_treated_as_unused_not_exhausted():
    """The API intermittently returns nulls; those must not read as 100%."""
    candidate = _candidate(seven_day=None, sonnet=None)
    assert candidate is not None
    assert candidate.utilization == 0.0


def test_drain_rate_is_headroom_over_hours_to_reset():
    candidate = _candidate(seven_day=49.0, reset_hours=10.0)
    assert candidate.drain_rate == pytest.approx(5.0, rel=0.05)


def test_hot_five_hour_window_scales_the_score_down():
    cool = _candidate(seven_day=50.0, five_hour=10.0)
    hot = _candidate(seven_day=50.0, five_hour=95.0)
    assert hot.five_hour_factor < cool.five_hour_factor
    assert hot.adjusted_drain < cool.adjusted_drain


def test_burst_blocking_flags_accounts_near_the_ceiling():
    assert _candidate(seven_day=91.0).burst_blocked is True   # 91 + 4 buffer >= 94
    assert _candidate(seven_day=50.0).burst_blocked is False


# ── select_best_candidate ────────────────────────────────────────────────────


def test_no_candidates_selects_nothing():
    assert select_best_candidate([]) is None


def test_prefers_the_higher_adjusted_drain():
    low = _candidate(0, seven_day=90.0, reset_hours=100.0)
    high = _candidate(1, seven_day=10.0, reset_hours=10.0)
    assert select_best_candidate([low, high]) is high


def test_burst_blocked_accounts_are_skipped_when_alternatives_exist():
    blocked = _candidate(0, seven_day=91.0, reset_hours=1.0)  # huge drain, but blocked
    usable = _candidate(1, seven_day=50.0, reset_hours=100.0)
    assert blocked.burst_blocked and not usable.burst_blocked
    assert select_best_candidate([blocked, usable]) is usable


def test_burst_blocked_account_is_used_when_it_is_the_only_option():
    blocked = _candidate(0, seven_day=91.0)
    assert select_best_candidate([blocked]) is blocked


def test_hot_five_hour_accounts_are_skipped_when_a_cool_one_exists():
    hot = _candidate(0, seven_day=10.0, five_hour=FIVE_HOUR_ROTATION_CAP + 1)
    cool = _candidate(1, seven_day=80.0, five_hour=5.0)
    assert select_best_candidate([hot, cool]) is cool


# ── select_top_similar_candidates ────────────────────────────────────────────


def test_similar_candidates_group_for_round_robin():
    a = _candidate(0, seven_day=10.0, reset_hours=10.0)
    b = _candidate(1, seven_day=10.0, reset_hours=10.0)
    far = _candidate(2, seven_day=90.0, reset_hours=100.0)
    similar = select_top_similar_candidates([a, b, far])
    assert {c.account.uuid for c in similar} == {'uuid-0', 'uuid-1'}


def test_similar_candidates_never_cross_tiers():
    overall = _candidate(0, seven_day=50.0, sonnet=10.0)
    sonnet = _candidate(1, seven_day=99.5, sonnet=50.0)
    similar = select_top_similar_candidates([overall, sonnet])
    assert {c.tier for c in similar} == {similar[0].tier}


def test_empty_list_groups_to_nothing():
    assert select_top_similar_candidates([]) == []


# ── needs_refresh ────────────────────────────────────────────────────────────


def test_live_usage_is_never_refreshed():
    assert needs_refresh(_candidate(seven_day=50.0, cache_source='live', cache_age=999)) is False


def test_stale_cache_is_refreshed():
    assert needs_refresh(_candidate(seven_day=50.0, cache_age=120)) is True


def test_fresh_cache_on_a_slow_account_is_kept():
    assert needs_refresh(_candidate(seven_day=50.0, reset_hours=1000.0, cache_age=5)) is False


def test_high_drain_account_refreshes_sooner():
    high_drain = _candidate(seven_day=10.0, reset_hours=5.0, cache_age=15)
    assert high_drain.priority_score >= 1.0
    assert needs_refresh(high_drain) is True
