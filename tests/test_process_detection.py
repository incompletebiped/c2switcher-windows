"""Claude Code process identification and the TCP-churn processing heuristic."""

from __future__ import annotations

import pytest

from c2switcher.presentation.tray.monitor import is_claude_code_process, is_claude_processing

CLAUDE_CODE_NATIVE = r'C:\Users\alex\AppData\Roaming\Claude\claude-code\2.1.234\claude.exe'
DESKTOP_APP_STORE = r'C:\Program Files\WindowsApps\Claude_1.32885.1.0_x64__pzs8sxrjxfjjc\app\claude.exe'
DESKTOP_APP_STANDALONE = r'C:\Users\alex\AppData\Local\AnthropicClaude\app-1.0.0\claude.exe'
CHROME_NATIVE_HOST = r'C:\Users\alex\AppData\Roaming\Claude\ChromeNativeHost\chrome-native-host.exe'


@pytest.mark.parametrize(
    'name, exe, cmdline',
    [
        ('claude.exe', CLAUDE_CODE_NATIVE, f'{CLAUDE_CODE_NATIVE} --output-format stream-json'),
        ('node.exe', r'C:\Program Files\nodejs\node.exe', r'node C:\p\node_modules\@anthropic-ai\claude-code\cli.js'),
        ('node.exe', r'C:\Program Files\nodejs\node.exe', 'node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js'),
        ('claude', '/home/alex/.local/share/claude/claude-code/2.1.234/claude', 'claude'),
    ],
)
def test_matches_claude_code(name, exe, cmdline):
    assert is_claude_code_process(name, exe, cmdline) is True


@pytest.mark.parametrize(
    'name, exe, cmdline',
    [
        # The desktop app is also called claude.exe and holds long-lived API
        # connections — matching it pinned the processing lock on permanently.
        ('claude.exe', DESKTOP_APP_STORE, f'{DESKTOP_APP_STORE} --type=renderer'),
        ('claude.exe', DESKTOP_APP_STANDALONE, DESKTOP_APP_STANDALONE),
        ('chrome-native-host.exe', CHROME_NATIVE_HOST, f'{CHROME_NATIVE_HOST} chrome-extension://abc/'),
        # Bystanders matched only because a path component contains "claude"
        ('node.exe', r'C:\Program Files\nodejs\node.exe', r'node C:\Users\alex\Desktop\CLAUDE VCL\server.js'),
        ('bash.exe', r'C:\Program Files\Git\bin\bash.exe', 'bash -c source /c/Users/alex/.claude/shell-snapshot.sh'),
        ('python.exe', r'C:\Python312\python.exe', 'python -c import claude_helper'),
        ('esbuild.exe', r'C:\Users\alex\Desktop\CLAUDE VCL\node_modules\esbuild.exe', 'esbuild --bundle'),
        ('cmd.exe', r'C:\Windows\System32\cmd.exe', r'cmd /c cd "C:\CLAUDE VCL"'),
    ],
)
def test_rejects_non_claude_code(name, exe, cmdline):
    assert is_claude_code_process(name, exe, cmdline) is False


def test_handles_missing_fields():
    assert is_claude_code_process(None, None, None) is False
    assert is_claude_code_process('', '', '') is False


def test_no_pids_reports_idle_and_clears_baseline():
    active, baseline = is_claude_processing([], frozenset({(1, '1.2.3.4', 443)}))
    assert active is False
    assert baseline is None


def test_first_sample_only_establishes_baseline(monkeypatch):
    """A tray started while Claude sits idle must not report a spurious lock."""
    monkeypatch.setattr(
        'c2switcher.presentation.tray.monitor.psutil.net_connections',
        lambda kind='tcp': [_conn(1, '160.79.104.10', 443, 'ESTABLISHED')],
    )

    active, baseline = is_claude_processing([1], None)
    assert active is False
    assert baseline == frozenset({(1, '160.79.104.10', 443)})

    # Same connection set on the next poll is still idle.
    active, baseline = is_claude_processing([1], baseline)
    assert active is False


def test_connection_change_reports_active(monkeypatch):
    conns = [_conn(1, '160.79.104.10', 443, 'ESTABLISHED')]
    monkeypatch.setattr(
        'c2switcher.presentation.tray.monitor.psutil.net_connections',
        lambda kind='tcp': conns,
    )
    _, baseline = is_claude_processing([1], None)

    conns.append(_conn(1, '160.79.104.11', 443, 'ESTABLISHED'))
    active, _ = is_claude_processing([1], baseline)
    assert active is True


def test_loopback_connections_are_ignored(monkeypatch):
    monkeypatch.setattr(
        'c2switcher.presentation.tray.monitor.psutil.net_connections',
        lambda kind='tcp': [_conn(1, '127.0.0.1', 8787, 'ESTABLISHED')],
    )
    _, baseline = is_claude_processing([1], None)
    assert baseline == frozenset()


class _Addr:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


class _Conn:
    def __init__(self, pid, ip, port, status):
        self.pid = pid
        self.raddr = _Addr(ip, port)
        self.status = status


def _conn(pid, ip, port, status):
    return _Conn(pid, ip, port, status)
