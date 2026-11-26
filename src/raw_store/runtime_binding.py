"""Keep edition-specific runtime files and SQLite copies in their original domain."""

import os
from pathlib import Path

from src.edition_policy import Edition


MARKER = ".voc-personal"
APPLICATION_IDS = {Edition.BUSINESS: 0, Edition.PERSONAL: 0x564F4350}


def personal_directory(directory):
    if os.name == "nt":
        home = os.environ.get("LOCALAPPDATA")
        if not home or Path(home).resolve() not in directory.parents:
            raise ValueError("个人版本机运行目录须位于当前用户的 LOCALAPPDATA 下。")
    else:
        info = directory.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("个人版本机运行目录须由当前用户拥有，并且仅限该用户访问。")


def bind_directory(directory, edition):
    directory = Path(directory).resolve()
    if any(os.path.lexists(parent / MARKER) for parent in directory.parents):
        raise ValueError("运行目录不能嵌套于已绑定的个人工作区。")
    marker = directory / MARKER
    if edition == Edition.BUSINESS:
        if os.path.lexists(marker):
            raise ValueError("个人工作区不能作为商用工作区打开。")
        return directory

    if os.name == "nt":
        personal_directory(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        personal_directory(directory)
    if not os.path.lexists(marker):
        if any(directory.iterdir()):
            raise ValueError("请为个人版使用独立空目录，或此前已绑定的个人工作目录。")
        try:
            with marker.open("xb") as handle:
                handle.write(b"PERSONAL\n")
        except FileExistsError:
            pass
    if marker.is_symlink() or not marker.is_file() or marker.read_bytes() != b"PERSONAL\n":
        raise ValueError("个人工作区标识无效。")
    return directory
