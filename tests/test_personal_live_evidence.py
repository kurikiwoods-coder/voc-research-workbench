from copy import deepcopy
import unittest

from src.config import MODEL
from src.execution import jev
from src.execution.personal_live_evidence import (
    INDEX, ISOLATION_CHECKS, REGISTRY, REQUIREMENTS, SLOTS, _digest, evaluate_formal_batch,
)
from src.ingestion.public_source import DOMAIN


QUOTE = "An imaginary local test quote."
REDACTED = "An imaginary local test excerpt."
URL = "https://cooking.stackexchange.com/questions/123"
BATCH = "synthetic-test-batch"


def _answers(asked):
    answers = {}
    for name, question in asked.items():
        kind = question["type"]
        if kind == "noul":
            answers[name] = {"type": "noul", "noul": .5}
        elif kind == "choice":
            keys = list(question["criteria"])
            answers[name] = {"type": "choice", "choice": keys[0], "confidence": 1,
                             "probabilities": {key: int(key == keys[0]) for key in keys}}
        else:
            answers[name] = {"type": "score", "score": 0, "confidence": 1,
                             "probabilities": {"0": 1, "1": 0, "2": 0},
                             "legend": {str(index): label for index, label in enumerate(question["criteria"])}}
    return answers


class FormalMatrixTests(unittest.TestCase):
    def setUp(self):
        self.archive = {}
        self.view = {
            "batch": {"batch_id": BATCH, "mode": "formal_live", "edition": "PERSONAL",
                      "purpose": "g1_personal_acceptance", "state": "evidence_review",
                      "currency": "USD", "cost_limit": 15, "single_cost": 5, "request_limit": 4,
                      "credit_limit": 1, "input_limit": 4, "output_limit": 2, "token_limit": 6},
            "requests": [], "grants": [], "receipts": [], "evidence": [],
        }
        self.link("tavily", {"query": "fictional quality check", "include_domains": [DOMAIN]},
                  {"results": [{"url": URL, "actual_url": URL + "/test"}], "usage": {"credits": 1}})
        self.link("stackexchange", {"url": URL, "site": "cooking", "filter": "withbody"},
                  {"items": [{"question_id": 123, "link": URL, "body": QUOTE,
                              "content_license": "CC BY-SA 4.0",
                              "owner": {"display_name": "Synthetic Author"}, "creation_date": 100}],
                   "provenance": {"collected_at": "2026-11-26T12:00:00+00:00", "final_url": URL + "/test",
                                  "method": "Stack Exchange API /questions/{id}", "classification": "public_approved",
                                  "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"}},
                  quote=QUOTE)
        questions = jev.questions()
        questions["intent"] = jev.intent_question({f"intent-{index}": f"Definition {index}"
                                                   for index in range(11)})
        for asked in jev.split(questions):
            self.link("packycode", {"model": MODEL, "state": REDACTED, "questions": asked},
                      {"model": MODEL, "answers": _answers(asked),
                       "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}}, quote=REDACTED)

        self.proof("C0-4", {
            "sqlite_reopened": True, "restart_readback": True, "idempotent_readback": True,
            "duplicate_charge_prevented": True, "currency": "USD", "integrity_check": "ok",
            "foreign_key_violations": 0,
            "charges": {receipt["request_id"]: {
                "actual_units": receipt["actual_units"], "bill_ref": f"bill-{receipt['request_id']}",
                "provider_request_id": receipt["provider_request_id"],
                "provider": receipt["provider"], "account_ref": receipt["account_ref"],
            } for receipt in self.view["receipts"]},
        })
        self.proof("C0-5", {
            "passed": True, "synthetic_cases": 36, "blocked_before_transport": 36, "private_transport_calls": 0,
            "external_requests": 0, "formal_cases": dict.fromkeys(ISOLATION_CHECKS, True),
        })
        self.proof("C0-6", {
            "passed": True, "counts": {"products": 2, "tasks": 3, "intents": 30}, "orphan_links": 0,
            "dataset": "synthetic_smoke", "research_denominator": 0, "k": 1,
            "registry_version": REGISTRY, "index_version": INDEX,
            "queries": [{"cross_product_hit": True, "query_product": query, "evidence_product": evidence,
                         "noul_guard": "in_registry", "expected": "intent", "choice_options": ["intent", "None"],
                         "candidates": [{"intent_id": "intent"}]} for query, evidence in (("A", "B"), ("B", "A"))],
        })

    def link(self, provider, payload, response, *, quote=None):
        index = len(self.view["requests"])
        operation, slot = SLOTS[index]
        request_id, grant_id = f"request-{index}", f"grant-{index}"
        ref = f"receipt-{index}"
        previous = self.view["receipts"][-1] if index else {}
        self.archive[ref] = {"batch_id": BATCH, "request_id": request_id,
                             "request": payload, "response": response}
        self.view["grants"].append({
            "batch_id": BATCH, "grant_id": grant_id, "operation": operation, "slot": slot,
            "provider": provider, "account_ref": provider, "channel_ref": "typesafe-officially",
            "credential_revision": "revision", "question_version": "question-version",
            "approval_event_id": "owner-approval", "model": MODEL if operation == "model" else "",
            "source_ref": "fictional-source" if index else DOMAIN,
            "source_sha256": _digest(URL if index else DOMAIN), "payload_sha256": _digest(payload),
            "depends_on": previous.get("request_id"), "depends_on_sha256": previous.get("response_sha256"),
            "valid_from": "2026-11-26T11:55:00+00:00", "expires_at": "2026-11-26T12:05:00+00:00",
        })
        self.view["requests"].append({
            "batch_id": BATCH, "request_id": request_id, "grant_id": grant_id,
            "operation": operation, "slot": slot, "payload_sha256": _digest(payload), "state": "settled",
            "credits": 1, "input_tokens": 5, "output_tokens": 5, "total_tokens": 10, "units": 5,
        })
        self.view["receipts"].append({
            "request_id": request_id, "provider_request_id": f"provider-{index}",
            "provider": provider, "account_ref": provider, "model": MODEL if operation == "model" else "",
            "response_status": 200, "request_sha256": _digest(payload), "response_sha256": _digest(response),
            "eligible": 1, "evidence_ref": ref, "source_sha256": _digest(URL if index else DOMAIN),
            "quote_sha256": _digest(quote) if quote is not None else None, "actual_units": 1,
            "balance_status": "unsynced", **response.get("usage", {}),
        })

    def proof(self, requirement, proof):
        ref = f"{requirement}-proof"
        kind = "formal_live" if requirement == "C0-4" else "formal_offline"
        row = {"batch_id": BATCH, "requirement": requirement, "kind": kind, "evidence_ref": ref}
        artifact = proof | {"batch_id": BATCH, "requirement": requirement}
        item = self.view["evidence"]
        item[:] = [prior for prior in item if prior["requirement"] != requirement]
        item.append(row | {"evidence_sha256": _digest(artifact)})
        self.archive[ref] = artifact

    def check(self, **overrides):
        options = dict(
            currently_authorized=True, current_grant_ids={grant["grant_id"] for grant in self.view["grants"]},
            reviewed_refs={(item["evidence_ref"], item["evidence_sha256"]) for item in self.view["evidence"]},
            reviewed_model_input_sha256=_digest(REDACTED), read_archive=self.archive.__getitem__,
        )
        return evaluate_formal_batch(self.view, **(options | overrides))

    def test_independent_same_batch_evidence_can_cover_all_six(self):
        results = self.check()
        self.assertEqual(tuple(results), REQUIREMENTS)
        self.assertTrue(all(item["status"] == "PASS" and item["batch_id"] == BATCH for item in results.values()))
        self.assertEqual(results["C0-1"]["evidence_refs"], ["receipt-2", "receipt-3"])
        self.assertEqual(results["C0-5"]["kind"], "formal_offline")

    def test_fixture_and_current_owner_authority_cannot_supply_formal_status(self):
        self.assertTrue(all(item["status"] == "BLOCKED" for item in self.check(currently_authorized=False).values()))
        self.view["batch"]["mode"] = "engineering_fixture"
        self.assertTrue(all(item["status"] == "BLOCKED" for item in self.check().values()))

    def test_missing_archive_or_current_grant_does_not_pass(self):
        for options in ({"read_archive": lambda ref: None}, {"current_grant_ids": {"grant-0"}}):
            with self.subTest(options=options):
                results = self.check(**options)
                for check in ("C0-1", "C0-2", "C0-3", "C0-4"):
                    self.assertEqual(results[check]["status"], "BLOCKED")

    def test_cross_batch_archive_cannot_supply_current_source(self):
        self.archive["receipt-1"]["batch_id"] = "other-batch"
        results = self.check()
        self.assertEqual(results["C0-3"]["status"], "BLOCKED")
        self.assertEqual(results["C0-1"]["status"], "BLOCKED")

    def test_search_hit_requires_exact_canonical_approved_url(self):
        response = self.archive["receipt-0"]["response"]
        response["results"][0]["url"] = URL + "/unapproved-variant"
        digest = _digest(response)
        self.view["receipts"][0]["response_sha256"] = digest
        self.view["grants"][1]["depends_on_sha256"] = digest
        self.assertEqual(self.check()["C0-3"]["status"], "BLOCKED")

    def test_search_grant_must_bind_the_allowed_domain(self):
        self.view["grants"][0]["source_ref"] = "outside-approval"
        self.assertEqual(self.check()["C0-3"]["status"], "BLOCKED")

    def test_source_provenance_must_match_current_license_url_and_window(self):
        response = self.archive["receipt-1"]["response"]
        original = deepcopy(response["provenance"])
        for field, value in (
            ("collected_at", "2026-11-26T13:00:00+00:00"), ("collected_at", "2026-11-26T12:00:00"),
            ("final_url", URL + "?other=data"), ("final_url", URL.replace("123", "999")),
            ("license_url", "https://example.invalid/license"), ("classification", "internal"),
            ("method", "unapproved"),
        ):
            with self.subTest(field=field, value=value):
                response["provenance"] = original | {field: value}
                self.view["receipts"][1]["response_sha256"] = _digest(response)
                self.assertEqual(self.check()["C0-3"]["status"], "BLOCKED")

    def test_unapproved_model_input_blocks_model_checks(self):
        self.assertEqual(self.check(reviewed_model_input_sha256=_digest(QUOTE))["C0-1"]["status"], "BLOCKED")
        self.assertEqual(self.check(reviewed_model_input_sha256=_digest(QUOTE))["C0-3"]["status"], "PASS")

    def test_schema_gap_reports_separately_from_model_and_alignment(self):
        artifact = self.archive["receipt-3"]
        del artifact["response"]["answers"]["signal_8"]["noul"]
        self.view["receipts"][3]["response_sha256"] = _digest(artifact["response"])
        results = self.check()
        self.assertEqual(results["C0-1"]["status"], "PASS")
        self.assertEqual(results["C0-2"]["status"], "BLOCKED")
        self.assertEqual(results["C0-2"]["reason"], "schema_gap")

    def test_unknown_cost_preserves_contract_but_blocks_accounting(self):
        self.view["requests"][3]["state"] = "reconciliation"
        self.view["receipts"][3]["actual_units"] = None
        results = self.check()
        self.assertEqual(results["C0-1"]["status"], "PASS")
        self.assertEqual(results["C0-4"]["status"], "BLOCKED")

    def test_cumulative_limits_apply_to_complete_accounting(self):
        batch = self.view["batch"]
        for limit in ("request_limit", "credit_limit", "input_limit", "output_limit", "token_limit"):
            with self.subTest(limit=limit):
                batch[limit] -= 1
                self.assertEqual(self.check()["C0-4"]["status"], "BLOCKED")
                batch[limit] += 1

    def test_score_legend_gap_cannot_pass_response_contract(self):
        response = self.archive["receipt-2"]["response"]
        del response["answers"]["friction"]["legend"]
        self.view["receipts"][2]["response_sha256"] = _digest(response)
        self.view["grants"][3]["depends_on_sha256"] = _digest(response)
        results = self.check()
        self.assertEqual(results["C0-1"]["status"], "PASS")
        self.assertEqual(results["C0-2"]["reason"], "schema_gap")

    def test_ineligible_schema_gap_remains_visible_without_counting_as_evidence(self):
        receipt = self.view["receipts"][3]
        receipt.update(eligible=0, reason="schema_gap")
        results = self.check()
        self.assertEqual(results["C0-1"]["status"], "BLOCKED")
        self.assertEqual(results["C0-2"]["reason"], "schema_gap")

    def test_unreviewed_or_modified_offline_artifacts_do_not_qualify(self):
        results = self.check(reviewed_refs=())
        for check in ("C0-4", "C0-5", "C0-6"):
            self.assertEqual(results[check]["status"], "BLOCKED")
        self.archive["C0-5-proof"]["formal_cases"]["restore_replay"] = False
        self.assertEqual(self.check()["C0-5"]["status"], "BLOCKED")

    def test_local_regression_label_cannot_substitute_for_formal_evidence(self):
        for item in self.view["evidence"]:
            item["kind"] = "local_regression"
        for check in ("C0-4", "C0-5", "C0-6"):
            with self.subTest(check=check):
                self.assertEqual(self.check()[check]["status"], "BLOCKED")

    def test_recall_rejects_unfrozen_index_and_missing_none(self):
        recall = deepcopy(self.archive["C0-6-proof"])
        recall["index_version"] = "index-unverified"
        self.proof("C0-6", recall)
        self.assertEqual(self.check()["C0-6"]["status"], "BLOCKED")
        self.assertEqual(self.check(approved_recall_versions=(REGISTRY, "index-unverified"))["C0-6"]["status"], "PASS")
        recall["index_version"] = INDEX
        recall["queries"][0]["choice_options"].remove("None")
        self.proof("C0-6", recall)
        self.assertEqual(self.check()["C0-6"]["status"], "BLOCKED")

    def test_reviewed_offline_failure_differs_from_missing_proof(self):
        self.proof("C0-5", {"passed": False})
        self.assertEqual(self.check()["C0-5"]["status"], "FAIL")
        self.assertEqual(self.check(reviewed_refs=())["C0-5"]["status"], "BLOCKED")
