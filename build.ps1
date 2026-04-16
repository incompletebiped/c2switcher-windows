# build.ps1 - Build c2switcher.exe and install it to %LOCALAPPDATA%\Programs\Common
#
# Usage:
#   .\build.ps1                # build + install + Start Menu shortcut
#   .\build.ps1 -NoShortcut   # skip Start Menu shortcut creation
#   .\build.ps1 -AddToPath    # also add install dir to user PATH (persistent)
#
# Produces: %LOCALAPPDATA%\Programs\Common\c2switcher.exe
# Run as admin to place the Start Menu shortcut in C:\ProgramData (all users).

param(
    [switch]$NoShortcut,
    [switch]$AddToPath
)

$ErrorActionPreference = 'Stop'

$InstallDir        = "$env:LOCALAPPDATA\Programs\Common"
$ExeName           = 'c2switcher.exe'
$AllUsersStartMenu = 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs'
$UserStartMenu     = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"

# Use the local pyinstaller from the project's Scripts directory
$PyInstaller = Join-Path $PSScriptRoot 'Scripts\pyinstaller.exe'
if (-not (Test-Path $PyInstaller)) {
    # Fall back to system pyinstaller if the local one doesn't exist
    $PyInstaller = 'pyinstaller'
}

# --- 1. Ensure install directory exists --------------------------------------
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

# --- 2. Build with PyInstaller -----------------------------------------------
Write-Host ""
Write-Host "Building $ExeName via PyInstaller..." -ForegroundColor Cyan
Write-Host "  distpath : $InstallDir"
Write-Host "  workpath : $env:TEMP\c2switcher-build"
Write-Host ""

& $PyInstaller `
    --distpath $InstallDir `
    --workpath "$env:TEMP\c2switcher-build" `
    --noconfirm `
    build.spec

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed (exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "OK  $InstallDir\$ExeName" -ForegroundColor Green

# --- 3. Start Menu shortcut --------------------------------------------------
if (-not $NoShortcut) {
    $isAdmin = ([Security.Principal.WindowsPrincipal] `
        [Security.Principal.WindowsIdentity]::GetCurrent() `
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if ($isAdmin) {
        $lnkDir = $AllUsersStartMenu
    } else {
        $lnkDir = $UserStartMenu
        Write-Host ""
        Write-Host "Note: not running as admin - shortcut will be in your user Start Menu." -ForegroundColor Yellow
        Write-Host "      Re-run as admin for the all-users Start Menu." -ForegroundColor Yellow
    }

    if (-not (Test-Path $lnkDir)) {
        New-Item -ItemType Directory -Path $lnkDir -Force | Out-Null
    }

    $lnkPath = "$lnkDir\Claude Switcher.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $lnk = $wsh.CreateShortcut($lnkPath)
    $lnk.TargetPath       = "$InstallDir\$ExeName"
    $lnk.WorkingDirectory = $InstallDir
    $lnk.IconLocation     = "$InstallDir\$ExeName,0"
    $lnk.Description      = 'Claude Code Account Switcher'
    $lnk.Save()

    Write-Host "OK  $lnkPath" -ForegroundColor Green
}

# --- 5. Optional: add install dir to user PATH (persistent) ------------------
if ($AddToPath) {
    $userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
    if ($userPath -notlike "*$InstallDir*") {
        [Environment]::SetEnvironmentVariable('PATH', "$userPath;$InstallDir", 'User')
        Write-Host "OK  Added $InstallDir to user PATH." -ForegroundColor Green
        Write-Host "    Restart your terminal for the change to take effect." -ForegroundColor Yellow
    } else {
        Write-Host "    $InstallDir is already in user PATH." -ForegroundColor Green
    }
}

# --- Summary -----------------------------------------------------------------
Write-Host ""
Write-Host "Build complete." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Exe      : $InstallDir\$ExeName"
if (-not $NoShortcut) {
    Write-Host "  Shortcut : Start Menu -> Claude Switcher"
}
Write-Host ""
Write-Host "To also add the install dir to your PATH run:" -ForegroundColor Gray
Write-Host "  .\build.ps1 -AddToPath" -ForegroundColor White
Write-Host ""
