# build.spec — Single PyInstaller spec → one c2switcher.exe
#
# Use build.ps1 (preferred) — it sets the correct distpath and creates the
# Start Menu shortcut automatically:
#   .\build.ps1              # build + install + shortcut
#   .\build.ps1 -AddToPath   # also add to user PATH
#
# Or build manually (exe lands in dist\ which is gitignored):
#   pip install pyinstaller
#   pyinstaller build.spec
#
# The resulting c2switcher.exe is both the tray app (no args) and the
# CLI tool (c2switcher.exe login / ls / usage / switch / etc.)

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['c2switcher/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('rsrc/icon-spec.svg', 'rsrc'),
        ('rsrc/icon.ico',       'rsrc'),
    ],
    hiddenimports=[
        # PySide6 modules loaded at runtime
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # pystray backends
        'pystray._win32',
        # PIL / Pillow
        'PIL.Image',
        'PIL.ImageDraw',
        # matplotlib backend
        'matplotlib.backends.backend_agg',
        # pandas / numpy runtime
        'pandas',
        'numpy',
        # SQLite
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude large unused GUI toolkits
        'tkinter',
        'wx',
        'PyQt5',
        # Exclude test frameworks
        'pytest',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='c2switcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False: no terminal window flashes when starting as tray app.
    # CLI mode attaches to parent console at runtime via AttachConsole(-1).
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='rsrc/icon.ico',
    # Embed version/manifest
    version_file=None,
    uac_admin=False,
    uac_uiaccess=False,
)
