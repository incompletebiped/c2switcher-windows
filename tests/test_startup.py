"""The command registered to start the tray with Windows."""

from __future__ import annotations

import sys

import pytest

from c2switcher.presentation.tray import startup


@pytest.fixture
def not_frozen(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)


def test_frozen_build_registers_itself(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    exe = tmp_path / 'c2switcher.exe'
    assert startup.startup_command(str(exe)) == f'"{exe}"'


def test_venv_layout_uses_the_console_script(not_frozen, tmp_path):
    """python.exe alone would open a Python prompt at login, not the tray."""
    scripts = tmp_path / 'Scripts'
    scripts.mkdir()
    (scripts / 'c2switcher.exe').touch()

    command = startup.startup_command(str(scripts / 'python.exe'))

    assert command == f'"{scripts / "c2switcher.exe"}"'
    assert 'python.exe' not in command


def test_base_install_layout_finds_scripts_subdirectory(not_frozen, tmp_path):
    scripts = tmp_path / 'Scripts'
    scripts.mkdir()
    (scripts / 'c2switcher.exe').touch()

    command = startup.startup_command(str(tmp_path / 'python.exe'))

    assert command == f'"{scripts / "c2switcher.exe"}"'


def test_falls_back_to_module_invocation(not_frozen, tmp_path):
    """No console script installed — running the module still starts the tray."""
    python = tmp_path / 'python.exe'
    assert startup.startup_command(str(python)) == f'"{python}" -m c2switcher'


def test_command_is_quoted_for_paths_with_spaces(not_frozen, tmp_path):
    root = tmp_path / 'Program Files' / 'Python'
    (root / 'Scripts').mkdir(parents=True)
    (root / 'Scripts' / 'c2switcher.exe').touch()

    command = startup.startup_command(str(root / 'python.exe'))

    assert command.startswith('"') and command.endswith('"')
    assert 'Program Files' in command
