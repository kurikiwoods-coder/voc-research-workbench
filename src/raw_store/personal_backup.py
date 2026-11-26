"""Create and check a read-only SQLite snapshot before a Personal v9 migration."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from src.edition_policy import Edition
from src.raw_store.runtime_binding import APPLICATION_IDS, MARKER, personal_directory
from src.raw_store.store import SQLITE_TIMEOUT, configure_workspace_connection


def require_personal_v9(db):
    if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_IDS[Edition.PERSONAL]:
        raise ValueError("备份源或副本并非个人工作库。")
    if db.execute("PRAGMA user_version").fetchone()[0] != 9:
        raise ValueError("此备份只接受个人版 v9 工作库。")


def backup_personal_v9(source, destination):
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

    with TemporaryDirectory(prefix="voc-v9-backup-", dir=parent) as scratch:
        staged = Path(scratch) / "backup.sqlite3"
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=SQLITE_TIMEOUT)) as db:
            db.execute("BEGIN")
            require_personal_v9(db)
            with closing(sqlite3.connect(staged, timeout=SQLITE_TIMEOUT)) as copy:
                db.backup(copy)
                configure_workspace_connection(copy)
                require_personal_v9(copy)
                if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise sqlite3.IntegrityError("SQLite 备份完整性检查失败。")
                if copy.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise sqlite3.IntegrityError("SQLite 备份外键检查失败。")
                if copy.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                    raise sqlite3.OperationalError("SQLite 备份未能转为独立文件。")
        os.link(staged, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        backup_personal_v9(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
    print("Personal v9 SQLite snapshot and checks complete.")


if __name__ == "__main__":
    main()
