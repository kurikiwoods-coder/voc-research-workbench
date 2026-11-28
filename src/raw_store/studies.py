"""Project metadata and immutable StudyScope snapshots in the local workspace."""

from contextlib import contextmanager
import hashlib
import json
from uuid import uuid4

from src.raw_store.store import Conflict, dump, now


PROJECT_FIELDS = ("name", "description", "background", "objective", "subject", "status")
PROJECT_COLUMNS = ", ".join(PROJECT_FIELDS)
SORT_COLUMNS = {"updated": "p.updated_at DESC", "created": "p.created_at DESC", "name": "p.name COLLATE NOCASE"}
SCOPE_SELECT = """SELECT s.*, f.frozen_at FROM study_scopes s
    LEFT JOIN study_scope_freezes f ON f.study_id=s.study_id AND f.scope_id=s.scope_id"""


def scope_record(row, *, include_content=True):
    record = {
        "study_id": row["study_id"],
        "scope_id": row["scope_id"],
        "scope_version": f"v{row['version_no']}",
        "created_at": row["created_at"],
        "frozen_at": row["frozen_at"],
        "change_note": row["change_note"],
        "changed_fields": json.loads(row["changed_fields_json"]),
    }
    if include_content:
        record.update(json.loads(row["content_json"]))
    return record


class StudyStore:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def write(self):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    @staticmethod
    def project_row(db, study_id):
        row = db.execute(
            f"""SELECT study_id, {PROJECT_COLUMNS}, revision, created_at, updated_at
                FROM study_projects WHERE study_id=?""",
            (study_id,),
        ).fetchone()
        if row is None:
            raise KeyError(study_id)
        return row

    @staticmethod
    def current_id(db):
        row = db.execute("SELECT study_id FROM study_workspace WHERE slot=1").fetchone()
        return row["study_id"] if row else None

    @staticmethod
    def scope_rows(db, study_id):
        return db.execute(SCOPE_SELECT + " WHERE s.study_id=? ORDER BY s.version_no DESC", (study_id,))

    def detail(self, db, study_id):
        project = dict(self.project_row(db, study_id))
        rows = list(self.scope_rows(db, study_id))
        return {
            **project,
            "is_current": self.current_id(db) == study_id,
            "scope": scope_record(rows[0]),
            "scope_history": [scope_record(row, include_content=False) for row in rows],
        }

    def get(self, study_id):
        with self.store.db() as db:
            db.execute("BEGIN")
            return self.detail(db, study_id)

    def history(self, study_id):
        with self.store.db() as db:
            self.project_row(db, study_id)
            return [scope_record(row, include_content=False) for row in self.scope_rows(db, study_id)]

    def get_scope(self, study_id, scope_id, *, authorize=None):
        with self.store.db() as db:
            if authorize is not None:
                db.execute("BEGIN")
                authorize(db)
            row = db.execute(
                SCOPE_SELECT + " WHERE s.study_id=? AND s.scope_id=?", (study_id, scope_id)
            ).fetchone()
            if row is None:
                raise KeyError(scope_id)
            return scope_record(row)

    def listing(self, query="", status="open", sort="updated"):
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = [
                dict(row)
                for row in db.execute(
                    f"""SELECT p.study_id, p.name, p.subject, p.objective, p.description,
                               p.status, p.created_at, p.updated_at, s.scope_id,
                               s.version_no, json_extract(s.content_json, '$.mode') AS mode,
                               json_extract(s.content_json, '$.topic') AS topic, f.frozen_at
                        FROM study_projects p
                        JOIN study_scopes s ON s.study_id=p.study_id AND s.version_no=(
                            SELECT MAX(version_no) FROM study_scopes WHERE study_id=p.study_id
                        )
                        LEFT JOIN study_scope_freezes f ON f.study_id=s.study_id AND f.scope_id=s.scope_id
                        ORDER BY {SORT_COLUMNS[sort]}, p.study_id"""
                )
            ]
            current_id = self.current_id(db)
        needle = query.casefold()
        projects = []
        current = None
        for row in rows:
            row["scope_version"] = f"v{row.pop('version_no')}"
            if row["study_id"] == current_id:
                current = row
            if not (status == "all" or status == row["status"] or
                    (status == "open" and row["status"] != "archived")):
                continue
            if not needle or any(needle in row[field].casefold() for field in (
                "name", "subject", "objective", "description", "topic"
            )):
                projects.append(row)
        return {"projects": projects, "current": current}

    @staticmethod
    def add_scope(db, study_id, version_no, content, changed_fields, change_note, at):
        db.execute(
            """INSERT INTO study_scopes (study_id, scope_id, version_no, content_json,
                                         changed_fields_json, change_note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (study_id, str(uuid4()), version_no, dump(content), dump(changed_fields), change_note, at),
        )

    def create(self, request_key, fields, scope, note):
        fingerprint = hashlib.sha256(dump([fields, scope, note]).encode("utf-8")).hexdigest()
        with self.write() as db:
            existing = db.execute(
                "SELECT study_id, request_digest FROM study_projects WHERE request_key=?", (request_key,)
            ).fetchone()
            if existing:
                if existing["request_digest"] != fingerprint:
                    raise Conflict("此创建请求已用于另一个表单，请返回项目列表核对。")
                return self.detail(db, existing["study_id"])
            study_id, at = str(uuid4()), now()
            db.execute(
                f"""INSERT INTO study_projects
                    (study_id, request_key, request_digest, {PROJECT_COLUMNS}, revision, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (study_id, request_key, fingerprint, *(fields[key] for key in PROJECT_FIELDS), at, at),
            )
            self.add_scope(db, study_id, 1, scope, [], note, at)
            return self.detail(db, study_id)

    @staticmethod
    def check_edit(row, revision=None):
        if row["status"] == "archived":
            raise Conflict("请恢复此项目后再修改或设为当前项目。")
        if revision is not None and row["revision"] != revision:
            raise Conflict("项目已更新。请重新打开页面核对后再保存。")

    def update(self, study_id, revision, fields, scope, note):
        with self.write() as db:
            row = self.project_row(db, study_id)
            self.check_edit(row, revision)
            previous = next(self.scope_rows(db, study_id))
            old = json.loads(previous["content_json"])
            changed = [field for field in scope if scope[field] != old.get(field)]
            if changed or any(row[key] != value for key, value in fields.items()):
                at = now()
                db.execute(
                    f"""UPDATE study_projects SET {', '.join(key + '=?' for key in PROJECT_FIELDS)},
                        revision=revision+1, updated_at=? WHERE study_id=?""",
                    (*(fields[key] for key in PROJECT_FIELDS), at, study_id),
                )
                if changed:
                    self.add_scope(db, study_id, previous["version_no"] + 1, scope, changed, note, at)
            return self.detail(db, study_id)

    def freeze(self, study_id, scope_id):
        with self.write() as db:
            row = self.project_row(db, study_id)
            self.check_edit(row)
            scope = db.execute(
                SCOPE_SELECT + " WHERE s.study_id=? AND s.scope_id=?", (study_id, scope_id)
            ).fetchone()
            if scope is None:
                raise KeyError(scope_id)
            if scope["frozen_at"]:
                return self.detail(db, study_id)
            if next(self.scope_rows(db, study_id))["scope_id"] != scope_id:
                raise Conflict("仅可冻结当前范围版本，请重新读取项目。")
            at = now()
            db.execute("INSERT INTO study_scope_freezes VALUES (?, ?, ?)", (study_id, scope_id, at))
            db.execute("UPDATE study_projects SET revision=revision+1, updated_at=? WHERE study_id=?", (at, study_id))
            return self.detail(db, study_id)

    def select(self, study_id):
        with self.write() as db:
            row = self.project_row(db, study_id)
            self.check_edit(row)
            db.execute(
                """INSERT INTO study_workspace (slot, study_id) VALUES (1, ?)
                   ON CONFLICT (slot) DO UPDATE SET study_id=excluded.study_id""",
                (study_id,),
            )
            return self.detail(db, study_id)

    def archive(self, study_id, revision):
        with self.write() as db:
            row = self.project_row(db, study_id)
            if row["status"] != "archived":
                self.check_edit(row, revision)
                db.execute(
                    """UPDATE study_projects SET status_before_archive=status, status='archived',
                       revision=revision+1, updated_at=? WHERE study_id=?""",
                    (now(), study_id),
                )
                db.execute("UPDATE study_workspace SET study_id=NULL WHERE study_id=?", (study_id,))
            return self.detail(db, study_id)

    def restore(self, study_id, revision):
        with self.write() as db:
            row = self.project_row(db, study_id)
            if row["status"] == "archived":
                if row["revision"] != revision:
                    raise Conflict("项目已更新，请重新读取归档记录。")
                db.execute(
                    """UPDATE study_projects SET status=status_before_archive, status_before_archive=NULL,
                       revision=revision+1, updated_at=? WHERE study_id=?""",
                    (now(), study_id),
                )
            return self.detail(db, study_id)
