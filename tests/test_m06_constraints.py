"""Exercise the M06 structural rules directly on isolated SQLite databases."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from src.raw_store.store import Store


NOW = "2026-11-24T00:00:00Z"
QUOTE = "合成😀需求。"
QUOTE_HASH = hashlib.sha256(QUOTE.encode("utf-8")).hexdigest()


def insert(db, table, **values):
    """Make fixture column names explicit and keep values bound."""
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))


def edge_values(study, revision, mention, evidence_id, version, product):
    return {
        "study_id": study, "segment_revision": revision, "mention_id": mention,
        "evidence_id": evidence_id, "catalog_version": version, "product_category_id": product,
    }


def command(db, command_id, study=None, *, key=None, digest=None, operation="fixture"):
    insert(
        db, "m06_command", command_id=command_id, study_id=study,
        namespace=f"study:{study}" if study is not None else "global",
        operation=operation, idempotency_key=key or command_id, input_hash=digest or "a" * 64,
        actor_ref="synthetic-reviewer", reason="synthetic decision", created_at=NOW, result_ref="{}",
    )


def registry(db, version, parent=None, *, seal=False):
    command_id = f"registry-{version}"
    command(db, command_id)
    insert(
        db, "m06_registry", registry_version=version, parent_version=parent,
        created_at=NOW, command_id=command_id, sealed=0,
    )
    if seal:
        seal_registry(db, version)


def seal_registry(db, version):
    db.execute("UPDATE m06_registry SET sealed=1 WHERE registry_version=?", (version,))


class M06DatabaseConstraints(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory(prefix="voc-m06-c1 约束 "))
        self.store = Store(Path(folder))
        self.db = self.enterContext(closing(self.store.connect()))
        self.addCleanup(self.db.rollback)

    def study(self, study, *, with_source=False):
        db = self.db
        scope, file_id, batch, record = (f"{kind}-{study}" for kind in ("scope", "file", "batch", "record"))
        insert(
            db, "study_projects", study_id=study, request_key=f"request-{study}", request_digest="fixture",
            name=study, description="", background="", objective="", subject="", status="draft",
            revision=1, created_at=NOW, updated_at=NOW,
        )
        insert(
            db, "study_scopes", study_id=study, scope_id=scope, version_no=1,
            content_json='{"product_categories":["历史品类"]}', changed_fields_json="[]",
            change_note="", created_at=NOW,
        )
        insert(db, "study_scope_freezes", study_id=study, scope_id=scope, frozen_at=NOW)
        if with_source:
            insert(
                db, "import_files", file_id=file_id, study_id=study, scope_id=scope,
                filename="synthetic.csv", kind="csv", sha256="b" * 64, source_bytes=b"fixture",
                sheets_json="[]", uploaded_at=NOW,
            )
            insert(
                db, "import_batches", batch_id=batch, study_id=study, scope_id=scope, file_id=file_id,
                sheet_index=0, sheet_name="fixture", header_line=1, headers_json="[]",
                mapping_json="{}", privacy="public", signature="fixture", summary_json="{}", created_at=NOW,
            )
            insert(
                db, "import_rows", record_id=record, batch_id=batch, line_number=2, raw_text=QUOTE,
                originals_json="[]", fields_json="{}", status="pending_review", privacy="public",
                issues_json="[]",
            )
            insert(
                db, "corpus_snapshots", record_id=record, study_id=study, scope_id=scope,
                raw_sha256=QUOTE_HASH, created_at=NOW,
            )
        return scope, record

    def product(self, version, product_id, parent=None, *, status="confirmed"):
        insert(
            self.db, "m06_product", registry_version=version, product_category_id=product_id,
            name=product_id, description="", parent_id=parent, status=status, version="1.0.0",
        )

    def task(self, version, category, *, status="confirmed"):
        insert(
            self.db, "m06_task", registry_version=version, category_id=category, name=category,
            definition="", inclusion_criteria="", exclusion_criteria="", discovery="preset",
            lifecycle_status=status, version="1.0.0",
        )

    def intent(self, version, intent_id, *, primary=None, status="confirmed", marker=1):
        insert(
            self.db, "m06_intent", registry_version=version, intent_id=intent_id, name=intent_id,
            definition="", inclusion_criteria="", exclusion_criteria="", lifecycle_status=status,
            primary_category_id=primary, primary_marker=marker,
            survey_validation_status="unvalidated", version="1.0.0",
        )

    def task_edge(self, version, intent_id, category, *, primary=1, status="confirmed"):
        insert(
            self.db, "m06_intent_task", registry_version=version, intent_id=intent_id,
            category_id=category, is_primary=primary, task_status=status,
        )

    def evidence(self, study, evidence_id, start=0, end=1, **overrides):
        values = {
            "study_id": study, "evidence_id": evidence_id, "record_id": f"record-{study}",
            "scope_id": f"scope-{study}", "raw_sha256": QUOTE_HASH, "start_cp": start, "end_cp": end,
        }
        insert(self.db, "m06_evidence", **(values | overrides))

    def segment(self, study, revision, parent=None, **overrides):
        command_id = f"segment-{study}-{revision}"
        command(self.db, command_id, study)
        values = {
            "study_id": study, "segment_revision": revision, "parent_rev": parent,
            "rule_version": "unicode-fixture", "created_at": NOW, "command_id": command_id, "sealed": 0,
        }
        insert(self.db, "m06_segment_rev", **(values | overrides))

    def seal_segment(self, study, revision):
        self.db.execute(
            "UPDATE m06_segment_rev SET sealed=1 WHERE study_id=? AND segment_revision=?",
            (study, revision),
        )

    def mention(self, study, mention):
        insert(self.db, "m06_mention", study_id=study, mention_id=mention, created_at=NOW)

    def member(self, study, revision, mention):
        insert(
            self.db, "m06_member", study_id=study, segment_revision=revision,
            mention_id=mention, identity_state="distinct",
        )

    def support(self, study, revision, mention, evidence_id):
        insert(
            self.db, "m06_support", study_id=study, segment_revision=revision, mention_id=mention,
            evidence_id=evidence_id, segment_no=1, occurrence_basis="original",
            review_ref="fixture-review",
        )

    def mapping(self, study, revision, version, *, previous=None, status="unresolved", reviewer=None):
        command_id = f"mapping-{study}-{revision}"
        command(self.db, command_id, study)
        insert(
            self.db, "m06_scope_binding", study_id=study, scope_id=f"scope-{study}",
            mapping_revision=revision, previous_revision=previous, registry_version=version,
            mapping_status=status, scope_reviewer_ref="scope-review", catalog_reviewer_ref=reviewer,
            basis_ref=f"basis-{revision}", command_id=command_id,
        )

    def scope_product(self, study, revision, version, product):
        insert(
            self.db, "m06_scope_product", study_id=study, scope_id=f"scope-{study}",
            mapping_revision=revision, registry_version=version, product_category_id=product,
        )

    def assert_clean(self):
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_confirmed_intent_refuses_absent_primary_and_null_markers(self):
        registry(self.db, "1.0.0")
        with self.assertRaises(sqlite3.IntegrityError):
            self.intent("1.0.0", "CONFIRMED")
        with self.assertRaises(sqlite3.IntegrityError):
            self.intent("1.0.0", "BAD-MARKER", primary="C", marker=None)
        self.intent("1.0.0", "CANDIDATE", status="pending_parent")
        seal_registry(self.db, "1.0.0")
        self.db.commit()
        self.assert_clean()

    def test_primary_pointer_cannot_commit_without_matching_primary_edge(self):
        registry(self.db, "1.0.0")
        self.task("1.0.0", "C")
        self.intent("1.0.0", "A", primary="C")
        self.task_edge("1.0.0", "A", "C", primary=0)
        violations = self.db.execute("PRAGMA foreign_key_check(m06_intent)").fetchall()
        self.assertEqual([row[2] for row in violations], ["m06_intent_task"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM m06_registry").fetchone()[0], 0)

    def test_two_primary_edges_are_rejected_but_secondary_can_coexist(self):
        registry(self.db, "1.0.0")
        self.task("1.0.0", "C1")
        self.task("1.0.0", "C2")
        self.intent("1.0.0", "A", primary="C1")
        self.task_edge("1.0.0", "A", "C1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.task_edge("1.0.0", "A", "C2")
        self.task_edge("1.0.0", "A", "C2", primary=0)
        self.assertEqual(
            [tuple(row) for row in self.db.execute("SELECT category_id, is_primary FROM m06_intent_task ORDER BY 1")],
            [("C1", 1), ("C2", 0)],
        )

    def test_primary_cannot_use_older_version_or_inactive_task(self):
        registry(self.db, "1.0.0")
        self.task("1.0.0", "OLD")
        seal_registry(self.db, "1.0.0")
        registry(self.db, "2.0.0", "1.0.0")
        self.intent("2.0.0", "A", primary="OLD")
        with self.assertRaises(sqlite3.IntegrityError):
            self.task_edge("2.0.0", "A", "OLD")
        for status in ("candidate", "rejected", "merged", "retired"):
            with self.subTest(status=status):
                self.task("2.0.0", status, status=status)
                with self.assertRaises(sqlite3.IntegrityError):
                    self.task_edge("2.0.0", "A", status)
                with self.assertRaises(sqlite3.IntegrityError):
                    self.task_edge("2.0.0", "A", status, status=status)

    def test_registry_rejects_extra_root_unsealed_parent_fork_and_direct_seal(self):
        registry(self.db, "1.0.0")
        for version, parent in (("1.0.1", None), ("1.0.2", "1.0.0"), ("1.0.3", "1.0.3")):
            with self.subTest(version=version), self.assertRaises(sqlite3.IntegrityError):
                registry(self.db, version, parent)
        seal_registry(self.db, "1.0.0")
        command(self.db, "illegal-seal")
        with self.assertRaises(sqlite3.IntegrityError):
            insert(
                self.db, "m06_registry", registry_version="2.0.1", parent_version="1.0.0",
                created_at=NOW, command_id="illegal-seal", sealed=1,
            )
        registry(self.db, "2.0.0", "1.0.0", seal=True)
        with self.assertRaises(sqlite3.IntegrityError):
            registry(self.db, "3.0.0", "1.0.0")
        self.db.commit()
        self.assert_clean()

    def test_segment_roots_are_per_project_and_parent_is_prior_sealed_revision(self):
        self.study("s1")
        self.study("s2")
        self.segment("s1", 1)
        self.segment("s2", 1)
        for revision, parent in ((2, None), (3, 1), (4, 4), (5, 6)):
            with self.subTest(revision=revision), self.assertRaises(sqlite3.IntegrityError):
                self.segment("s1", revision, parent)
        self.seal_segment("s1", 1)
        self.segment("s1", 6, 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.segment("s1", 7, 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.segment("s2", 8, 6)
        self.seal_segment("s1", 6)
        self.seal_segment("s2", 1)
        self.db.commit()
        self.assert_clean()

    def test_product_ancestry_cannot_be_cyclic_or_use_another_registry(self):
        registry(self.db, "1.0.0")
        self.product("1.0.0", "p")
        self.product("1.0.0", "child", "p")
        with self.assertRaises(sqlite3.IntegrityError):
            self.product("1.0.0", "self", "self")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE m06_product SET parent_id='child' WHERE registry_version='1.0.0' "
                "AND product_category_id='p'"
            )
            seal_registry(self.db, "1.0.0")
        self.db.rollback()
        registry(self.db, "1.0.0")
        self.product("1.0.0", "p")
        seal_registry(self.db, "1.0.0")
        registry(self.db, "2.0.0", "1.0.0")
        with self.assertRaises(sqlite3.IntegrityError):
            self.product("2.0.0", "child", "p")
            seal_registry(self.db, "2.0.0")

    def test_draft_registry_and_segment_cannot_commit_without_sealing(self):
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            registry(self.db, "1.0.0")
        with self.db:
            self.study("s1")
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.segment("s1", 1)
        self.assertIsNone(self.db.execute("SELECT 1 FROM m06_registry").fetchone())
        self.assertIsNone(self.db.execute("SELECT 1 FROM m06_segment_rev").fetchone())
        self.assertIsNone(self.db.execute("SELECT 1 FROM m06_command").fetchone())
        self.assert_clean()

    def test_constraint_failure_rolls_back_command_version_intent_and_edges(self):
        with self.db:
            registry(self.db, "1.0.0", seal=True)
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            registry(self.db, "2.0.0", "1.0.0")
            self.task("2.0.0", "C")
            self.intent("2.0.0", "A", primary="C")
            self.task_edge("2.0.0", "A", "C")
            self.task("2.0.0", "OTHER")
            self.task_edge("2.0.0", "A", "OTHER")
        for table in ("m06_task", "m06_intent", "m06_intent_task"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertIsNone(
            self.db.execute("SELECT 1 FROM m06_command WHERE command_id='registry-2.0.0'").fetchone()
        )
        self.assertEqual(
            [tuple(row) for row in self.db.execute("SELECT registry_version, sealed FROM m06_registry")],
            [("1.0.0", 1)],
        )
        self.assert_clean()

    def test_concurrent_issuers_share_one_committed_child_and_no_loser_command(self):
        with self.db:
            registry(self.db, "1.0.0", seal=True)
        old_version_read = Barrier(2, timeout=10)

        def issue(version):
            with closing(self.store.connect()) as conn:
                parent = conn.execute("SELECT registry_version FROM m06_registry WHERE sealed=1").fetchone()[0]
                old_version_read.wait()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    registry(conn, version, parent, seal=True)
                    conn.commit()
                except sqlite3.IntegrityError:
                    conn.rollback()
                    return "rejected"
                return "issued"

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(issue, ("2.0.0", "3.0.0")))
        self.assertCountEqual(results, ["issued", "rejected"])
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM m06_registry WHERE parent_version='1.0.0' AND sealed=1")
            .fetchone()[0],
            1,
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM m06_command").fetchone()[0], 2)
        self.assert_clean()

    def test_evidence_requires_exact_frozen_source_hash_and_unicode_coordinates(self):
        self.study("s1", with_source=True)
        self.study("s2", with_source=True)
        for kwargs in (
            {"record_id": "record-s2"},
            {"scope_id": "scope-s2"},
            {"raw_sha256": "d" * 64},
            {"scope_id": None},
            {"start": -1}, {"start": 1, "end": 1}, {"end": len(QUOTE) + 1},
            {"start": 0.5}, {"end": "not-an-integer"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(sqlite3.IntegrityError):
                self.evidence("s1", "bad-evidence", **kwargs)
        self.evidence("s1", "e1", 2, 3)
        with self.assertRaises(sqlite3.IntegrityError):
            self.evidence("s1", "duplicate-coordinates", 2, 3)
        for record_id, line_number in (("record-s1", 99), ("replacement-id", 2)):
            with self.subTest(record_id=record_id), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(
                    "INSERT OR REPLACE INTO import_rows "
                    "(record_id, batch_id, line_number, raw_text, originals_json, fields_json, "
                    "status, privacy, issues_json) "
                    "VALUES (?, 'batch-s1', ?, 'changed', '[]', '{}', 'pending_review', 'public', '[]')",
                    (record_id, line_number),
                )
        self.db.commit()
        self.assertEqual(
            self.db.execute("SELECT start_cp, end_cp FROM m06_evidence").fetchone()[:], (2, 3),
        )
        self.assertEqual(
            self.db.execute("SELECT raw_text FROM import_rows WHERE record_id='record-s1'").fetchone()[0],
            QUOTE,
        )
        self.assert_clean()

    def test_source_batch_cannot_be_replaced_by_id_or_signature(self):
        self.study("s1", with_source=True)
        self.study("s2", with_source=True)
        self.evidence("s1", "e1", 2, 3)
        self.db.execute("UPDATE import_batches SET revoked_at=? WHERE batch_id='batch-s1'", (NOW,))
        self.db.commit()

        for batch_id, signature, source in (
            ("batch-s1", "foreign-project", "batch-s2"),
            ("replacement-id", "fixture", "batch-s1"),
        ):
            with self.subTest(batch_id=batch_id), self.db:
                with self.assertRaises(sqlite3.IntegrityError) as error:
                    self.db.execute(
                        "INSERT OR REPLACE INTO import_batches "
                        "(batch_id, study_id, scope_id, file_id, sheet_index, sheet_name, header_line, "
                        "headers_json, mapping_json, privacy, signature, summary_json, created_at) "
                        "SELECT ?, study_id, scope_id, file_id, sheet_index, sheet_name, header_line, "
                        "headers_json, mapping_json, privacy, ?, summary_json, created_at "
                        "FROM import_batches WHERE batch_id=?",
                        (batch_id, signature, source),
                    )
                self.assertEqual(error.exception.sqlite_errorname, "SQLITE_CONSTRAINT_TRIGGER")

        self.assertEqual(
            self.db.execute(
                "SELECT e.record_id, b.study_id, b.scope_id, b.file_id, b.signature, b.revoked_at "
                "FROM m06_evidence e JOIN import_rows r ON r.record_id=e.record_id "
                "JOIN import_batches b ON b.batch_id=r.batch_id WHERE e.evidence_id='e1'"
            ).fetchone()[:],
            ("record-s1", "s1", "scope-s1", "file-s1", "fixture", NOW),
        )
        self.assert_clean()

    def test_support_cannot_link_across_projects_or_reuse_evidence_in_a_revision(self):
        for study in ("s1", "s2"):
            self.study(study, with_source=True)
            self.segment(study, 1)
            self.mention(study, f"m-{study}")
            self.member(study, 1, f"m-{study}")
            self.evidence(study, f"e-{study}")
        with self.assertRaises(sqlite3.IntegrityError):
            self.support("s1", 1, "m-s1", "e-s2")
        with self.assertRaises(sqlite3.IntegrityError):
            self.support("s1", 1, "m-s2", "e-s1")
        self.support("s1", 1, "m-s1", "e-s1")
        self.mention("s1", "second")
        self.member("s1", 1, "second")
        with self.assertRaises(sqlite3.IntegrityError):
            self.support("s1", 1, "second", "e-s1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.seal_segment("s1", 1)
        self.evidence("s1", "second-evidence", 1, 2)
        self.support("s1", 1, "second", "second-evidence")
        self.support("s2", 1, "m-s2", "e-s2")
        self.seal_segment("s1", 1)
        self.seal_segment("s2", 1)
        self.db.commit()
        self.assert_clean()

    def test_confirmed_intent_seal_requires_three_structurally_distinct_supports(self):
        self.study("s1", with_source=True)
        self.segment("s1", 1)
        for offset in range(4):
            evidence_id = f"e{offset}"
            mention = "m2" if offset > 1 else f"m{offset}"
            if offset < 3:
                self.mention("s1", mention)
                self.member("s1", 1, mention)
            self.evidence("s1", evidence_id, offset, offset + 1)
            self.support("s1", 1, mention, evidence_id)
        self.seal_segment("s1", 1)
        registry(self.db, "1.0.0")
        self.task("1.0.0", "C")
        self.intent("1.0.0", "A", primary="C")
        self.task_edge("1.0.0", "A", "C")

        def add_representative(mention, evidence_id):
            insert(
                self.db, "m06_representative", registry_version="1.0.0", intent_id="A",
                study_id="s1", segment_revision=1, mention_id=mention, evidence_id=evidence_id,
            )

        with self.assertRaises(sqlite3.IntegrityError):
            add_representative("m0", "e1")
        for mention, evidence_id in (("m0", "e0"), ("m2", "e2"), ("m2", "e3")):
            add_representative(mention, evidence_id)
        with self.assertRaises(sqlite3.IntegrityError):
            seal_registry(self.db, "1.0.0")
        add_representative("m1", "e1")
        seal_registry(self.db, "1.0.0")
        self.db.commit()
        self.assert_clean()

    def test_sealed_registry_and_children_cannot_be_inserted_updated_deleted_or_replaced(self):
        registry(self.db, "1.0.0")
        self.product("1.0.0", "P")
        self.task("1.0.0", "C")
        self.intent("1.0.0", "A", status="candidate")
        seal_registry(self.db, "1.0.0")
        registry(self.db, "2.0.0", "1.0.0")
        self.product("2.0.0", "draft")
        invalid_sql = (
            "UPDATE m06_registry SET sealed=0 WHERE registry_version='1.0.0'",
            "DELETE FROM m06_registry WHERE registry_version='1.0.0'",
            "INSERT OR REPLACE INTO m06_registry(registry_version,parent_version,created_at,command_id,sealed) "
            "SELECT registry_version,parent_version,"
            "created_at,command_id,0 FROM m06_registry WHERE registry_version='1.0.0'",
            "UPDATE m06_product SET name='bad' WHERE registry_version='1.0.0'",
            "DELETE FROM m06_product WHERE registry_version='1.0.0'",
            "INSERT OR REPLACE INTO m06_product SELECT * FROM m06_product WHERE registry_version='1.0.0'",
            "UPDATE m06_product SET registry_version='1.0.0' WHERE registry_version='2.0.0'",
            "UPDATE m06_task SET name='bad' WHERE registry_version='1.0.0'",
            "DELETE FROM m06_intent WHERE registry_version='1.0.0'",
        )
        for sql in invalid_sql:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        with self.assertRaises(sqlite3.IntegrityError):
            self.product("1.0.0", "late")
        self.assertEqual(
            self.db.execute("SELECT name FROM m06_product WHERE registry_version='1.0.0'").fetchone()[0],
            "P",
        )
        seal_registry(self.db, "2.0.0")
        self.db.commit()
        self.assert_clean()

    def test_sealed_segment_and_edges_reject_mutations(self):
        self.study("s1", with_source=True)
        self.segment("s1", 1)
        self.mention("s1", "m")
        self.member("s1", 1, "m")
        self.evidence("s1", "e")
        self.support("s1", 1, "m", "e")
        self.seal_segment("s1", 1)
        self.mention("s1", "late")
        self.db.commit()
        invalid_sql = (
            "UPDATE m06_segment_rev SET rule_version='bad' WHERE study_id='s1'",
            "DELETE FROM m06_segment_rev WHERE study_id='s1'",
            "UPDATE m06_member SET identity_state='needs_review' WHERE study_id='s1'",
            "DELETE FROM m06_member WHERE study_id='s1'",
            "UPDATE m06_support SET review_ref='bad' WHERE study_id='s1'",
            "DELETE FROM m06_support WHERE study_id='s1'",
            "INSERT OR REPLACE INTO m06_support SELECT * FROM m06_support WHERE study_id='s1'",
            "UPDATE m06_evidence SET start_cp=1,end_cp=2 WHERE study_id='s1'",
        )
        for sql in invalid_sql:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        with self.assertRaises(sqlite3.IntegrityError):
            self.member("s1", 1, "late")
        self.assert_clean()

    def test_scope_mappings_require_exact_catalog_and_keep_older_mapping_and_frozen_content(self):
        self.study("s1")
        registry(self.db, "1.0.0")
        self.product("1.0.0", "P1")
        seal_registry(self.db, "1.0.0")
        registry(self.db, "2.0.0", "1.0.0")
        self.product("2.0.0", "P2")
        seal_registry(self.db, "2.0.0")
        self.mapping("s1", 1, "1.0.0")
        self.db.commit()
        for kwargs in (
            {"status": "mapped_product", "reviewer": "catalog-review"},
            {"status": "non_product"},
            {"previous": None},
        ):
            args = {"previous": 1} | kwargs
            with self.subTest(kwargs=kwargs), self.assertRaises(sqlite3.IntegrityError), self.db:
                self.mapping("s1", 2, "2.0.0", **args)
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.scope_product("s1", 2, "1.0.0", "P1")
            self.mapping(
                "s1", 2, "2.0.0", previous=1, status="mapped_product", reviewer="catalog-review",
            )
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.scope_product("s1", 2, "2.0.0", "P2")
            self.mapping(
                "s1", 2, "2.0.0", previous=1, status="non_product", reviewer="catalog-review",
            )
        with self.db:
            self.scope_product("s1", 2, "2.0.0", "P2")
            self.mapping(
                "s1", 2, "2.0.0", previous=1, status="mapped_product", reviewer="catalog-review",
            )
            self.mapping(
                "s1", 3, "2.0.0", previous=2, status="non_product", reviewer="catalog-review",
            )
        self.assertEqual(
            [
                tuple(row) for row in self.db.execute(
                    "SELECT mapping_revision, registry_version, mapping_status FROM m06_scope_binding"
                    " ORDER BY mapping_revision"
                )
            ],
            [(1, "1.0.0", "unresolved"), (2, "2.0.0", "mapped_product"), (3, "2.0.0", "non_product")],
        )
        for sql in (
            "UPDATE study_scopes SET content_json='{}' WHERE scope_id='scope-s1'",
            "INSERT OR REPLACE INTO study_scopes SELECT * FROM study_scopes WHERE scope_id='scope-s1'",
            "DELETE FROM study_scope_freezes WHERE scope_id='scope-s1'",
            "INSERT OR REPLACE INTO study_scope_freezes SELECT * FROM study_scope_freezes WHERE scope_id='scope-s1'",
            "UPDATE m06_scope_binding SET basis_ref='bad' WHERE mapping_revision=1",
            "DELETE FROM m06_scope_binding WHERE mapping_revision=3",
            "INSERT OR REPLACE INTO m06_scope_binding SELECT * FROM m06_scope_binding WHERE mapping_revision=3",
            "DELETE FROM m06_scope_product WHERE mapping_revision=2",
            "INSERT OR REPLACE INTO m06_scope_product SELECT * FROM m06_scope_product WHERE mapping_revision=2",
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.assertEqual(
            self.db.execute("SELECT content_json FROM study_scopes").fetchone()[0],
            '{"product_categories":["历史品类"]}',
        )
        self.assert_clean()

    def test_idempotency_key_is_unique_per_operation_namespace(self):
        self.study("s1")
        self.study("s2")
        command(self.db, "old", "s1", key="same-request")
        for digest in ("a", "b"):
            with self.subTest(digest=digest), self.assertRaises(sqlite3.IntegrityError):
                command(self.db, f"retry-{digest}", "s1", key="same-request", digest=digest * 64)
        command(self.db, "independent", "s2", key="same-request")
        command(self.db, "global", key="same-request")
        command(self.db, "other-action", "s1", key="same-request", operation="other")
        with self.assertRaises(sqlite3.IntegrityError):
            self.segment("s2", 1, command_id="old")
        with self.assertRaises(sqlite3.IntegrityError):
            self.segment("s2", 2, command_id="global")
        for sql in (
            "UPDATE m06_command SET reason='overwritten' WHERE command_id='old'",
            "DELETE FROM m06_command WHERE command_id='old'",
            "INSERT OR REPLACE INTO m06_command SELECT * FROM m06_command WHERE command_id='old'",
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.db.commit()
        self.assert_clean()

    def test_product_review_keeps_full_edge_key_and_append_only_decisions(self):
        for study in ("s1", "s2"):
            self.study(study, with_source=True)
        registry(self.db, "1.0.0")
        self.product("1.0.0", "P")
        seal_registry(self.db, "1.0.0")
        registry(self.db, "2.0.0", "1.0.0")
        self.product("2.0.0", "P")
        seal_registry(self.db, "2.0.0")
        self.segment("s1", 1)
        self.mention("s1", "m")
        self.member("s1", 1, "m")
        self.evidence("s1", "e")
        self.support("s1", 1, "m", "e")
        command(self.db, "product-link", "s1")
        command(self.db, "wrong-project", "s2")
        command(self.db, "proposal", "s1")
        command(self.db, "confirmation", "s1")
        edge = edge_values("s1", 1, "m", "e", "1.0.0", "P")
        insert(self.db, "m06_mention_product", **edge, link_type="explicit", command_id="product-link")

        def review(sequence, decision, cmd, **overrides):
            values = edge | {
                "decision_seq": sequence, "decision": decision, "basis_ref": "basis",
                "actor_ref": "synthetic-reviewer", "decided_at": NOW, "command_id": cmd,
                "mode": "A", "proposal_provenance": "{}",
            }
            insert(self.db, "m06_product_review", **(values | overrides))

        for overrides in (
            {"catalog_version": "2.0.0"},
            {"study_id": "s2", "command_id": "wrong-project"},
            {"command_id": "wrong-project"},
            {"evidence_id": None},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(sqlite3.IntegrityError):
                review(1, "proposed", "proposal", **overrides)
        review(1, "proposed", "proposal")
        self.seal_segment("s1", 1)
        with self.assertRaises(sqlite3.IntegrityError):
            review(2, "human_confirmed", "confirmation", mode="B")
        review(2, "human_confirmed", "confirmation")
        self.db.commit()
        for sql in (
            "UPDATE m06_product_review SET basis_ref='bad'",
            "DELETE FROM m06_product_review WHERE decision_seq=1",
            "INSERT OR REPLACE INTO m06_product_review SELECT * FROM m06_product_review WHERE decision_seq=2",
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)
        self.assertEqual(
            [tuple(row) for row in self.db.execute("SELECT decision_seq, decision FROM m06_product_review ORDER BY 1")],
            [(1, "proposed"), (2, "human_confirmed")],
        )
        self.assert_clean()

    def test_discovery_input_validates_nullable_branch_and_exact_occurrence_relation(self):
        self.study("s1", with_source=True)
        self.segment("s1", 1)
        self.mention("s1", "m")
        self.member("s1", 1, "m")
        self.evidence("s1", "occurrence")
        self.evidence("s1", "context-only", 1, 2)
        self.support("s1", 1, "m", "occurrence")
        self.seal_segment("s1", 1)
        registry(self.db, "1.0.0", seal=True)
        command(self.db, "discovery", "s1")
        review_key = {
            "study_id": "s1", "segment_revision": 1, "mention_id": "m", "registry_version": "1.0.0",
            "seq": 1,
        }
        insert(
            self.db, "m06_discovery_review", **review_key, intent_id=None, review_state="open",
            reason_code="fixture", command_id="discovery",
        )
        for kind, evidence_id, target in (
            ("occurrence", "occurrence", None),
            ("occurrence", "context-only", "context-only"),
            ("occurrence", "context-only", "occurrence"),
            ("context", "context-only", "occurrence"),
        ):
            with self.subTest(kind=kind, evidence=evidence_id, target=target), self.assertRaises(sqlite3.IntegrityError):
                insert(
                    self.db, "m06_discovery_input", **review_key, evidence_id=evidence_id,
                    dependency_role=kind, target_e=target,
                )
        for kind, evidence_id, target in (
            ("occurrence", "occurrence", "occurrence"),
            ("context", "context-only", None),
        ):
            insert(
                self.db, "m06_discovery_input", **review_key, evidence_id=evidence_id,
                dependency_role=kind, target_e=target,
            )
        self.db.commit()
        self.assert_clean()

    def test_replacement_cannot_point_to_wrong_parent_or_form_a_stable_identity_cycle(self):
        self.study("s1", with_source=True)
        self.mention("s1", "old")
        self.mention("s1", "new")
        self.evidence("s1", "first")
        self.evidence("s1", "second", 1, 2)

        def revision(number, parent, member, evidence_id):
            self.segment("s1", number, parent)
            self.member("s1", number, member)
            self.support("s1", number, member, evidence_id)

        def replace(number, prior, old, new):
            insert(
                self.db, "m06_replacement", study_id="s1", segment_revision=number, old_rev=prior,
                old_mention_id=old, new_mention_id=new, reason="synthetic replacement",
            )

        revision(1, None, "old", "first")
        self.seal_segment("s1", 1)
        revision(2, 1, "new", "second")
        with self.assertRaises(sqlite3.IntegrityError):
            replace(2, 2, "new", "new")
        replace(2, 1, "old", "new")
        self.seal_segment("s1", 2)
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            revision(3, 2, "old", "first")
            replace(3, 2, "new", "old")
            self.seal_segment("s1", 3)
        self.assertEqual(
            [row[0] for row in self.db.execute("SELECT segment_revision FROM m06_segment_rev ORDER BY 1")],
            [1, 2],
        )
        self.assert_clean()

    def test_change_edge_requires_consistent_nulls_and_endpoints_of_the_declared_kind(self):
        registry(self.db, "1.0.0")
        self.product("1.0.0", "old-product")
        self.task("1.0.0", "old-task")
        seal_registry(self.db, "1.0.0")
        self.db.commit()

        def change(from_id, **overrides):
            values = {
                "registry_version": "2.0.0", "seq": 1, "command_id": "registry-2.0.0",
                "kind": "product", "from_version": "1.0.0", "from_id": from_id,
                "to_id": "new-product", "action": "update",
            }
            insert(self.db, "m06_change_edge", **(values | overrides))

        with self.assertRaises(sqlite3.IntegrityError), self.db:
            registry(self.db, "2.0.0", "1.0.0")
            self.product("2.0.0", "new-product")
            change("old-task")
            seal_registry(self.db, "2.0.0")
        self.assertIsNone(self.db.execute("SELECT 1 FROM m06_change_edge").fetchone())
        with self.db:
            registry(self.db, "2.0.0", "1.0.0")
            self.product("2.0.0", "new-product")
            with self.assertRaises(sqlite3.IntegrityError):
                change("old-product", from_version=None)
            change("old-product")
            seal_registry(self.db, "2.0.0")
        self.assertEqual(
            self.db.execute("SELECT from_id, to_id FROM m06_change_edge").fetchone()[:],
            ("old-product", "new-product"),
        )
        self.assert_clean()
