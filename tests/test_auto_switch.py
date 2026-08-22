"""Rate-limit detection that drives the tray's auto-switch."""

from __future__ import annotations

import pytest

from c2switcher.presentation.tray.monitor import RATE_LIMIT_THRESHOLD, TrayMonitor


@pytest.fixture
def monitor():
    return TrayMonitor(on_data_updated=lambda _accounts: None)


def _account(*, active=True, **windows):
    return {
        'index': 0,
        'uuid': 'uuid-0',
        'nickname': None,
        'email': 'user@example.com',
        'is_active': active,
        'usage': {window: {'utilization': value} for window, value in windows.items()},
    }


def _seed(monitor, accounts):
    with monitor._lock:
        monitor._accounts = accounts


@pytest.mark.parametrize('window', ['five_hour', 'seven_day', 'seven_day_sonnet'])
def test_any_maxed_window_triggers_a_switch(monitor, window):
    """seven_day is the balancer's primary window and has to count here too."""
    _seed(monitor, [_account(**{window: RATE_LIMIT_THRESHOLD})])
    assert monitor._current_account_maxed() is True


def test_headroom_on_every_window_does_not_trigger(monitor):
    _seed(monitor, [_account(five_hour=50.0, seven_day=60.0, seven_day_sonnet=70.0)])
    assert monitor._current_account_maxed() is False


def test_only_the_active_account_is_considered(monitor):
    _seed(monitor, [_account(active=False, seven_day=99.0), _account(active=True, seven_day=10.0)])
    assert monitor._current_account_maxed() is False


def test_null_utilization_is_not_treated_as_maxed(monitor):
    _seed(monitor, [_account(five_hour=None, seven_day=None, seven_day_sonnet=None)])
    assert monitor._current_account_maxed() is False


def test_no_accounts_does_not_trigger(monitor):
    _seed(monitor, [])
    assert monitor._current_account_maxed() is False


def test_switching_needs_somewhere_to_switch_to(monitor):
    _seed(monitor, [_account(seven_day=99.0)])
    assert monitor._has_other_accounts() is False

    _seed(monitor, [_account(seven_day=99.0), _account(active=False, seven_day=10.0)])
    assert monitor._has_other_accounts() is True
