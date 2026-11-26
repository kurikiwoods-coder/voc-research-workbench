"""PackyCode protocol and admission checks on isolated synthetic stores."""

from base64 import b64encode
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from test_connectivity import response_for
from src.config import MODEL, PACKYCODE_CONTRACT, PROVIDERS, Settings, validate_review
from src.dashboard.app import balance, create_app
from src.execution.checks import run_checks
from src.execution.jev import call_shards, questions, split
from src.execution.provider_diagnostics import run_probe
from src.execution.transport import Denied, Response, network, outbound
from src.raw_store.store import Conflict, Store


PROVIDER = "packycode"
ENDPOINT = "https://cf.api.fan/v1/systemone"
EXAMPLE_CREDENTIAL = "synthetic-packycode-credential"
FIXTURE_PROOF = b"PackyCode isolated synthetic review attachment"
QUOTE = {"text": "Synthetic test fixture.", "verified": True, "post_id": "fixture"}
PUBLIC = {"public_approved"}


def review_record():
    return {
        "provider": PROVIDER, "checked_at": "2026-01-01T00:00:00Z",
        "public_text_approved": True, "region": "synthetic-region",
        "terms_reference": "local:synthetic-terms", "reviewer": "synthetic-reviewer",
        "evidence_file": "synthetic-review.txt", "evidence_sha256": sha256(FIXTURE_PROOF).hexdigest(),
        "subprocessors_reviewed": True, "retention_reviewed": True, "training_use_reviewed": True,
        "deletion_reviewed": True, "upstream_reviewed": True, "zdr_terms_reviewed": True,
        "upstream_reference": "local:synthetic-upstream", "group": "typesafe-officially",
        "model": MODEL, "endpoint": ENDPOINT,
    }


def metered_response(payload, *, input_tokens=17, output_tokens=3, remaining=None):
    body = response_for(payload)
    body["usage"] = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return Response(200, body, remaining=remaining)


class PackyCodeTests(unittest.TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory(prefix="voc-packycode-fixture ")))
        self.settings = Settings(directory, provider=PROVIDER, keys={
            PROVIDER: EXAMPLE_CREDENTIAL,
            "typesafe": "synthetic-typesafe-credential",
            "jevmodel": "synthetic-jevmodel-credential",
        })
        review = {
            "record": b64encode(json.dumps(review_record()).encode()).decode(),
            "attachment": b64encode(FIXTURE_PROOF).decode(),
            "account_tag": self.settings.account_tag(),
        }
        self.approved = replace(self.settings, local_reviews={PROVIDER: review})
        self.fixture = Store(directory, fixture=True)
        self.probes = Store(directory, fixture=True, diagnostic=True)

    def recorded_body(self, report, shard=0):
        record = self.probes.ledger(report["run_id"])[shard]
        evidence = self.probes.one("SELECT response_json FROM evidence WHERE id=?", (record["evidence_id"],))
        return json.loads(evidence["response_json"])["body"]

    def test_fixed_packycode_channel_keeps_other_provider_bindings(self):
        self.assertEqual(PACKYCODE_CONTRACT["group"], "typesafe-officially")
        self.assertEqual(PACKYCODE_CONTRACT["model"], "jev-1.14.0")
        self.assertEqual(PROVIDERS[PROVIDER][0], ENDPOINT)
        self.assertEqual(PROVIDERS["typesafe"][0], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(PROVIDERS["jevmodel"][0], "https://jevmodel.org/v1/systemone")

    def test_fixed_model_shards_and_three_answer_contracts(self):
        transport = Mock(side_effect=lambda _, __, payload, ___: metered_response(payload))
        report = run_probe(self.approved, self.probes, PROVIDER, "packycode-contract", transport)
        self.assertEqual(report["scope"], "engineering_fixture")
        self.assertEqual(report["research_denominator"], 0)
        self.assertEqual(report["schema_status"], "PASS")
        self.assertEqual(report["model"], "jev-1.14.0")
        self.assertEqual([shard["questions"] for shard in report["shards"]], [8, 3])
        self.assertEqual([shard["response_model"] for shard in report["shards"]], [MODEL, MODEL])
        self.assertEqual(transport.call_count, 2)
        for call, expected in zip(transport.call_args_list, split(questions()), strict=True):
            method, url, payload, headers = call.args
            self.assertEqual((method, url), ("POST", ENDPOINT))
            self.assertEqual(set(payload), {"model", "state", "questions"})
            self.assertEqual(payload["model"], MODEL)
            self.assertEqual(payload["questions"], expected)
            self.assertEqual(headers["Authorization"], "Bearer " + EXAMPLE_CREDENTIAL)
        self.assertEqual(len({call.args[3]["Idempotency-Key"] for call in transport.call_args_list}), 2)
        fields = report["shards"][0]["response_fields"]
        self.assertIn("probabilities", fields["intent"])
        self.assertIn("probabilities", fields["friction"])
        self.assertEqual(set(fields["in_registry"]), {"type", "noul"})

    def test_wrong_returned_model_or_question_rejects_without_fallback(self):
        for option in ("model", "question_id"):
            with self.subTest(option=option):
                def wrong_identity(method, url, payload, headers):
                    body = response_for(payload)
                    if option == "model":
                        body["model"] = "jev-latest"
                    else:
                        body["answers"]["other_signal"] = body["answers"].pop("signal_1")
                    return Response(200, body)

                transport = Mock(side_effect=wrong_identity)
                reply = run_probe(self.approved, self.probes, PROVIDER, f"wrong-{option}", transport)
                self.assertEqual(reply["status"], "CAPABILITY_BLOCKED")
                self.assertIn("model_or_question_ids", reply["schema_gap"])
                self.assertEqual(transport.call_count, 1)
                self.assertEqual(transport.call_args.args[1], ENDPOINT)

    def test_missing_and_invalid_probabilities_remain_unmodified_in_ledger(self):
        def incomplete(method, url, payload, headers):
            body = metered_response(payload).body
            if "intent" in body["answers"]:
                del body["answers"]["intent"]["probabilities"]
                body["answers"]["friction"]["probabilities"].pop("0")
                del body["answers"]["in_registry"]["noul"]
            return Response(200, body)

        report = run_probe(self.approved, self.probes, PROVIDER, "schema-gaps", incomplete)
        self.assertEqual(report["status"], "CAPABILITY_BLOCKED")
        self.assertEqual(set(report["schema_gap"]), {"intent.probabilities", "friction.probabilities", "in_registry.noul"})
        answers = self.recorded_body(report)["answers"]
        self.assertNotIn("probabilities", answers["intent"])
        self.assertEqual(set(answers["friction"]["probabilities"]), {"1", "2"})
        self.assertNotIn("noul", answers["in_registry"])

    def test_missing_or_invalid_output_token_usage_blocks_diagnostic(self):
        for case in ("missing", "negative"):
            with self.subTest(case=case):
                def incomplete_usage(method, url, payload, headers):
                    response = metered_response(payload, output_tokens=0)
                    if len(payload["questions"]) == 3:
                        if case == "missing":
                            del response.body["usage"]["output_tokens"]
                        else:
                            response.body["usage"]["output_tokens"] = -1
                    return response

                report = run_probe(self.approved, self.probes, PROVIDER, f"output-usage-{case}", incomplete_usage)
                self.assertEqual(report["status"], "CAPABILITY_BLOCKED")
                self.assertEqual(report["schema_status"], "FAIL")
                self.assertEqual(report["schema_gap"], ["usage.output_tokens"])
                self.assertEqual([shard["output_tokens"] for shard in report["shards"]], [0, None])
                self.assertEqual(report["research_denominator"], 0)

    def test_http_transport_failures_do_not_fall_back_or_fabricate_usage(self):
        cases = (
            (401, "invalid_key", "retryable"), (403, "permission_denied", "retryable"),
            (402, "insufficient_balance", "retryable"), (429, "rate_limited", "retryable"),
            (502, "upstream_error", "uncertain"), (503, "upstream_error", "uncertain"),
            (None, "offline", "uncertain"),
        )
        for status, error_code, state in cases:
            with self.subTest(status=status):
                transport = Mock(return_value=Response(status, {"usage": {"input_tokens": 999}}))
                report = run_probe(self.approved, self.probes, PROVIDER, f"error-{status}", transport)
                self.assertEqual(report["status"], "ERROR")
                self.assertEqual(report["error_code"], error_code)
                self.assertEqual(report["http_status"], status)
                self.assertEqual(transport.call_count, 1)
                self.assertEqual(transport.call_args.args[1], ENDPOINT)
                record = self.probes.ledger(report["run_id"])[0]
                self.assertEqual(record["state"], state)
                self.assertIsNone(record["tokens"])

    def test_non_json_response_is_archived_as_schema_failure(self):
        def non_json(method, url, payload, headers):
            stream = BytesIO(b"<html>synthetic response</html>")
            stream.status = 200
            stream.headers = {}
            with patch("src.execution.transport.build_opener") as opener:
                opener.return_value.open.return_value = stream
                return network(method, url, payload, headers)

        report = run_probe(self.approved, self.probes, PROVIDER, "non-json-response", non_json)
        self.assertEqual(report["status"], "CAPABILITY_BLOCKED")
        self.assertIn("model_or_question_ids", report["schema_gap"])
        first = self.probes.ledger(report["run_id"])[0]
        self.assertEqual(self.recorded_body(report), {"error": "non_json_response"})
        self.assertIsNone(first["tokens"])

    def test_429_retries_and_402_second_shard_resume_share_the_same_keys(self):
        run_id, attempt = self.fixture.begin("packycode-resume", self.approved)
        calls = []

        def transport(method, url, payload, headers):
            calls.append(headers["Idempotency-Key"])
            if len(calls) == 1:
                return Response(429, {}, retry_after="1")
            if len(calls) == 3:
                return Response(402, {"error": "fixture_insufficient_balance"})
            return metered_response(payload)

        sleep = Mock()
        first = call_shards(self.approved, self.fixture, run_id, attempt, QUOTE, transport, sleep)
        self.assertEqual(first[1], [True])
        self.assertIn("402", first[3])
        sleep.assert_called_once_with(1)
        self.assertEqual(calls[0], calls[1])
        self.fixture.finish(run_id, attempt, False)
        reopened = Store(self.settings.directory, fixture=True)
        _, second_attempt = reopened.begin(None, self.approved, run_id)
        second = call_shards(self.approved, reopened, run_id, second_attempt, QUOTE, transport, sleep)
        self.assertEqual(second[1:], ([True, True], [], None))
        self.assertEqual(calls[2], calls[3])
        self.assertNotEqual(calls[0], calls[2])
        self.assertEqual(call_shards(self.approved, reopened, run_id, second_attempt, QUOTE, transport)[1:],
                         ([True, True], [], None))
        self.assertEqual(len(calls), 4)
        self.assertEqual([row["tokens"] for row in reopened.ledger(run_id)], [17, 17])

    def test_uncertain_502_is_never_retried_with_the_same_or_a_fallback_provider(self):
        run_id, attempt = self.fixture.begin("packycode-unknown", self.approved)
        transport = Mock(return_value=Response(502, {}))
        first = call_shards(self.approved, self.fixture, run_id, attempt, QUOTE, transport)
        self.assertIn("502", first[3])
        self.assertEqual(self.fixture.ledger(run_id)[0]["state"], "uncertain")
        reason = call_shards(self.approved, self.fixture, run_id, attempt, QUOTE, transport)[3]
        self.assertIn("待核对", reason)
        transport.assert_called_once()
        for provider in ("typesafe", "jevmodel"):
            with self.subTest(provider=provider), self.assertRaises(Conflict):
                self.fixture.begin(None, replace(self.approved, provider=provider), run_id)
        with self.assertRaises(Conflict):
            self.fixture.begin(None, replace(self.approved, keys={PROVIDER: "synthetic-rotated"}), run_id)

    def test_packycode_requires_independent_proof_and_review_for_current_account(self):
        document = review_record()
        self.assertTrue(validate_review(PROVIDER, json.dumps(document).encode(), FIXTURE_PROOF)["approved"])
        for key in ("upstream_reference", "zdr_terms_reviewed", "training_use_reviewed", "deletion_reviewed",
                    "upstream_reviewed", "subprocessors_reviewed", "retention_reviewed", "group", "model",
                    "endpoint", "public_text_approved"):
            with self.subTest(key=key):
                incomplete = deepcopy(document)
                del incomplete[key]
                self.assertFalse(validate_review(PROVIDER, json.dumps(incomplete).encode(), FIXTURE_PROOF)["approved"])
        other_attestation = document | {"provider": "typesafe", "zdr_enabled": True}
        self.assertFalse(validate_review(PROVIDER, json.dumps(other_attestation).encode(), FIXTURE_PROOF)["approved"])
        self.assertFalse(validate_review(PROVIDER, json.dumps(document).encode(), b"Different proof")["approved"])
        self.assertTrue(self.approved.review_status()["approved"])
        rotated = replace(self.approved, keys={PROVIDER: "synthetic-rotated"})
        self.assertFalse(rotated.review_status()["approved"])
        review_file = self.settings.directory / "synthetic-review.json"
        review_file.write_text(json.dumps(document), encoding="utf-8")
        (self.settings.directory / document["evidence_file"]).write_bytes(FIXTURE_PROOF)
        self.assertFalse(replace(self.settings, review=str(review_file)).review_status()["approved"])
        transport = Mock(side_effect=AssertionError("unapproved provider sent a request"))
        diagnostic = run_probe(self.settings, self.probes, PROVIDER, "unapproved", transport)
        self.assertEqual(diagnostic["status"], "REVIEW_REQUIRED")
        transport.assert_not_called()

    def test_outbound_rejects_internal_text_and_unapproved_routes(self):
        transport = Mock(side_effect=AssertionError("denied transport was invoked"))
        with self.assertRaises(Denied):
            outbound(PROVIDER, labels={"internal_cx"}, method="POST", body={"state": "fixture"}, transport=transport)
        with self.assertRaises(Denied):
            outbound(PROVIDER, labels=PUBLIC, method="POST", path="/other", transport=transport)
        transport.assert_not_called()

    def test_local_review_requires_current_key_and_is_cleared_by_rotation_and_deletion(self):
        settings = replace(self.settings, keys={})
        app = create_app(settings)
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 30001)) as client:
            client.headers.update({"Origin": "http://localhost", "X-VOC-Action": "connectivity"})
            review_path = "/api/setup/packycode/review"
            key_path = "/api/setup/packycode/key"
            materials = {
                "record": b64encode(json.dumps(review_record()).encode()).decode(),
                "attachment": b64encode(FIXTURE_PROOF).decode(),
            }
            self.assertEqual(client.put(review_path, json=materials).status_code, 409)
            self.assertTrue(client.put(key_path, json={"key": EXAMPLE_CREDENTIAL}).is_success)
            self.assertTrue(client.put(review_path, json=materials).json()["approved"])
            self.assertTrue(app.state.vault.read()["reviews"][PROVIDER]["account_tag"])
            self.assertTrue(client.put(key_path, json={"key": "synthetic-preamble-rotation"}).is_success)
            self.assertNotIn(PROVIDER, app.state.vault.read()["reviews"])
            self.assertTrue(client.put(review_path, json=materials).json()["approved"])
            self.assertTrue(client.delete(key_path).is_success)
            self.assertNotIn(PROVIDER, app.state.vault.read()["reviews"])
            self.assertNotIn(EXAMPLE_CREDENTIAL, client.get("/api/workspace").text)

    def test_live_paths_stay_closed_even_with_approved_synthetic_configuration(self):
        store = Store(self.settings.directory)
        diagnostics = Store(self.settings.directory, diagnostic=True)
        run_id, attempt = store.begin("packed-preflight", self.approved)
        with patch("src.execution.transport.build_opener", side_effect=AssertionError("network is prohibited")) as opener:
            with self.assertRaises(Denied):
                outbound(PROVIDER, labels=PUBLIC, method="POST", body={"state": "synthetic"})
            result = call_shards(self.approved, store, run_id, attempt, QUOTE)
            self.assertTrue(result[3])
            reply = run_probe(self.approved, diagnostics, PROVIDER, "blocked-live-diagnostics")
            self.assertEqual(reply["status"], "LIVE_TEST_BLOCKED")
            with patch("src.execution.checks.discover") as discover, self.assertRaises(Conflict):
                run_checks(self.approved, store, "blocked-formal-acceptance")
            discover.assert_not_called()
            opener.assert_not_called()
        self.assertEqual(store.ledger(run_id), [])
        self.assertEqual(len(store.rows("SELECT id FROM runs")), 1)
        self.assertEqual(diagnostics.rows("SELECT id FROM runs"), [])

    def test_diagnostic_ledger_and_report_omit_echoed_credentials(self):
        def echoed_fixture(method, url, payload, headers):
            body = metered_response(payload).body
            body["detail"] = headers["Authorization"]
            body["api_key"] = EXAMPLE_CREDENTIAL
            return Response(200, body)

        report = run_probe(self.approved, self.probes, PROVIDER, "credential-redaction", echoed_fixture)
        self.assertEqual(report["schema_status"], "PASS")
        self.assertEqual(self.recorded_body(report)["detail"], "Bearer [REDACTED]")
        archive = self.probes.rows("SELECT request_json,response_json FROM evidence")
        self.assertNotIn(EXAMPLE_CREDENTIAL, json.dumps([report, archive]))
        self.assertNotIn("api_key", self.recorded_body(report))

    def test_estimated_cost_never_becomes_an_actual_charge_or_balance(self):
        def success(method, url, payload, headers):
            return metered_response(payload, input_tokens=1_000_000, output_tokens=31, remaining=80)

        initial = balance(self.fixture, self.approved)["billing"]
        self.assertEqual(initial["charge_status"], "NO_REQUESTS")
        self.assertIsNone(initial["actual_charge_usd"])
        self.assertIsNone(initial["estimated_usd"])
        report = run_probe(self.approved, self.probes, PROVIDER, "billing-fixture", success)
        self.assertEqual(report["schema_status"], "PASS")
        total = balance(self.fixture, self.approved, self.probes)
        billing = total["billing"]
        self.assertEqual(billing["input_tokens"], 2_000_000)
        self.assertEqual(billing["output_tokens"], 62)
        self.assertEqual(Decimal(billing["estimated_usd"]), Decimal("0.588"))
        self.assertTrue(billing["rate_source"])
        self.assertIsNone(billing["actual_charge_usd"])
        self.assertEqual(billing["charge_status"], "UNKNOWN")
        self.assertEqual(billing["balance_status"], "UNSYNCED")
        self.assertIsNone(total["remaining"])
        self.assertIsNone(total["sync_method"])
