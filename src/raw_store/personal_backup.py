"""Verify SQLite snapshots for Personal v9 and v10 migrations."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from src.edition_policy import Edition
from src.raw_store.runtime_binding import APPLICATION_IDS, MARKER, personal_directory
from src.raw_store.store import SQLITE_TIMEOUT, configure_workspace_connection


def require_personal_version(db, version):
    if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_IDS[Edition.PERSONAL]:
        raise ValueError("备份源或副本并非个人工作库。")
    if db.execute("PRAGMA user_version").fetchone()[0] != version:
        raise ValueError(f"此备份只接受个人版 v{version} 工作库。")


def require_personal_v9(db):
    require_personal_version(db, 9)


def _verified_snapshot(source, staged, version):
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=SQLITE_TIMEOUT)) as db:
        db.execute("BEGIN")
        require_personal_version(db, version)
        with closing(sqlite3.connect(staged, timeout=SQLITE_TIMEOUT)) as copy:
            db.backup(copy)
            configure_workspace_connection(copy)
            require_personal_version(copy, version)
            if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise sqlite3.IntegrityError("SQLite 备份完整性检查失败。")
            if copy.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise sqlite3.IntegrityError("SQLite 备份外键检查失败。")
            if copy.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                raise sqlite3.OperationalError("SQLite 备份未能转为独立文件。")


def _backup_personal(source, destination, version):
    source = Path(source)
    destination = Path(destination)
    if source.name != "connectivity.sqlite3" or source.is_symlink() or not source.is_file():
        raise ValueError("请指定个人工作目录中的 connectivity.sqlite3。")
    source = source.resolve(strict=True)
    personal_directory(source.parent)
    marker = source.parent / MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != b"PERSONAL\n":
        raise ValueError("个人工作目录标识无效。")
    parent = destination.parent.resolve(strict=True)
    personal_directory(parent)
    if parent == source.parent or source.parent in parent.parents:
        raise ValueError("备份目的地须位于独立的私人目录。")
    destination = parent / destination.name
    if os.path.lexists(destination):
        raise FileExistsError("备份目的地已存在。")

    with TemporaryDirectory(prefix=f"voc-v{version}-backup-", dir=parent) as scratch:
        staged = Path(scratch) / "backup.sqlite3"
        _verified_snapshot(source, staged, version)
        os.link(staged, destination)


def backup_personal_v9(source, destination):
    _backup_personal(source, destination, 9)


def backup_personal_v10(source, destination):
    _backup_personal(source, destination, 10)


def restore_personal_v10(snapshot, directory):
    """Restore a checked v10 snapshot into a new private workspace."""
    snapshot = Path(snapshot)
    directory = Path(directory)
    if snapshot.is_symlink() or not snapshot.is_file():
        raise ValueError("请指定独立的 SQLite 备份文件。")
    snapshot = snapshot.resolve(strict=True)
    personal_directory(snapshot.parent)
    parent = directory.parent.resolve(strict=True)
    personal_directory(parent)
    directory = parent / directory.name
    if any(os.path.lexists(path / MARKER) for path in directory.parents):
        raise ValueError("恢复目录不能嵌套于已绑定的个人工作区。")
    if os.path.lexists(directory):
        raise FileExistsError("恢复目标目录已存在。")

    with TemporaryDirectory(prefix="voc-v10-restore-", dir=parent) as scratch:
        staged = Path(scratch) / "connectivity.sqlite3"
        _verified_snapshot(snapshot, staged, 10)
        directory.mkdir(mode=0o700)
        os.link(staged, directory / staged.name)
        with (directory / MARKER).open("xb") as marker:
            marker.write(b"PERSONAL\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--source", type=Path)
    operation.add_argument("--restore-v10", type=Path, metavar="SNAPSHOT")
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--version", type=int, choices=(9, 10), default=9)
    args = parser.parse_args()
    try:
        if args.restore_v10 is not None:
            restore_personal_v10(args.restore_v10, args.destination)
            print("Personal v10 SQLite restore and checks complete.")
            return
        _backup_personal(args.source, args.destination, args.version)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Personal v{args.version} SQLite snapshot and checks complete.")


if __name__ == "__main__":
    main()
