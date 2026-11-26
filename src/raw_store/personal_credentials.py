"""Local DPAPI credential state. Mutations run under the Personal Store writer lock."""

import json
import os
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile
from uuid import uuid4

from src.edition_policy import REFERENCE, canonical_uuid
from src.raw_store.credentials import VaultError, windows_protect
from src.raw_store.runtime_binding import MARKER, personal_directory


_BINDING_FIELDS = ("provider", "channel_ref", "account_ref", "credential_revision")
_EMPTY = {"version": 1, "configured": False}
_LIMIT = 16 * 1024
_KEY = re.compile(r"[!-~]{1,512}")
_REVISION = re.compile(r"[0-9a-f]{32}")


def _protect(data, *, encrypt):
    if os.name != "nt":
        raise VaultError("个人供应商凭证需要 Windows 当前用户 DPAPI。")
    return windows_protect(data, encrypt=encrypt)


def _check_path(info, *, directory=False, private=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if reparse or not expected(info.st_mode) or (not directory and info.st_nlink != 1):
        raise ValueError
    if private and os.name != "nt" and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError


def _validate_binding(provider, channel_ref, account_ref, api_key):
    if not isinstance(api_key, str) or not _KEY.fullmatch(api_key):
        raise ValueError
    for value in (provider, channel_ref, account_ref):
        if not isinstance(value, str) or not REFERENCE.fullmatch(value) or api_key in value:
            raise ValueError


def _status(payload):
    return {"configured": payload["configured"], **{field: payload.get(field) for field in _BINDING_FIELDS}}


class PersonalCredentials:
    def __init__(self, directory, *, study_id=None, scope_id=None):
        self.directory = Path(directory)
        if (study_id is None) != (scope_id is None) or (
            study_id is not None and (canonical_uuid(study_id) != study_id or canonical_uuid(scope_id) != scope_id)
        ):
            raise ValueError("无效的个人凭证范围。")
        self.scope = f"{study_id}.{scope_id}" if study_id is not None else ""
        suffix = f".{self.scope}" if self.scope else ""
        self.path = self.directory / f"personal-provider{suffix}.dpapi"

    def _check_root(self):
        _check_path(self.directory.lstat(), directory=True)
        personal_directory(self.directory.resolve(strict=True))
        marker = self.directory / MARKER
        info = marker.lstat()
        _check_path(info)
        if info.st_size != len(b"PERSONAL\n") or marker.read_bytes() != b"PERSONAL\n":
            raise ValueError

    def _exists(self, path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        _check_path(info, private=True)
        return True

    def _revision_path(self, revision):
        if not self.scope or not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise VaultError("无效的个人凭证版本。")
        return self.path.with_suffix(f".{revision}.dpapi")

    def read(self, revision=None):
        try:
            self._check_root()
            if self.scope and revision is None:
                return _status(_EMPTY)
            path = self._revision_path(revision) if self.scope else self.path
            if not self._exists(path):
                return _status(_EMPTY)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            with os.fdopen(os.open(path, flags), "rb") as handle:
                data = handle.read(_LIMIT + 1)
            if not 0 < len(data) <= _LIMIT:
                raise ValueError
            payload = json.loads(_protect(data, encrypt=False))
            if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1:
                raise ValueError
            if payload.pop("scope", None) != self.scope:
                raise ValueError
            if payload.get("configured") is False and payload.keys() == _EMPTY.keys():
                return _status(_EMPTY)
            if payload.get("configured") is not True or payload.keys() != {*_EMPTY, *_BINDING_FIELDS, "api_key"}:
                raise ValueError
            _validate_binding(payload["provider"], payload["channel_ref"], payload["account_ref"], payload["api_key"])
            if not _REVISION.fullmatch(payload["credential_revision"]) or (
                self.scope and revision != payload["credential_revision"]
            ):
                raise ValueError
            return _status(payload)
        except (OSError, ValueError, TypeError, RecursionError):
            raise VaultError("无法读取个人供应商凭证，请检查本机工作区及凭证库。") from None

    def put(self, provider, channel_ref, account_ref, api_key):
        try:
            _validate_binding(provider, channel_ref, account_ref, api_key)
        except ValueError:
            raise VaultError("个人供应商凭证或账户、通道引用格式无效。") from None
        payload = {"version": 1, "configured": True, "provider": provider, "channel_ref": channel_ref,
                   "account_ref": account_ref, "credential_revision": uuid4().hex, "api_key": api_key}
        path = self._revision_path(payload["credential_revision"]) if self.scope else self.path
        return self._replace(payload, path)

    def delete(self):
        if self.scope:
            return _status(_EMPTY)
        return self._replace(_EMPTY, self.path)

    def discard_unbound(self, active_revision):
        self._check_root()
        for path in self.directory.glob(f"{self.path.stem}.*.dpapi"):
            revision = path.stem.rsplit(".", 1)[-1]
            if _REVISION.fullmatch(revision) and revision != active_revision and self._exists(path):
                path.unlink(missing_ok=True)

    def _replace(self, payload, path):
        temporary = None
        try:
            self._check_root()
            self._exists(path)
            raw = json.dumps({**payload, "scope": self.scope}, separators=(",", ":")).encode("utf-8")
            encrypted = _protect(raw, encrypt=True)
            with NamedTemporaryFile(dir=self.directory, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        except (OSError, ValueError):
            raise VaultError("无法更新个人供应商凭证，请检查本机磁盘及目录权限。") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        return _status(payload)
