"""Atomic, local-only configuration. Callers serialize changes with Store.writer."""

import json
import os
from pathlib import Path
import stat
import tempfile


class VaultError(RuntimeError):
    pass


def windows_protect(data, encrypt):
    import ctypes as c
    from ctypes import wintypes as w

    class Blob(c.Structure):
        _fields_ = [("size", w.DWORD), ("data", c.POINTER(c.c_ubyte))]

    source = (c.c_ubyte * len(data)).from_buffer_copy(data)
    incoming, outgoing = Blob(len(data), source), Blob()
    dll = c.WinDLL("crypt32", use_last_error=True)
    crypt = dll.CryptProtectData if encrypt else dll.CryptUnprotectData
    crypt.argtypes = [
        c.POINTER(Blob), w.LPCWSTR if encrypt else c.POINTER(w.LPWSTR),
        c.POINTER(Blob), c.c_void_p, c.c_void_p, w.DWORD, c.POINTER(Blob),
    ]
    crypt.restype = w.BOOL
    if not crypt(c.byref(incoming), None, None, None, None, 1, c.byref(outgoing)):
        raise VaultError("Windows 当前用户无法读取或保护此凭证库。")
    release = c.WinDLL("kernel32").LocalFree
    release.argtypes = [c.c_void_p]
    release.restype = c.c_void_p
    try:
        return c.string_at(outgoing.data, outgoing.size)
    finally:
        release(outgoing.data)


class CredentialVault:
    def __init__(self, directory):
        self.directory = Path(directory) / "credentials"
        self.path = self.directory / "local-api.json"

    def _check(self, path, directory=False):
        info = path.lstat()
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected(info.st_mode) or (not directory and info.st_nlink != 1):
            raise VaultError("凭证库路径必须是当前工作区的普通目录或文件。")
        if os.name != "nt" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
            raise VaultError("凭证库权限不安全。目录须为 0700，文件须为 0600。")

    def read(self):
        try:
            self._check(self.directory, directory=True)
            self._check(self.path)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            with os.fdopen(os.open(self.path, flags), "rb") as handle:
                raw = handle.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError
            if os.name == "nt":
                raw = windows_protect(raw, encrypt=False)
            payload = json.loads(raw)
            if (
                not isinstance(payload, dict) or payload.get("version") != 1
                or not all(isinstance(payload.get(field), dict) for field in ("keys", "reviews"))
                or any(value is not None and not isinstance(value, str) for value in payload["keys"].values())
                or (payload.get("provider") is not None and not isinstance(payload["provider"], str))
            ):
                raise ValueError
            return payload
        except FileNotFoundError:
            return {"version": 1, "keys": {}, "reviews": {}, "wizard_seen": False}
        except (OSError, ValueError, TypeError, RecursionError):
            raise VaultError("无法读取本机凭证库，请检查当前系统账户及该目录的权限。") from None

    def write(self, payload):
        temporary = None
        try:
            self.directory.mkdir(mode=0o700, exist_ok=True)
            self._check(self.directory, directory=True)
            data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            if os.name == "nt":
                data = windows_protect(data, encrypt=True)
            with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except (OSError, ValueError, TypeError):
            raise VaultError("无法保存本机凭证，请检查磁盘和目录写入权限。") from None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
