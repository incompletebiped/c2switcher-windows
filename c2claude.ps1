# c2claude.ps1 — Claude Code wrapper with account switching via c2switcher
#
# Usage:
#   c2claude [options] [claude arguments...]
#
# Options:
#   -0, -1, -2       Switch to account by index (0, 1, 2)
#   -a / --account N Switch to account N (by index, nickname, or email)
#   -o / --optimal   Use the optimal account (lowest usage)
#   -c / --cycle     Cycle to the next account
#   (no option)      Load-balanced account selection
#
# Examples:
#   c2claude -0
#   c2claude -a work -p "hi"
#   c2claude --optimal
#   c2claude --cycle

param(
    [string]$a,
    [string]$account,
    [switch]$o,
    [switch]$optimal,
    [switch]$c,
    [switch]$cycle,
    [switch]$0,
    [switch]$1,
    [switch]$2,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

$ErrorActionPreference = 'Stop'

# ── Find c2switcher executable ─────────────────────────────────────────────
$c2s = Get-Command 'c2switcher' -ErrorAction SilentlyContinue
if (-not $c2s) {
    # Try alongside this script (bundled distribution)
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
    $bundled = Join-Path $scriptDir 'c2switcher.exe'
    if (Test-Path $bundled) { $c2s = $bundled } else {
        Write-Error "c2switcher not found. Make sure c2switcher.exe is on PATH."
        exit 1
    }
} else {
    $c2s = $c2s.Source
}

# ── Parse account selection ────────────────────────────────────────────────
$selectedAccount = $null
$useOptimal = $true

if ($PSBoundParameters.ContainsKey('0')) { $selectedAccount = '0'; $useOptimal = $false }
elseif ($PSBoundParameters.ContainsKey('1')) { $selectedAccount = '1'; $useOptimal = $false }
elseif ($PSBoundParameters.ContainsKey('2')) { $selectedAccount = '2'; $useOptimal = $false }
elseif ($a) { $selectedAccount = $a; $useOptimal = $false }
elseif ($account) { $selectedAccount = $account; $useOptimal = $false }
elseif ($o -or $optimal) { $useOptimal = $true }
elseif ($c -or $cycle) {
    & $c2s cycle | Out-Null
    $useOptimal = $false
}

# ── Session tracking ───────────────────────────────────────────────────────
$sessionId = [System.Guid]::NewGuid().ToString()
$pid_ = $PID
$parentPid = (Get-CimInstance Win32_Process -Filter "ProcessId = $PID").ParentProcessId
$cwd = (Get-Location).Path

try {
    & $c2s start-session `
        --session-id $sessionId `
        --pid $pid_ `
        --parent-pid $parentPid `
        --cwd $cwd 2>$null
} catch { <# non-fatal #> }

# ── Get token ─────────────────────────────────────────────────────────────
$env:DISABLE_BUG_COMMAND = '1'
$env:DISABLE_COST_WARNINGS = '1'
$env:DISABLE_TELEMETRY = '1'
$env:CLAUDE_CODE_FORCE_FULL_LOGO = 'true'

if ($useOptimal) {
    $output = & $c2s optimal --session-id $sessionId --token-only --with-label 2>$null
    if ($output -is [array] -and $output.Count -ge 2) {
        $env:C2_ACCOUNT_LABEL = $output[0]
        $env:CLAUDE_CODE_OAUTH_TOKEN = $output[-1]
    } elseif ($output) {
        $env:CLAUDE_CODE_OAUTH_TOKEN = $output
    }
} elseif ($selectedAccount) {
    $output = & $c2s switch $selectedAccount --token-only --with-label 2>$null
    if ($output -is [array] -and $output.Count -ge 2) {
        $env:C2_ACCOUNT_LABEL = $output[0]
        $env:CLAUDE_CODE_OAUTH_TOKEN = $output[-1]
    } elseif ($output) {
        $env:CLAUDE_CODE_OAUTH_TOKEN = $output
    }
}

# ── Run claude ─────────────────────────────────────────────────────────────
try {
    if ($ClaudeArgs) {
        & claude @ClaudeArgs
    } else {
        & claude
    }
    $exitCode = $LASTEXITCODE
} finally {
    # End session regardless of exit
    try {
        & $c2s end-session --session-id $sessionId 2>$null
    } catch { <# non-fatal #> }
}

exit $exitCode
