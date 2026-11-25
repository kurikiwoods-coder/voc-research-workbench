"""Exercise shared registry reads against sealed synthetic definitions."""

import json
from pathlib import Path
from sqlite3 import IntegrityError
from tempfile import TemporaryDirectory
import unittest

import test_m06_relations_queries as c4
from test_m06_constraints import insert, registry, seal_registry
from src.raw_store.registry_versions import RegistryVersions
from src.raw_store.relations import RelationStore
from src.raw_store.store import Store


BEFORE = c4.VERSION
AFTER = "3.1.0"
TIP = "3.2.0"
SPLIT = "A-SPLIT"
DISTINCT = "A-FURTHER"
MERGE_TARGET = "A-SUCCESSOR"


def copy_definitions(db, version, parent):
    for table in ("m06_task", "m06_intent", "m06_intent_task", "m06_representative"):
        columns = ", ".join(row["name"] for row in db.execute(f"PRAGMA table_info({table})")
                            if row["name"] != "registry_version")
        db.execute(f"INSERT INTO {table} (registry_version, {columns}) "
                   f"SELECT ?, {columns} FROM {table} WHERE registry_version=?", (version, parent))


class RegistryVersionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = c4.RelationQueryTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        representatives = self.fixture.publish([])
        self.fixture.seal_definitions(representatives, parent=None)
        self.versions = RegistryVersions(RelationStore(self.fixture.fixture.db))

    def add_definitions(self):
        with self.fixture.fixture.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            registry(db, AFTER, BEFORE)
            for task in (c4.PRIMARY, c4.SECONDARY):
                insert(
                    db, "m06_task", registry_version=AFTER, category_id=task, name=f"Shared {task}",
                    definition="Task definition", inclusion_criteria="", exclusion_criteria="",
                    discovery="preset", lifecycle_status="confirmed", version="1.1.0",
                )
            for intent, name, lifecycle, primary, survey, secondaries in (
                (c4.INTENT, "Shared safety lock", "retired", c4.SECONDARY, "failed", (c4.PRIMARY,)),
                (c4.PENDING, "Same name", "candidate", c4.PRIMARY, "validating", (c4.SECONDARY,)),
                (SPLIT, "Same name", "candidate", None, "unvalidated", ()),
                (DISTINCT, "Same name", "candidate", None, "unvalidated", ()),
                (MERGE_TARGET, "Successor", "candidate", None, "unvalidated", ()),
            ):
                insert(
                    db, "m06_intent", registry_version=AFTER, intent_id=intent, name=name,
                    definition=f"Shared definition for {intent}", inclusion_criteria="Included",
                    exclusion_criteria="Excluded", lifecycle_status=lifecycle,
                    primary_category_id=primary, survey_validation_status=survey, version="1.1.0",
                )
                if primary is not None:
                    insert(db, "m06_intent_task", registry_version=AFTER, intent_id=intent,
                           category_id=primary, is_primary=1)
                for category in secondaries:
                    insert(db, "m06_intent_task", registry_version=AFTER, intent_id=intent,
                           category_id=category, is_primary=0)
            insert(db, "m06_change_edge", registry_version=AFTER, seq=11,
                   command_id=f"registry-{AFTER}", kind="intent",
                   from_version=BEFORE, from_id=c4.PENDING, to_id=SPLIT, action="split")
            seal_registry(db, AFTER)
            registry(db, TIP, AFTER)
            copy_definitions(db, TIP, AFTER)
            db.execute(
                "UPDATE m06_intent SET lifecycle_status='merged' WHERE registry_version=? AND intent_id=?",
                (TIP, SPLIT),
            )
            insert(db, "m06_change_edge", registry_version=TIP, seq=15,
                   command_id=f"registry-{TIP}", kind="intent",
                   from_version=AFTER, from_id=SPLIT, to_id=MERGE_TARGET, action="merge")
            seal_registry(db, TIP)

    def test_empty_and_paged_history(self):
        with TemporaryDirectory(prefix="voc-m07 empty ") as folder:
            versions = RegistryVersions(RelationStore(Store(Path(folder))))
            self.assertEqual(versions.versions(), {
                "current_registry_version": None, "items": [], "next_offset": None,
            })
            self.assertEqual(versions.catalog(), {"registry_version": None, "items": [], "next_offset": None})
        self.add_definitions()
        first, second = self.versions.versions(limit=1), self.versions.versions(limit=1, offset=1)
        self.assertEqual(first["current_registry_version"], TIP)
        self.assertEqual(first["items"][0]["parent_version"], AFTER)
        self.assertEqual(first["next_offset"], 1)
        self.assertEqual(second["items"][0]["registry_version"], AFTER)
        with self.assertRaises(KeyError):
            self.versions.catalog("9.9.9")
        with self.assertRaises(ValueError):
            self.versions.versions(limit=101)

    def test_filtered_catalog_and_exact_shared_projection(self):
        self.add_definitions()
        result = self.versions.catalog(TIP, q="sAmE NaMe", lifecycle_status="candidate", limit=1)
        first = result["items"][0]
        self.assertEqual(first["intent_id"], DISTINCT)
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(first["recent_change"]["registry_version"], AFTER)
        self.assertEqual(first["approved_shared_examples"], [])
        filtered = self.versions.catalog(
            TIP, primary_category_id=c4.PRIMARY, survey_validation_status="validating",
        )["items"]
        self.assertEqual([item["intent_id"] for item in filtered], [c4.PENDING])
        self.assertEqual(filtered[0]["recent_change"]["registry_version"], AFTER)
        successor = self.versions.catalog(TIP, q="Successor")["items"][0]
        self.assertEqual(successor["recent_change"]["registry_version"], TIP)
        self.assertEqual(successor["recent_change"]["status"], "merged")
        self.assertEqual(successor["recent_change"]["fields"], [])
        self.assertEqual(filtered[0]["task_categories"], [
            {"category_id": c4.PRIMARY, "name": f"Shared {c4.PRIMARY}", "role": "primary"},
            {"category_id": c4.SECONDARY, "name": f"Shared {c4.SECONDARY}", "role": "secondary"},
        ])
        self.assertEqual(self.versions.detail(BEFORE, c4.PENDING)["primary_category_id"], None)
        self.assertEqual(self.versions.catalog(TIP, q="Synthetic safety concern")["items"], [])

    def test_diff_preserves_stable_ids_fields_and_lineage(self):
        self.add_definitions()
        result = self.versions.compare(BEFORE, AFTER)
        items = {item["intent_id"]: item for item in result["items"]}
        self.assertEqual(set(items), {c4.INTENT, c4.PENDING, DISTINCT, SPLIT, MERGE_TARGET})
        self.assertEqual(items[DISTINCT]["status"], "added")
        self.assertEqual(items[c4.INTENT]["status"], "retired")
        self.assertEqual(items[SPLIT]["status"], "split")
        self.assertEqual(items[SPLIT]["lineage"], [
            {"registry_version": AFTER, "from_version": BEFORE, "from_id": c4.PENDING,
             "to_id": SPLIT, "action": "split"},
        ])
        self.assertEqual(self.versions.compare(AFTER, AFTER)["items"][0]["status"], "unchanged")
        next_version = {item["intent_id"]: item for item in self.versions.compare(AFTER, TIP)["items"]}
        self.assertEqual(next_version[SPLIT]["status"], "merged")
        self.assertEqual(next_version[DISTINCT]["status"], "unchanged")
        changed = {field["field"]: (field["before"], field["after"]) for field in items[c4.INTENT]["changes"]}
        self.assertEqual(changed["primary_category_id"], (c4.PRIMARY, c4.SECONDARY))
        self.assertEqual(changed["secondary_category_ids"], ([c4.SECONDARY], [c4.PRIMARY]))
        self.assertEqual(changed["survey_validation_status"], ("unvalidated", "failed"))
        self.assertTrue({"name", "definition", "inclusion_criteria", "exclusion_criteria"} <= changed.keys())
        self.assertEqual(self.versions.compare(BEFORE, AFTER, limit=1)["next_offset"], 1)

    def test_historical_detail_remains_immutable_and_private_fields_stay_private(self):
        original = self.versions.detail(BEFORE, c4.INTENT)
        self.add_definitions()
        self.assertEqual(self.versions.detail(BEFORE, c4.INTENT), original)
        historical = self.versions.detail(TIP, SPLIT)
        for value in (historical, self.versions.compare(BEFORE, TIP), self.versions.versions()):
            payload = json.dumps(value)
            for private in ("synthetic-reviewer", "synthetic decision", "Synthetic safety concern",
                            "command_id", "study_id", "evidence_id", "mention_id", "source_breakdown"):
                self.assertNotIn(private, payload)
        self.assertEqual([item["registry_version"] for item in historical["change_log"]], [TIP, AFTER])
        self.assertEqual(historical["change_log"][0]["status"], "merged")
        self.assertEqual([edge["action"] for edge in historical["lineage"]], ["split", "merge"])
        with self.assertRaises(IntegrityError), self.fixture.fixture.db.db() as db:
            db.execute("UPDATE m06_intent SET name='mutated' WHERE registry_version=?", (BEFORE,))

    def test_consumer_requires_exact_version_and_filters_current_candidates(self):
        self.add_definitions()
        with self.assertRaises(ValueError):
            self.versions.consumer(None)
        with self.assertRaises(KeyError):
            self.versions.consumer("9.9.9")
        pinned = self.versions.consumer(BEFORE)
        self.assertEqual(pinned["registry_version"], BEFORE)
        self.assertEqual(pinned["mode"], "engineering")
        self.assertEqual([item["intent_id"] for item in pinned["items"]], [c4.INTENT])
        self.assertEqual(pinned["items"][0]["survey_validation_status"], "unvalidated")
        self.assertEqual(self.versions.consumer(AFTER)["items"], [])

    def test_comparison_includes_public_intermediate_lineage(self):
        self.add_definitions()
        final = "3.3.0"
        with self.fixture.fixture.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            registry(db, final, TIP, seal=True)
        result = {item["intent_id"]: item for item in self.versions.compare(BEFORE, final)["items"]}
        self.assertEqual(result[MERGE_TARGET]["status"], "merged")
        self.assertEqual(result[MERGE_TARGET]["changes"], [])
        self.assertEqual(result[MERGE_TARGET]["lineage"][0]["from_id"], SPLIT)
        self.assertNotIn(DISTINCT, result)

    def test_sealed_examples_are_version_specific_and_consumer_excludes_synthetic(self):
        rows = [
            ("positive", "Shared positive example", "approved_shared"),
            ("negative", "Synthetic negative example", "synthetic"),
        ]
        with self.fixture.fixture.db.db() as db:
            db.execute("BEGIN IMMEDIATE")
            registry(db, AFTER, BEFORE)
            copy_definitions(db, AFTER, BEFORE)
            for position, (kind, text, classification) in enumerate(rows, start=1):
                insert(db, "m07_shared_example", registry_version=AFTER, intent_id=c4.INTENT, seq=position,
                       kind=kind, example_text=text, classification=classification, approval_ref="fixture-private")
            seal_registry(db, AFTER)
            registry(db, TIP, AFTER)
            copy_definitions(db, TIP, AFTER)
            seal_registry(db, TIP)
        projected = [dict(kind=kind, text=text, classification=classification)
                     for kind, text, classification in rows]
        detail = self.versions.detail(AFTER, c4.INTENT)
        self.assertEqual(detail["approved_shared_examples"], projected)
        self.assertNotIn("fixture-private", json.dumps(detail))
        self.assertEqual(self.versions.detail(BEFORE, c4.INTENT)["approved_shared_examples"], [])
        self.assertEqual(self.versions.detail(TIP, c4.INTENT)["approved_shared_examples"], [])
        diff = {item["intent_id"]: item for item in self.versions.compare(BEFORE, AFTER)["items"]}
        self.assertEqual(diff[c4.INTENT]["changes"], [
            {"field": "approved_shared_examples", "before": [], "after": projected},
        ])
        self.assertEqual(self.versions.consumer(AFTER)["items"][0]["approved_shared_examples"], projected[:1])
        with self.assertRaises(IntegrityError), self.fixture.fixture.db.db() as db:
            db.execute("DELETE FROM m07_shared_example WHERE registry_version=?", (AFTER,))
