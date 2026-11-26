"""Provision an isolated Personal study from the trusted local shell."""

import argparse
import json
from pathlib import Path
from uuid import UUID, uuid4

from src.dashboard.study_api import ProjectInput
from src.edition_policy import Edition
from src.raw_store.store import Store
from src.raw_store.studies import StudyStore


def provision(directory, name, topic, request_key):
    if not directory.is_absolute():
        raise ValueError("请提供个人版专用的绝对目录路径。")
    form = ProjectInput(name=name, scope={"mode": "open", "topic": topic})
    studies = StudyStore(Store(directory, edition=Edition.PERSONAL))
    project = studies.create(str(request_key), form.metadata(), form.snapshot(), form.change_note)
    scope = studies.freeze(project["study_id"], project["scope"]["scope_id"])["scope"]
    return {key: scope[key] for key in ("study_id", "scope_id", "scope_version", "frozen_at")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--request-key", type=UUID, default=uuid4())
    args = parser.parse_args()
    try:
        binding = provision(args.directory, args.name, args.topic, args.request_key)
    except (ValueError, OSError):
        parser.exit(2, "无法创建个人研究项目。请核对目录、项目名称和研究问题。\n")
    print(json.dumps(binding, ensure_ascii=False))


if __name__ == "__main__":
    main()
