"""Synthetic regression for the dedicated PackyCode preflight."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_connectivity import response_for
from src.execution import packycode_preflight
from src.execution.jev import questions, split
from src.execution.packycode_preflight import SYNTHETIC_STATE, run_preflight
from src.execution.transport import Denied, Response
from src.raw_store.store import Busy, Conflict, Store


MODEL = "jev-1.14.0"
ENDPOINT = "https://cf.api.fan/v1/systemone"
KEY = "synthetic-packycode-preflight-test-credential"
VAULT_REVISION = "a" * 64


def response(payload, *, input_tokens=17, output_tokens=3):
    body = response_for(payload)
    body["usage"] = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    for name, question in payload["questions"].items():
        if question["type"] == "score":
            body["answers"][name]["legend"] = {
                str(index): label for index, label in enumerate(question["criteria"])
            }
    return Response(200, body)


def console_acknowledgement(_shard):
    return "0.01", "1.99"


class PackyCodePreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-packycode-preflight ")))
        self.store = self.fixture_store("main")
        self.proof = self.directory / "operator.json"
        self.document = {
            "provider": "packycode",
            "group": "typesafe-officially",
            "model": MODEL,
            "endpoint": ENDPOINT,
            "protocol": "SystemOne",
            "synthetic_use_permitted": True,
            "current_key_entitled": True,
            "quota_available": True,
            "vault_sha256": VAULT_REVISION,
            "token_quota_usd": "2.00",
            "token_remaining_usd": "2.00",
            "quota_resets": False,
            "evidence_reference": "local:synthetic operator evidence",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        self.write_evidence(self.document)

    def fixture_store(self, name):
        return Store(self.directory / name, diagnostic=True, fixture=True)

    def write_evidence(self, document):
        self.proof.write_text(json.dumps(document), encoding="utf-8")

    def run_probe(
        self, transport, store=None, key=KEY, vault_revision=VAULT_REVISION,
        recheck_vault=None, reconcile=console_acknowledgement, resume_second=False,
    ):
        return run_preflight(
            store or self.store, key, self.proof, vault_revision=vault_revision,
            recheck_vault=recheck_vault, reconcile=reconcile, resume_second=resume_second,
            transport=transport,
        )

    def assert_consumed(self, *, store=None, key=KEY, vault_revision=VAULT_REVISION):
        transport = Mock(side_effect=AssertionError("Consumed authorization must not send"))
        try:
            self.run_probe(transport, store=store, key=key, vault_revision=vault_revision)
        except (Denied, Conflict):
            pass
        transport.assert_not_called()

    def test_two_fixed_posts_and_isolated_receipts(self):
        def echo_fixture(_method, _url, payload, headers):
            reply = response(payload)
            reply.body["api_key"] = KEY
            reply.body["credential_echo"] = headers["Authorization"]
            return reply

        transport = Mock(side_effect=echo_fixture)
        reconcile = Mock(side_effect=console_acknowledgement)
        report = self.run_probe(transport, reconcile=reconcile)
        self.assertEqual(transport.call_count, 2)
        expected_groups = split(questions())
        for call, expected in zip(transport.call_args_list, expected_groups, strict=True):
            method, url, payload, headers = call.args
            self.assertEqual((method, url, payload["model"]), ("POST", ENDPOINT, MODEL))
            self.assertEqual(set(payload), {"model", "state", "questions"})
            self.assertEqual(payload["questions"], expected)
            self.assertEqual(headers["Authorization"], "Bearer " + KEY)
            self.assertEqual(payload["state"], SYNTHETIC_STATE)
        self.assertEqual([len(group) for group in expected_groups], [8, 3])
        self.assertEqual(len({call.args[3]["Idempotency-Key"] for call in transport.call_args_list}), 2)
        self.assertEqual(report["status"], "PASS")
        self.assertIsNone(report["stop_reason"])
        self.assertEqual(report["posts_reserved"], 2)
        self.assertEqual(report["research_denominator"], 0)
        self.assertEqual((report["input_tokens"], report["output_tokens"]), (34, 6))
        self.assertIsNone(report["actual_charge"])
        self.assertIsNone(report["balance"])
        self.assertEqual([shard["question_ids"] for shard in report["shards"]], [list(group) for group in expected_groups])
        self.assertEqual(set(report["answers"]), set(questions()))
        reconcile.assert_called_once()
        first_shard = reconcile.call_args.args[0]
        self.assertEqual(first_shard["question_ids"], list(expected_groups[0]))
        self.assertEqual(first_shard["http_status"], 200)
        self.assertEqual(first_shard["input_tokens"], 17)
        self.assertEqual(first_shard["response_model"], MODEL)
        self.assertNotIn(KEY, json.dumps(first_shard))
        ledger = self.store.ledger(report["run_id"])
        self.assertEqual([row["tokens"] for row in ledger], [17, 17])
        self.assertEqual([row["state"] for row in ledger], ["received", "received"])
        self.assertEqual([row["shard_no"] for row in ledger], [1, 2])
        self.assertEqual(len({row["evidence_id"] for row in ledger}), 2)
        archive = self.store.rows("SELECT request_json,response_json FROM evidence")
        self.assertNotIn(KEY, json.dumps([report, archive]))
        self.assertEqual(self.store.rows("PRAGMA integrity_check"), [{"integrity_check": "ok"}])
        self.assertEqual(self.store.rows("PRAGMA foreign_key_check"), [])
        self.assertEqual(self.store.rows("SELECT * FROM results"), [])

    def test_invalid_authorization_never_claims_budget(self):
        transport = Mock(side_effect=AssertionError("Invalid authorization sent a request"))
        for field, value in (
            ("provider", "typesafe"),
            ("group", "default"),
            ("endpoint", "https://example.com/v1/systemone"),
            ("protocol", "Other"),
            ("model", "jev-latest"),
            ("synthetic_use_permitted", False),
            ("current_key_entitled", 1),
            ("quota_available", False),
            ("vault_sha256", "b" * 64),
            ("token_quota_usd", "2.01"),
            ("token_quota_usd", 2),
            ("token_quota_usd", "NaN"),
            ("token_quota_usd", "1.99"),
            ("token_remaining_usd", "0"),
            ("quota_resets", True),
            ("quota_resets", 0),
            ("evidence_reference", " "),
            ("expires_at", "2020-01-01T00:00:00+00:00"),
            ("expires_at", "2090-01-01T00:00:00"),
        ):
            with self.subTest(field=field, value=value):
                self.write_evidence(self.document | {field: value})
                with self.assertRaises(Denied):
                    self.run_probe(transport)
        self.proof.unlink()
        with self.assertRaises(Denied):
            self.run_probe(transport)
        self.proof.write_text("{", encoding="utf-8")
        with self.assertRaises(Denied):
            self.run_probe(transport)
        self.write_evidence(self.document | {"state": "unexpected operator text"})
        with self.assertRaises(Denied):
            self.run_probe(transport)
        self.write_evidence(self.document)
        with self.assertRaises(Denied):
            self.run_probe(transport, key="")
        self.assertEqual(self.store.rows("SELECT id FROM runs"), [])
        transport.assert_not_called()

    def test_formal_store_and_network_fixture_are_rejected(self):
        formal = Store(self.directory / "formal")
        transport = Mock(side_effect=AssertionError("Formal store reached transport"))
        with self.assertRaises(Denied):
            self.run_probe(transport, store=formal)
        with patch("src.execution.transport.build_opener") as opener:
            with self.assertRaises(Denied):
                run_preflight(self.store, KEY, self.proof, vault_revision=VAULT_REVISION)
            opener.assert_not_called()
        transport.assert_not_called()
        self.assertEqual(formal.rows("SELECT id FROM runs"), [])
        self.assertEqual(self.store.rows("SELECT id FROM runs"), [])

    def test_cli_checks_local_evidence_before_using_dpapi_and_fixed_network(self):
        ciphertext = b"synthetic encrypted vault fixture"
        vault_path = self.directory / "local-api.json"
        vault_path.write_bytes(ciphertext)
        local_os = SimpleNamespace(name="nt", getenv=lambda _: str(self.directory))
        execute = ["packycode_preflight", "--execute", "--account-evidence", str(self.proof)]

        def model_post(request, *, timeout):
            self.assertEqual((request.method, request.full_url), ("POST", ENDPOINT))
            self.assertEqual(request.get_header("Authorization"), "Bearer " + KEY)
            payload = json.loads(request.data)
            self.assertEqual(payload["state"], SYNTHETIC_STATE)
            stream = BytesIO(json.dumps(response(payload).body).encode())
            stream.status = 200
            stream.headers = {}
            return stream

        with (
            patch.object(packycode_preflight, "PROBE_DIRECTORY", self.directory / "isolated-cli"),
            patch.object(packycode_preflight, "os", local_os),
            patch.object(packycode_preflight, "CredentialVault") as vault,
            patch.object(packycode_preflight, "reconcile_first", side_effect=console_acknowledgement),
            patch("src.execution.transport.build_opener") as opener,
        ):
            vault.return_value.path = vault_path
            vault.return_value.read.return_value = {"provider": "packycode", "keys": {"packycode": KEY}}
            opener.return_value.open.side_effect = model_post

            with patch("sys.argv", ["packycode_preflight"]), redirect_stdout(StringIO()) as stdout:
                self.assertEqual(packycode_preflight.main(), 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "NOT_TESTED")
            vault.assert_not_called()

            with patch("sys.argv", execute), redirect_stdout(StringIO()) as stdout:
                self.assertEqual(packycode_preflight.main(), 2)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "BLOCKED")
            vault.return_value.read.assert_not_called()
            opener.assert_not_called()

            self.write_evidence(self.document | {"vault_sha256": sha256(ciphertext).hexdigest()})
            with patch("sys.argv", execute), redirect_stdout(StringIO()) as stdout:
                self.assertEqual(packycode_preflight.main(), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["posts_reserved"], 2)
            self.assertNotIn(KEY, stdout.getvalue())
            vault.return_value.read.assert_called_once()
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_failed_http_or_ambiguous_response_is_never_retried(self):
        for status in (302, 401, 402, 403, 422, 429, 502, None):
            with self.subTest(status=status):
                store = self.fixture_store(f"http-{status}")
                transport = Mock(return_value=Response(status, {"error": "synthetic"}, retry_after="1"))
                report = self.run_probe(transport, store=store)
                transport.assert_called_once()
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(len(store.ledger(report["run_id"])), 1)
                self.assertIsNone(store.ledger(report["run_id"])[0]["tokens"])
                self.assert_consumed(store=store)

    def test_process_interruption_after_reservation_keeps_authorization_consumed(self):
        transport = Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.run_probe(transport)
        transport.assert_called_once()
        self.assertEqual(len(self.store.rows("SELECT id FROM runs")), 1)
        self.assertEqual(len(self.store.rows("SELECT request_key FROM shards")), 1)
        reopened = self.fixture_store("main")
        no_retry = Mock(side_effect=AssertionError("Interrupted preflight must not retry"))
        report = self.run_probe(no_retry, store=reopened)
        self.assertEqual(report["status"], "INTERRUPTED_OR_RUNNING")
        self.assertEqual(report["posts_reserved"], 1)
        self.assertEqual(report["ledger"][0]["state"], "sending")
        no_retry.assert_not_called()

    def test_wrong_model_question_or_incomplete_answer_stops_before_second_post(self):
        def incomplete(change, payload):
            reply = response(payload)
            body = reply.body
            if change == "wrong model":
                body["model"] = "jev-latest"
            elif change == "wrong id":
                body["answers"]["unknown"] = body["answers"].pop("signal_1")
            elif change == "choice probabilities":
                body["answers"]["intent"]["probabilities"].pop("None")
            elif change == "score probabilities":
                body["answers"]["friction"]["probabilities"].pop("1")
            elif change == "score legend":
                body["answers"]["friction"].pop("legend")
            else:
                body["answers"]["in_registry"].pop("noul")
            return reply

        cases = {
            "wrong model": "model_or_question_ids",
            "wrong id": "model_or_question_ids",
            "choice probabilities": "intent.probabilities",
            "score probabilities": "friction.probabilities",
            "score legend": "friction.legend",
            "noul": "in_registry.noul",
        }
        for index, (change, gap) in enumerate(cases.items()):
            with self.subTest(change=change):
                store = self.fixture_store(f"contract-{index}")
                transport = Mock(side_effect=lambda _method, _url, payload, _headers: incomplete(change, payload))
                report = self.run_probe(transport, store=store)
                transport.assert_called_once()
                self.assertEqual(report["status"], "BLOCKED")
                self.assertIn(gap, report["shards"][0]["schema_gaps"])
                self.assertEqual(len(store.ledger(report["run_id"])), 1)
                self.assert_consumed(store=store)

    def test_second_post_uses_local_input_projection_and_checks_reported_total(self):
        cases = [
            (34_464, 3, 65_536, 2, "PASS"),
            (34_464, 3, 65_537, 2, "BLOCKED"),
            (34_465, 3, 65_536, 1, "BLOCKED"),
            (65_536, 3, 65_536, 1, "BLOCKED"),
            (None, 3, 65_536, 1, "BLOCKED"),
            (True, 3, 65_536, 1, "BLOCKED"),
            (17, None, 65_536, 1, "BLOCKED"),
            (17, -1, 65_536, 1, "BLOCKED"),
        ]
        for index, (input_tokens, output_tokens, second_input, post_count, status) in enumerate(cases):
            with self.subTest(input_tokens=input_tokens, output_tokens=output_tokens, second_input=second_input):
                store = self.fixture_store(f"budget-{index}")

                def metered(_method, _url, payload, _headers):
                    if len(payload["questions"]) == 3:
                        return response(payload, input_tokens=second_input)
                    return response(payload, input_tokens=input_tokens, output_tokens=output_tokens)

                transport = Mock(side_effect=metered)
                report = self.run_probe(transport, store=store)
                self.assertEqual(transport.call_count, post_count)
                self.assertEqual(report["status"], status)
                if status == "PASS":
                    self.assertEqual(report["input_tokens"], input_tokens + second_input)
                self.assert_consumed(store=store)

    def test_rotated_credential_or_fresh_evidence_does_not_allow_another_test(self):
        transport = Mock(side_effect=lambda _method, _url, payload, _headers: response(payload))
        self.run_probe(transport)
        self.assertEqual(transport.call_count, 2)
        rotated_revision = "b" * 64
        with self.assertRaises(Denied):
            self.run_probe(transport, key="synthetic-rotated-credential", vault_revision=rotated_revision)
        self.write_evidence(self.document | {
            "evidence_reference": "local:later synthetic operator evidence", "vault_sha256": rotated_revision,
        })
        self.assert_consumed(
            store=self.fixture_store("main"), key="synthetic-rotated-credential", vault_revision=rotated_revision,
        )
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(len(self.store.rows("SELECT id FROM runs")), 1)

    def test_second_post_requires_verified_first_charge_and_sufficient_remaining_quota(self):
        cases = (
            (None, "2.00", 1),
            (Mock(return_value=None), "2.00", 1),
            (Mock(return_value=("unknown", "1.99")), "2.00", 1),
            (Mock(return_value=("0.00", "1.99")), "2.00", 1),
            (Mock(return_value=("0.01", "0.019")), "0.029", 1),
            (Mock(return_value=("0.01", "2.00")), "2.00", 1),
            (Mock(return_value=("0.01", "0.02")), "2.00", 1),
            (Mock(return_value=("0.01", "0.02")), "0.03", 2),
            (Mock(return_value=("0.00014", "2.00")), "2.00", 2),
        )
        for index, (reconcile, starting_balance, post_count) in enumerate(cases):
            with self.subTest(index=index):
                store = self.fixture_store(f"reconcile-{index}")
                transport = Mock(side_effect=lambda _method, _url, payload, _headers: response(payload))
                self.write_evidence(self.document | {"token_remaining_usd": starting_balance})
                report = self.run_probe(transport, store=store, reconcile=reconcile)
                self.assertEqual(report["status"], "PASS" if post_count == 2 else "BLOCKED")
                self.assertEqual(report["posts_reserved"], post_count)
                self.assertEqual(transport.call_count, post_count)
                if reconcile is not None:
                    reconcile.assert_called_once()
                self.assert_consumed(store=store)

    def test_credential_rotation_between_shards_halts_one_shot(self):
        recheck_vault = Mock(side_effect=[VAULT_REVISION, "b" * 64])
        transport = Mock(side_effect=lambda _method, _url, payload, _headers: response(payload))
        report = self.run_probe(transport, recheck_vault=recheck_vault)
        transport.assert_called_once()
        self.assertEqual(recheck_vault.call_count, 2)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["stop_reason"], "account_configuration_changed")
        self.assertEqual(report["posts_reserved"], 1)
        self.assertEqual(report["input_tokens"], 17)
        self.assert_consumed()

    def test_resume_uses_one_existing_first_shard_and_appends_a_second_receipt(self):
        transport = Mock(side_effect=lambda _method, _url, payload, _headers: response(payload))
        first = self.run_probe(transport, reconcile=None)
        self.assertEqual(first["stop_reason"], "first_shard_billing_unverified")
        transport.assert_called_once()
        prior_rows = self.store.rows("SELECT * FROM evidence ORDER BY id")
        prior_ledger = self.store.ledger(first["run_id"])
        reopened = self.fixture_store("main")

        invalid = Mock(return_value=("0.00", "2.00"))
        try:
            blocked = self.run_probe(transport, store=reopened, reconcile=invalid, resume_second=True)
        except (Denied, Conflict):
            pass
        else:
            self.assertEqual(blocked["status"], "BLOCKED")
        invalid.assert_called_once()
        transport.assert_called_once()
        self.assertEqual(reopened.ledger(first["run_id"]), prior_ledger)

        reconciled = Mock(side_effect=console_acknowledgement)
        report = self.run_probe(transport, store=reopened, reconcile=reconciled, resume_second=True)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["run_id"], first["run_id"])
        self.assertEqual(report["posts_reserved"], 2)
        self.assertEqual((report["input_tokens"], report["output_tokens"]), (34, 6))
        self.assertEqual(set(report["answers"]), set(questions()))
        self.assertEqual(transport.call_count, 2)
        method, url, payload, headers = transport.call_args.args
        self.assertEqual((method, url, payload["state"]), ("POST", ENDPOINT, SYNTHETIC_STATE))
        self.assertEqual(payload["questions"], split(questions())[1])
        reconciled.assert_called_once_with(first["shards"][0])
        self.assertEqual(reopened.ledger(first["run_id"])[0], prior_ledger[0])
        self.assertNotEqual(headers["Idempotency-Key"], prior_ledger[0]["request_key"])
        rows = reopened.rows("SELECT * FROM evidence ORDER BY id")
        self.assertEqual(rows[:len(prior_rows)], prior_rows)
        self.assertGreater(len(rows), len(prior_rows))

        try:
            self.run_probe(transport, store=reopened, resume_second=True)
        except (Denied, Conflict):
            pass
        self.assertEqual(transport.call_count, 2)

    def test_resume_requires_eligible_state_intact_ledger_and_original_account_proof(self):
        transport = Mock(side_effect=AssertionError("Ineligible resume reached transport"))
        recoverable = self.fixture_store("recoverable")
        metered = Mock(side_effect=lambda _method, _url, payload, _headers: response(payload))
        self.run_probe(
            metered, store=recoverable, reconcile=None,
        )
        inconsistent_ledger = self.fixture_store("inconsistent-ledger")
        first = self.run_probe(metered, store=inconsistent_ledger, reconcile=None)
        with inconsistent_ledger.db() as connection:
            connection.execute("UPDATE shards SET tokens=100 WHERE run_id=? AND shard_no=1", (first["run_id"],))
        invalid_response = self.fixture_store("invalid-response")
        self.run_probe(Mock(return_value=Response(403, {})), store=invalid_response)
        cases = (
            ("empty", self.store, self.document, KEY, VAULT_REVISION),
            ("non-billing failure", invalid_response, self.document, KEY, VAULT_REVISION),
            ("inconsistent first usage", inconsistent_ledger, self.document, KEY, VAULT_REVISION),
            ("changed proof", recoverable, self.document | {"evidence_reference": "local:other"}, KEY, VAULT_REVISION),
            ("changed key", recoverable, self.document, "synthetic-other-credential", VAULT_REVISION),
            ("changed vault", recoverable, self.document | {"vault_sha256": "b" * 64}, KEY, "b" * 64),
        )
        for label, store, proof, key, revision in cases:
            with self.subTest(case=label):
                self.write_evidence(proof)
                reconcile = Mock(side_effect=AssertionError("Ineligible resume requested reconciliation"))
                try:
                    report = self.run_probe(
                        transport, store=store, key=key, vault_revision=revision,
                        reconcile=reconcile, resume_second=True,
                    )
                except (Denied, Conflict):
                    pass
                else:
                    self.assertNotEqual(report["status"], "PASS")
                reconcile.assert_not_called()
                transport.assert_not_called()
        self.assertEqual(self.store.rows("SELECT id FROM runs"), [])

    def test_concurrent_resume_and_interrupted_second_shard_never_retry(self):
        first_transport = Mock(side_effect=lambda _method, _url, payload, _headers: response(payload))
        first = self.run_probe(first_transport, reconcile=None)
        entered = Event()
        release = Event()

        def interrupt_post(_method, _url, payload, _headers):
            self.assertEqual(payload["questions"], split(questions())[1])
            entered.set()
            if not release.wait(5):
                raise AssertionError("Concurrent test did not release the second request")
            raise KeyboardInterrupt

        second_transport = Mock(side_effect=interrupt_post)
        extra_transport = Mock(side_effect=AssertionError("Reserved second shard must not be retried"))
        reopened = self.fixture_store("main")
        with ThreadPoolExecutor(max_workers=2) as executor:
            resumed = executor.submit(self.run_probe, second_transport, resume_second=True)
            try:
                self.assertTrue(entered.wait(5))
                try:
                    self.run_probe(extra_transport, store=reopened, resume_second=True)
                except (Busy, Conflict, Denied):
                    pass
                extra_transport.assert_not_called()
            finally:
                release.set()
            with self.assertRaises(KeyboardInterrupt):
                resumed.result(timeout=5)
        first_transport.assert_called_once()
        second_transport.assert_called_once()
        self.assertEqual([row["state"] for row in reopened.ledger(first["run_id"])], ["received", "sending"])
        try:
            self.run_probe(extra_transport, store=reopened, resume_second=True)
        except (Denied, Conflict):
            pass
        extra_transport.assert_not_called()

    def test_concurrent_triggers_share_the_same_one_shot_limit(self):
        entered = Event()
        release = Event()

        def hold_first_post(_method, _url, payload, _headers):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Concurrent test did not release the first request")
            return response(payload)

        active = Mock(side_effect=hold_first_post)
        contender = Mock(side_effect=AssertionError("Second concurrent command sent a request"))
        second_store = self.fixture_store("main")
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.run_probe, active)
            try:
                self.assertTrue(entered.wait(5))
                try:
                    self.run_probe(contender, store=second_store)
                except (Busy, Conflict, Denied):
                    pass
                contender.assert_not_called()
            finally:
                release.set()
            first.result(timeout=5)
        self.assertEqual(active.call_count, 2)
        self.assertEqual(len(self.store.rows("SELECT id FROM runs")), 1)
