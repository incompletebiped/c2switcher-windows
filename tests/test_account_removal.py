"""Removing an account, including the rows that reference it."""

from __future__ import annotations

import pytest

from c2switcher.data import store as store_mod


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(store_mod, 'C2SWITCHER_DIR', tmp_path)
    db = store_mod.Store(tmp_path / 'store.db')
    yield db
    db.conn.close()


def _insert_account(store, uuid: str, index_num: int, email: str) -> None:
    with store.conn:
        store.conn.execute(
            'INSERT INTO accounts (uuid, index_num, email, credentials_json) VALUES (?, ?, ?, ?)',
            (uuid, index_num, email, '{}'),
        )
    store._load_all_caches()


def _count(store, table: str) -> int:
    return store.conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


USAGE = {
    'five_hour': {'utilization': 12.0},
    'seven_day': {'utilization': 5.0},
    'seven_day_opus': {'utilization': 0.0},
    'seven_day_sonnet': {'utilization': 1.0},
}


def test_account_with_usage_history_can_be_removed(store):
    """usage_history's foreign key rejected the delete outright, so any account that
    had ever been listed became permanently undeletable."""
    _insert_account(store, 'uuid-a', 0, 'a@example.com')
    store.save_usage('uuid-a', USAGE)
    assert _count(store, 'usage_history') == 1

    store.delete_account('uuid-a')

    assert _count(store, 'accounts') == 0
    assert _count(store, 'usage_history') == 0


def test_account_without_usage_can_still_be_removed(store):
    _insert_account(store, 'uuid-a', 0, 'a@example.com')
    store.delete_account('uuid-a')
    assert _count(store, 'accounts') == 0


def test_only_the_target_accounts_usage_is_deleted(store):
    _insert_account(store, 'uuid-a', 0, 'a@example.com')
    _insert_account(store, 'uuid-b', 1, 'b@example.com')
    store.save_usage('uuid-a', USAGE)
    store.save_usage('uuid-b', USAGE)

    store.delete_account('uuid-a')

    rows = store.conn.execute('SELECT account_uuid FROM usage_history').fetchall()
    assert [r[0] for r in rows] == ['uuid-b']


def test_remaining_accounts_are_reindexed_from_zero(store):
    for i, uuid in enumerate(('uuid-a', 'uuid-b', 'uuid-c')):
        _insert_account(store, uuid, i, f'{uuid}@example.com')

    store.delete_account('uuid-a')

    rows = store.conn.execute('SELECT uuid, index_num FROM accounts ORDER BY index_num').fetchall()
    assert [tuple(r) for r in rows] == [('uuid-b', 0), ('uuid-c', 1)]


def test_round_robin_pointer_is_cleared(store):
    """A dangling pointer would keep the balancer referencing a removed account."""
    _insert_account(store, 'uuid-a', 0, 'a@example.com')
    store.set_round_robin_last('overall', 'uuid-a')
    assert store.get_round_robin_last('overall') == 'uuid-a'

    store.delete_account('uuid-a')

    assert store.get_round_robin_last('overall') is None
