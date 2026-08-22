"""State-directory resolution and the error shown when it can't be opened."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import c2switcher.constants as constants
from c2switcher.core.errors import C2SwitcherError, StoreUnavailable


@pytest.fixture
def reloaded_constants(monkeypatch):
    """Re-import constants under a patched environment, then restore it."""

    def _load(**env):
        for key in ('C2SWITCHER_HOME', 'APPDATA'):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(constants)

    yield _load
    importlib.reload(constants)


def test_home_override_wins(reloaded_constants, tmp_path):
    mod = reloaded_constants(C2SWITCHER_HOME=str(tmp_path / 'portable'), APPDATA=str(tmp_path / 'roaming'))
    assert mod.C2SWITCHER_DIR == tmp_path / 'portable'
    assert mod.DB_PATH == tmp_path / 'portable' / 'store.db'


def test_home_override_expands_user(reloaded_constants):
    mod = reloaded_constants(C2SWITCHER_HOME='~/c2switcher-state')
    assert '~' not in str(mod.C2SWITCHER_DIR)
    assert mod.C2SWITCHER_DIR == Path.home() / 'c2switcher-state'


def test_falls_back_to_appdata(reloaded_constants, tmp_path):
    mod = reloaded_constants(APPDATA=str(tmp_path / 'roaming'))
    assert mod.C2SWITCHER_DIR == tmp_path / 'roaming' / 'c2switcher'


def test_falls_back_to_home_without_appdata(reloaded_constants):
    mod = reloaded_constants()
    assert mod.C2SWITCHER_DIR == Path.home() / '.c2switcher'


def test_every_state_path_follows_the_override(reloaded_constants, tmp_path):
    root = tmp_path / 'portable'
    mod = reloaded_constants(C2SWITCHER_HOME=str(root))
    for name in ('DB_PATH', 'LOCK_PATH', 'HEADERS_PATH', 'LB_STATE_PATH', 'THEME_PREF_PATH', 'STATUS_CACHE_PATH'):
        assert getattr(mod, name).parent == root, name


def test_credentials_path_is_not_affected(reloaded_constants, tmp_path):
    """Claude Code owns ~/.claude — the override must not move it."""
    mod = reloaded_constants(C2SWITCHER_HOME=str(tmp_path / 'portable'))
    assert mod.CREDENTIALS_PATH == Path.home() / '.claude' / '.credentials.json'


def test_unopenable_store_raises_a_domain_error(monkeypatch, tmp_path):
    """A bare sqlite error says nothing about the directory being the problem."""
    import sqlite3

    from c2switcher.data import store as store_mod

    monkeypatch.setattr(store_mod, 'C2SWITCHER_DIR', tmp_path)

    def _refuse(*args, **kwargs):
        raise sqlite3.OperationalError('unable to open database file')

    monkeypatch.setattr(store_mod.sqlite3, 'connect', _refuse)

    with pytest.raises(StoreUnavailable) as excinfo:
        store_mod.Store(tmp_path / 'store.db')

    message = str(excinfo.value)
    assert 'C2SWITCHER_HOME' in message
    assert str(tmp_path / 'store.db') in message
    assert isinstance(excinfo.value, C2SwitcherError)
