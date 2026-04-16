"""Windows DPAPI credential encryption using ctypes (no extra dependencies).

Encrypts sensitive strings using the current user's Windows master key.
Encrypted values are stored with a 'dpapi:' prefix so plain-text legacy
values can be read transparently and re-encrypted on the next write.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import sys

_PREFIX = 'dpapi:'
_available = sys.platform == 'win32'

if _available:
    class _BLOB(ctypes.Structure):
        _fields_ = [
            ('cbData', ctypes.wintypes.DWORD),
            ('pbData', ctypes.POINTER(ctypes.c_ubyte)),
        ]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext with Windows DPAPI. Returns 'dpapi:<base64>' string."""
    if not _available or not plaintext:
        return plaintext

    data = plaintext.encode('utf-8')
    in_blob = _BLOB(len(data), (ctypes.c_ubyte * len(data))(*data))
    out_blob = _BLOB()

    if not _crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise OSError(f'CryptProtectData failed (error {ctypes.GetLastError()})')

    try:
        return _PREFIX + base64.b64encode(
            bytes(out_blob.pbData[:out_blob.cbData])
        ).decode('ascii')
    finally:
        _kernel32.LocalFree(out_blob.pbData)


def decrypt(ciphertext: str) -> str:
    """Decrypt a DPAPI-encrypted string. Returns plain text unchanged (legacy compat)."""
    if not _available or not ciphertext or not ciphertext.startswith(_PREFIX):
        return ciphertext

    data = base64.b64decode(ciphertext[len(_PREFIX):])
    in_blob = _BLOB(len(data), (ctypes.c_ubyte * len(data))(*data))
    out_blob = _BLOB()

    if not _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise OSError(f'CryptUnprotectData failed (error {ctypes.GetLastError()})')

    try:
        return bytes(out_blob.pbData[:out_blob.cbData]).decode('utf-8')
    finally:
        _kernel32.LocalFree(out_blob.pbData)
