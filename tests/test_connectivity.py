"""Deterministic regression tests, including a physically separate synthetic HTTP ledger."""

from pathlib import Path
from io import BytesIO
import json
import sqlite3
import tempfile
import unittest
import uuid
from urllib.parse import urlsplit
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.config import Settings, MODEL
from src.dashboard.app import balance, create_app, catalogue
from src.discovery.recall import test_cross_category_recall
from src.execution.checks import CODES, run_checks, test_gate_requires_all_six, test_isolation_drill
from src.execution.jev import call_shards, intent_question, questions, split, validate
from src.execution.transport import Denied, Response, network, outbound, redact
from src.ingestion.public_source import discover, first_sentence, post_id
from src.raw_store.store import Busy, Conflict, Store
from src.outputs.audit_receipt import public_evidence

AUTH = {"X-VOC-Action": "connectivity"}
FORUM_URL = "https://cooking.stackexchange.com/q/"


class ApprovedFixture(Settings):
    def review_status(self):
        return {"approved": True, "scope": "contract_fixture"}


def response_for(payload):
    answers = {}
    for key, q in payload["questions"].items():
        kind = q["type"]
        if kind == "noul":
            answers[key] = {"type": kind, "noul": 0.5}
        elif kind == "choice":
            first = next(iter(q["criteria"]))
            answers[key] = {
                "type": kind,
                "choice": first,
                "confidence": 1,
                "probabilities": {k: int(k == first) for k in q["criteria"]},
            }
        else:
            answers[key] = {
                "type": kind,
                "confidence": 1,
                "score": 1,
                "probabilities": {"0": 0, "1": 1, "2": 0},
            }
    return {"model": MODEL, "usage": {"input_tokens": 17}, "answers": answers}


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = ApprovedFixture(self.root, keys={"jevmodel": "fixture-only"})
        self.db = Store(self.root, fixture=True)
        self.batch_id, self.attempt = self.db.begin("unit", self.cfg)
        self.quote = {"text": "Synthetic fixture.", "verified": True, "post_id": "fixture"}

    def test_shards_share_gate_and_are_complete(self):
        shards = split(questions())
        self.assertEqual([len(s) for s in shards], [8, 3])
        self.assertTrue({"intent", "in_registry"} <= set(shards[0]))
        self.assertEqual(len(shards[0].keys() | shards[1].keys()), 11)
        self.assertIn("None", shards[0]["intent"]["criteria"])
        with self.assertRaises(ValueError):
            intent_question({str(i): "sample" for i in range(20)})

    def test_score_gap_keeps_actual_fields_and_never_infers_distribution(self):
        asked = questions()
        obj = response_for({"questions": asked})
        del obj["answers"]["friction"]["probabilities"]
        self.assertEqual(validate(asked, obj), (True, ["friction.probabilities"]))
        self.assertNotIn("probabilities", obj["answers"]["friction"])

    def test_alias_missing_answer_nan_and_wrong_sum_do_not_pass(self):
        asked = questions()
        obj = response_for({"questions": asked})
        obj["model"] = "jev-latest"
        self.assertFalse(validate(asked, obj)[0])
        del obj["answers"]["signal_2"]
        obj["answers"]["in_registry"]["noul"] = float("nan")
        obj["answers"]["intent"]["probabilities"]["None"] = 0.6
        identity, gaps = validate(asked, obj)
        self.assertFalse(identity)
        self.assertTrue({"in_registry.noul", "intent.probabilities", "signal_2.type"} <= set(gaps))

    def test_malformed_answer_values_become_schema_gaps(self):
        asked = questions()
        obj = response_for({"questions": asked})
        obj["answers"]["intent"]["choice"] = ["use"]
        obj["answers"]["friction"]["score"] = 10**400
        obj["answers"]["in_registry"]["noul"] = 10**400
        identity, gaps = validate(asked, obj)
        self.assertTrue(identity)
        self.assertEqual(gaps, ["intent.choice", "in_registry.noul", "friction.score"])

    def test_invalid_json_numbers_leave_a_recordable_http_failure(self):
        for literal in (b"NaN", b"Infinity", b"1e999"):
            with self.subTest(literal=literal):
                stream = BytesIO(b'{"answers":{"confidence":' + literal + b"}}")
                stream.status = 200
                stream.headers = {}
                with patch("src.execution.transport.build_opener") as opener:
                    opener.return_value.open.return_value = stream
                    reply = network("GET", "https://example.invalid", None, {})
                self.assertEqual(reply.status, 200)
                self.assertEqual(reply.body, {"error": "non_json_response"})

    def test_partial_second_shard_and_idempotent_resume(self):
        calls = []

        def transport(method, url, body, headers):
            calls.append(headers["Idempotency-Key"])
            if len(calls) == 2:
                return Response(402, {"error": {"type": "insufficient_credits"}})
            return Response(200, response_for(body), 900)

        args = (self.cfg, self.db, self.batch_id, self.attempt, self.quote, transport)
        _, verified, _, reason = call_shards(*args)
        self.assertEqual(verified, [True])
        self.assertIn("402", reason)
        self.assertEqual(balance(self.db, self.cfg)["warning"], "额度不足")
        self.assertEqual(call_shards(*args)[1:], ([True, True], [], None))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1], calls[2])
        self.assertEqual(
            [r["tokens"] for r in Store(self.root, fixture=True).ledger(self.batch_id)], [17, 17]
        )
        call_shards(*args)
        self.assertEqual(len(calls), 3)
        self.assertEqual(balance(self.db, self.cfg)["input_tokens"], 34)
        self.assertTrue(
            all(
                e["mode"] != "live_http" for e in self.db.audit(self.batch_id)["attempts"][0]["evidence"]
            )
        )

    def test_interrupted_request_pauses_without_double_submission(self):
        asked = split(questions())[0]
        self.db.reserve(
            self.batch_id, 1, {"model": MODEL, "state": self.quote["text"], "questions": asked}
        )

        def unreachable(*args):
            self.fail("An ambiguous request was transmitted again")

        self.assertIn(
            "待核对",
            call_shards(self.cfg, self.db, self.batch_id, self.attempt, self.quote, unreachable)[3],
        )

    def test_resume_recovers_legacy_recorded_success_without_sending_it_twice(self):
        payload = {"model": MODEL, "state": self.quote["text"], "questions": split(questions())[0]}
        key, _ = self.db.reserve(self.batch_id, 1, payload)
        archived = self.db.record(
            self.attempt, "jev_shard", "live_http", {"idempotency_key": key, "body": payload},
            {"X-Tokens-Remaining": 17, "body": response_for(payload)}, 200,
        )
        self.assertEqual(self.db.ledger(self.batch_id)[0]["state"], "sending")

        def only_second_shard(method, url, body, headers):
            self.assertEqual(list(body["questions"]), list(split(questions())[1]))
            return Response(200, response_for(body), 0)

        reopened = Store(self.root, fixture=True)
        _, attempt = reopened.begin(None, self.cfg, self.batch_id)
        args = (self.cfg, reopened, self.batch_id, attempt, self.quote, only_second_shard)
        self.assertEqual(call_shards(*args)[1:], ([True, True], [], None))
        ledger = reopened.ledger(self.batch_id)
        self.assertEqual([row["tokens"] for row in ledger], [17, 17])
        self.assertEqual(ledger[0]["evidence_id"], archived)
        self.assertEqual(balance(reopened, self.cfg)["remaining"], 0)

    def test_jev_evidence_and_usage_commit_together(self):
        with self.db.db() as conn:
            conn.executescript("""
                CREATE TRIGGER reject_first_settlement BEFORE UPDATE ON shards
                WHEN NEW.state='received'
                BEGIN SELECT RAISE(ABORT, 'synthetic storage failure'); END;
            """)

        sent = []

        def successful_fixture(method, url, body, headers):
            sent.append(headers["Idempotency-Key"])
            return Response(200, response_for(body), 80)

        args = (self.cfg, self.db, self.batch_id, self.attempt, self.quote, successful_fixture)
        with self.assertRaises(sqlite3.IntegrityError):
            call_shards(*args)
        self.assertEqual(self.db.rows("SELECT id FROM evidence WHERE name='jev_shard'"), [])
        self.assertEqual(self.db.ledger(self.batch_id)[0]["state"], "sending")

        # The provider fixture returned success, and the response transaction then failed.
        # Reopening and recovering the same batch must leave that request uncertain.
        reopened = Store(self.root, fixture=True)
        _, attempt = reopened.begin(None, self.cfg, self.batch_id)
        _, versions, _, reason = call_shards(
            self.cfg, reopened, self.batch_id, attempt, self.quote, successful_fixture
        )
        self.assertEqual(versions, [])
        self.assertIn("待核对", reason)
        self.assertEqual(len(sent), 1)
        self.assertIsNone(reopened.ledger(self.batch_id)[0]["tokens"])

    def test_latest_success_without_balance_header_is_unsynced(self):
        calls = []

        def transport(method, url, body, headers):
            calls.append(headers["Idempotency-Key"])
            return Response(200, response_for(body), 80 if len(calls) == 1 else None)

        call_shards(self.cfg, self.db, self.batch_id, self.attempt, self.quote, transport)
        token = balance(self.db, self.cfg)
        self.assertIsNone(token["remaining"])
        self.assertIsNone(token["sync_method"])
        self.assertIsNotNone(token["last_synced_at"])
        self.assertEqual(token["input_tokens"], 34)
        self.assertIn(80, [row["remaining"] for row in token["records"]])

    def test_unauthorized_response_hides_former_balance_but_preserves_usage(self):
        replies = iter((
            lambda payload: Response(200, response_for(payload), 80),
            lambda payload: Response(401, {"error": "fixture_invalid_key"}),
        ))

        def transport(method, url, body, headers):
            return next(replies)(body)

        call_shards(self.cfg, self.db, self.batch_id, self.attempt, self.quote, transport)
        token = balance(self.db, self.cfg)
        self.assertEqual(token["warning"], "密钥异常")
        self.assertIsNone(token["remaining"])
        self.assertEqual(token["input_tokens"], 17)

    def test_repeated_key_must_bind_same_payload_and_account(self):
        self.db.reserve(self.batch_id, 1, {"a": 1})
        with self.assertRaises(Conflict):
            self.db.reserve(self.batch_id, 1, {"a": 2})
        self.assertEqual(self.db.begin("unit", self.cfg), (self.batch_id, None))
        with self.assertRaises(Conflict):
            self.db.begin(None, Settings(self.root, provider="typesafe"), self.batch_id)

    def test_first_key_can_resume_unbilled_batch_only(self):
        db = Store(self.root)
        run, attempt = db.begin("empty-key", Settings(self.root))
        db.finish(run, attempt, False)
        self.assertEqual(db.begin(None, self.cfg, run)[0], run)
        other = Settings(self.root,keys={"jevmodel":"different-fixture"})
        with self.assertRaises(Conflict):
            db.begin(None, other, run)

    def test_public_receipt_preserves_quote_digest_without_identity(self):
        record={"id":1,"attempt_id":1,"name":"forum_post","mode":"live_http","checked_at":"test",
                "status_code":200,"request":{"method":"GET"},"response":{"verified":True,"text":"a synthetic excerpt",
                "author":"synthetic author","url":"https://cooking.stackexchange.com/q/123","license":"CC BY-SA 4.0"}}
        output=public_evidence(record)
        self.assertTrue(output["response"]["attributed_locally"])
        self.assertEqual(len(output["response"]["quote_utf8_sha256"]),64)
        self.assertNotIn("synthetic author",json.dumps(output))
        self.assertNotIn("a synthetic excerpt",json.dumps(output))

    def test_storage_immutable_and_writer_lock(self):
        ref = self.db.record(self.attempt, "fixture", "test", {}, {"ok": True})
        with self.assertRaises(sqlite3.IntegrityError), self.db.db() as conn:
            conn.execute("UPDATE evidence SET name='changed' WHERE id=?", (ref,))
        with self.db.writer(), self.assertRaises(Busy), self.db.writer():
            self.fail("Two writers acquired the same run lock")

    def test_nonpublic_isolation_and_faults(self):
        result = test_isolation_drill()
        self.assertTrue(result["passed"])
        self.assertEqual(result["private_transport_calls"], 0)
        self.assertEqual(result["fault_outcomes"]["429"]["backoff_seconds"], [1, 2])
        with self.assertRaises(Denied):
            outbound(
                "tavily",
                labels={"public_approved", "internal_confidential"},
                transport=lambda *args: self.fail("network reached"),
            )

    def test_synthetic_recall_is_global(self):
        result = test_cross_category_recall()
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"], {"products": 2, "tasks": 3, "intents": 30, "mentions": 30})
        self.assertEqual(result["unrestricted_scope_products"], 0)
        for query in result["queries"]:
            self.assertEqual(len(query["choice_options"]), 13)
            self.assertIn("None", query["choice_options"])
            self.assertNotEqual(query["query_product"], query["evidence_product"])

    def test_mock_transport_cannot_write_an_operational_gate(self):
        with self.assertRaises(ValueError):
            run_checks(self.cfg, self.db, "bad", transport=lambda *a: Response(200, {}))
        with self.assertRaises(ValueError):
            discover(self.cfg, Store(self.root), self.attempt, transport=lambda *a: Response(200, {}))
        self.assertNotEqual(self.db.path, Store(self.root).path)

    def test_gate_requires_six_same_batch_results_and_review(self):
        cases = {k: "PASS" for k in CODES}
        self.assertTrue(test_gate_requires_all_six(cases, {"approved": True}))
        self.assertFalse(test_gate_requires_all_six(cases, {"approved": False}))
        cases["C0-5"] = "NOT_TESTED"
        self.assertFalse(test_gate_requires_all_six(cases, {"approved": True}))
        del cases["C0-5"]
        self.assertFalse(test_gate_requires_all_six(cases, {"approved": True}))

    def test_source_id_quote_and_approved_only(self):
        self.assertIsNone(post_id("https://example.org/questions/94603/foo"))
        self.assertIsNone(post_id("http://cooking.stackexchange.com/questions/94603/foo"))
        self.assertEqual(post_id("https://cooking.stackexchange.com/q/94603"), "94603")
        self.assertEqual(
            first_sentence("<p>This is a quoted sentence. And another.</p>"),
            "This is a quoted sentence.",
        )

        def fake(method, url, body, headers):
            if "api.tavily.com" in url:
                return Response(
                    200,
                    {
                        "results": [
                            {"url": "https://cooking.stackexchange.com/q/123", "title": "Synthetic"}
                        ]
                    },
                )
            if "/questions/123" in url:
                return Response(
                    200,
                    {
                        "items": [
                            {
                                "question_id": 123,
                                "content_license": "private",
                                "body": "Synthetic unapproved text.",
                            }
                        ]
                    },
                )
            return Response(200, {"items": []})

        cfg = Settings(self.root, keys={"tavily": "fixture"})
        quote, _, hit, _ = discover(cfg, self.db, self.attempt, fake)
        self.assertIsNone(quote)
        self.assertFalse(hit)
        self.assertNotIn("Synthetic unapproved text", json.dumps(self.db.audit(self.batch_id)))

    def test_source_check_does_not_let_one_engine_exhaust_the_lookup_budget(self):
        for with_brave in (True, False):
            with self.subTest(with_brave=with_brave):
                candidate = 207 if with_brave else 208
                seen = []

                def transport(method, url, body, headers):
                    if "api.tavily.com" in url:
                        return Response(200, {"results": [{"url": f"{FORUM_URL}{i}"} for i in range(101, 106)]})
                    if "api.search.brave.com" in url:
                        return Response(200, {"web": {"results": [{"url": FORUM_URL + "207"}]}})
                    if "/search/advanced" in url:
                        return Response(200, {"items": [{"link": FORUM_URL + "208"}]})
                    ident = int(urlsplit(url).path.rsplit("/", 1)[1])
                    seen.append(ident)
                    if ident != candidate:
                        return Response(404, {"items": []})
                    return Response(200, {"items": [self.forum_item(ident)]})

                keys = {"tavily": "tavily-fixture"}
                if with_brave:
                    keys["brave"] = "brave-fixture"
                cfg = Settings(self.root, keys=keys)
                quote, _, hit, _ = discover(cfg, self.db, self.attempt, transport)
                self.assertIsNotNone(quote)
                self.assertEqual(quote["post_id"], str(candidate))
                self.assertEqual(hit, with_brave)
                self.assertLessEqual(len(seen), 4)

    def test_formal_search_receipt_preserves_only_reported_tavily_credits(self):
        cfg = Settings(self.root, keys={"tavily": "offline-tavily-fixture"})
        cases = (("metered", {"usage": {"credits": 1}}, 1), ("unknown", {}, None))
        for request_key, metering, expected in cases:
            with self.subTest(request_key=request_key):
                _, attempt = self.db.begin(request_key, cfg)

                def fixture(method, url, payload, headers):
                    self.assertEqual(method, "POST")
                    self.assertEqual(payload["search_depth"], "basic")
                    self.assertTrue(payload["include_usage"])
                    return Response(200, {"results": [], **metering})

                _, refs, _, _ = discover(cfg, self.db, attempt, fixture, engines=("tavily",))
                row = self.db.one("SELECT * FROM evidence WHERE id=?", (refs[0],))
                row["request"] = json.loads(row.pop("request_json"))
                row["response"] = json.loads(row.pop("response_json"))
                self.assertEqual(row["response"]["credits"], expected)
                exported = public_evidence(row)["response"]
                self.assertEqual(exported["credits"], expected)
                self.assertTrue(exported["result_list_valid"])
                self.assertEqual(exported["result_count"], 0)

    def test_source_check_skips_invalid_post_metadata(self):
        malformed = [
            self.forum_item(1) | {"owner": "deleted"},
            self.forum_item(2) | {"content_license": []},
            self.forum_item(3) | {"creation_date": 10**100},
        ]

        def transport(method, url, body, headers):
            if "/search/advanced" in url:
                return Response(200, {"items": [{"link": f"{FORUM_URL}{i}"} for i in range(1, 5)]})
            ident = int(urlsplit(url).path.rsplit("/", 1)[1])
            return Response(200, {"items": [malformed[ident - 1] if ident < 4 else self.forum_item(4)]})

        quote, refs, hit, _ = discover(Settings(self.root), self.db, self.attempt, transport)
        self.assertEqual(quote["post_id"], "4")
        self.assertFalse(hit)
        published = self.db.audit(self.batch_id)["attempts"][0]["evidence"]
        posts = [row for row in published if row["id"] in refs and row["name"] == "forum_post"]
        self.assertEqual([p["response"]["verified"] for p in posts], [False, False, False, True])
        self.assertTrue(all("text" not in p["response"] for p in posts[:3]))

    @staticmethod
    def forum_item(ident):
        return {
            "question_id": ident, "content_license": "CC BY-SA 4.0",
            "link": f"{FORUM_URL}{ident}", "body": "An offline synthetic excerpt.",
            "owner": {"display_name": "Fixture"}, "creation_date": 1_600_000_000,
        }

    def test_sanitization_and_provider_partition(self):
        self.assertEqual(
            redact(
                {"Authorization": "whatever", "usage": {"input_tokens": 3}, "detail": "remove fixture"},
                ["fixture"],
            ),
            {"usage": {"input_tokens": 3}, "detail": "remove [REDACTED]"},
        )
        other = Settings(self.root, provider="typesafe", keys={"typesafe": "other"})
        self.assertIsNone(balance(self.db, other)["remaining"])
        self.assertEqual(balance(self.db, other)["records"], [])

    def test_source_review_must_match_provider_and_file_digest(self):
        import hashlib

        evidence = self.root / "review-proof"
        evidence.write_text("synthetic receipt")
        receipt = self.root / "review.json"
        body = {
            "provider": "jevmodel",
            "checked_at": "2020-01-01T00:00:00+00:00",
            "public_text_approved": True,
            "region": "fixture",
            "terms_reference": "fixture",
            "reviewer": "fixture",
            "evidence_file": "review-proof",
            "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "retention_reviewed": True,
            "subprocessors_reviewed": True,
        }
        receipt.write_text(json.dumps(body))
        self.assertTrue(Settings(self.root, review=str(receipt)).review_status()["approved"])
        self.assertFalse(
            Settings(self.root, provider="typesafe", review=str(receipt)).review_status()["approved"]
        )
        evidence.write_text("changed")
        self.assertFalse(Settings(self.root, review=str(receipt)).review_status()["approved"])

    def test_api_empty_workspace_readonly_and_validation(self):
        with TestClient(create_app(Settings(self.root)), base_url="http://localhost") as client:
            first = client.get("/api/workspace").json()
            self.assertEqual(first["history"], [])
            self.assertIsNone(first["token"]["remaining"])
            self.assertGreaterEqual(len(first["requirements"]), 64)
            self.assertEqual(len(catalogue()), len({r["requirement_id"] for r in catalogue()}))
            self.assertEqual(client.get("/api/health").json()["schema_version"], 4)
            self.assertEqual(client.get("/api/runs/" + str(uuid.uuid4()) + "/evidence").status_code, 404)
            self.assertEqual(client.post("/api/runs", json={}).status_code, 403)
            self.assertEqual(
                client.post("/api/runs", headers=AUTH, json={"request_key": "invalid"}).status_code, 422
            )
            self.assertEqual(
                client.post(
                    "/api/runs", headers={**AUTH, "Origin": "https://example.invalid"}, json={}
                ).status_code,
                403,
            )
            self.assertEqual(
                client.post("/api/runs", headers={**AUTH, "Origin": "http://["}, json={}).status_code,
                403,
            )
            self.assertEqual(
                client.post("/api/runs", headers={**AUTH, "Origin": "http://localhost"}, json={}).status_code,
                422,
            )
            self.assertEqual(client.get("/api/workspace").json()["history"], [])
            self.assertEqual(client.get("/static/app.js").status_code, 200)
            self.assertEqual(client.get("/").status_code, 200)

    def test_connection_diagnostics_keep_credentials_and_fixture_results_out_of_status(self):
        local_value = "local-fixture-credential"
        settings = Settings(self.root, provider="typesafe", keys={"typesafe": local_value})
        store = Store(self.root)
        run, attempt = store.begin("connection-test", settings)
        ref = store.record(
            attempt, "jev_shard", "synthetic_contract", {}, {"body": {"model": MODEL}}, 200
        )
        store.result(attempt, "C0-1", "BLOCKED", "offline fixture", [ref], "no real provider")
        store.finish(run, attempt, False)
        with patch(
            "urllib.request.OpenerDirector.open", side_effect=AssertionError("Read must be offline")
        ), TestClient(create_app(settings), base_url="http://localhost") as client:
            reply = client.get("/api/workspace")
        self.assertEqual(reply.status_code, 200)
        self.assertNotIn(local_value, reply.text)
        config = reply.json()["config"]
        providers = {entry["id"]: entry for entry in config["connections"]}
        self.assertEqual(set(providers), {"typesafe", "jevmodel", "tavily", "brave"})
        self.assertTrue(providers["typesafe"]["configured"])
        self.assertEqual(providers["typesafe"]["review"], "PENDING")
        self.assertEqual(providers["typesafe"]["connection"], "NOT_TESTED")
        self.assertIsNone(providers["typesafe"]["http_status"])
        self.assertFalse(providers["jevmodel"]["configured"])
        self.assertEqual(config["acceptance"], "NOT_TESTED")

    def test_offline_history_survives_restart(self):
        actual = Store(self.root)
        run, attempt = actual.begin("local-io", Settings(self.root))
        ref = actual.record(attempt, "storage_probe", "local_sqlite", {"write": 1}, {"roundtrip": 1})
        actual.result(attempt, "C0-4", "BLOCKED", "local-only", [ref], "no provider")
        actual.finish(run, attempt, False)
        with patch(
            "urllib.request.OpenerDirector.open", side_effect=AssertionError("Read must be offline")
        ):
            with TestClient(create_app(Settings(self.root)), base_url="http://localhost") as client:
                row = client.get("/api/workspace").json()["requirements"][3]
                self.assertEqual(row["status"], "BLOCKED")
                self.assertEqual(
                    client.get(f"/api/runs/{run}/evidence").json()["attempts"][0]["evidence"][0][
                        "response"
                    ],
                    {"roundtrip": 1},
                )
