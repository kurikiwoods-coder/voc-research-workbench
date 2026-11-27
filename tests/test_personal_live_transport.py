from dataclasses import replace
import gzip
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler

from src.config import MODEL
from src.execution.personal_admission import digest, model_payloads, search_payload
from src.execution.personal_live_transport import (
    MAX_RESPONSE_BYTES, LiveTransportError, PersonalLiveTransport, PreparedLiveRequest, SystemOnePolicy,
)
from src.execution.transport import NoRedirect
from src.raw_store.personal_validation import Budget
from src.raw_store.store import dump


SEARCH_BUDGET = Budget(1, 1, 0, 0, 0, 0)
SOURCE_BUDGET = Budget(1, 0, 0, 0, 0, 0)
MODEL_BUDGET = Budget(1, 0, 500, 200, 700, 100)
SOURCE_PAYLOAD = {
    "url": "https://cooking.stackexchange.com/questions/123",
    "site": "cooking",
    "filter": "withbody",
}
SECRET = "synthetic-live-credential"
BUILD_OPENER = "src.execution.personal_live_transport.build_opener"


class Reply(BytesIO):
    def __init__(self, data, *, headers=None, status=200):
        super().__init__(data)
        self.headers = headers or {}
        self.status = status


class PersonalLiveTransportTests(unittest.TestCase):
    def setUp(self):
        self.transport = PersonalLiveTransport()
        self.search = search_payload({
            "keywords": ["fictional", "public sample"],
            "allowed_domains": ["cooking.stackexchange.com"],
        })
        self.shards = model_payloads("合成样本 Synthetic test quote.", {
            f"intent-{index}": f"Fictional choice {index}" for index in range(11, 0, -1)
        })

    def test_search_sends_only_pinned_basic_post(self):
        prepared = self.transport.prepare("search", self.search, slot=1, budget=SEARCH_BUDGET)
        response = {"request_id": "fixture-search-id", "usage": {"credits": 1}, "echo": SECRET}
        with patch(BUILD_OPENER) as build:
            open_request = build.return_value.open
            open_request.return_value = Reply(json.dumps(response).encode())
            result = self.transport.send(prepared, secret=SECRET)
            request = open_request.call_args.args[0]
            self.assertEqual(open_request.call_count, 1)
            self.assertEqual(open_request.call_args.kwargs, {"timeout": 12})
            proxy, redirect = build.call_args.args
            self.assertIsInstance(proxy, ProxyHandler)
            self.assertEqual(proxy.proxies, {})
            self.assertIsInstance(redirect, NoRedirect)
        self.assertEqual(request.full_url, "https://api.tavily.com/search")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + SECRET)
        self.assertEqual(json.loads(request.data), self.search)
        self.assertEqual(result.provider_request_id, "fixture-search-id")
        self.assertEqual(result.response.body["echo"], "[REDACTED]")

    def test_unapproved_search_parameters_and_budgets_are_rejected(self):
        synthetic_email = "@".join(("fixture-user", "example.test"))
        for change in (
            {"search_depth": "advanced"},
            {"auto_parameters": True},
            {"max_results": True},
            {"include_raw_content": True},
            {"include_domains": ["unapproved.example"]},
            {"include_domains_mode": "prefer"},
            {"unknown": True},
            {"query": synthetic_email},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(LiveTransportError, "PAYLOAD_INVALID"):
                self.transport.prepare("search", {**self.search, **change}, slot=1, budget=SEARCH_BUDGET)
        with self.assertRaisesRegex(LiveTransportError, "LIMIT_INVALID"):
            self.transport.prepare("search", self.search, slot=1, budget=Budget(1, 0, 0, 0, 0, 0))

    def test_source_sends_anonymous_fixed_endpoint_and_preserves_gzip_response(self):
        prepared = self.transport.prepare("source", SOURCE_PAYLOAD, slot=1, budget=SOURCE_BUDGET)
        response = {"items": [{"question_id": 123, "body": "Original sample text."}]}
        with patch(BUILD_OPENER) as build:
            build.return_value.open.return_value = Reply(gzip.compress(json.dumps(response).encode()))
            result = self.transport.send(prepared, secret=None)
            request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.stackexchange.com/2.3/questions/123?site=cooking&filter=withbody")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.data)
        self.assertEqual(result.response.body, response)

    def test_source_requires_exact_canonical_url_and_anonymous_binding(self):
        for url in (
            "http://cooking.stackexchange.com/questions/123",
            "https://example.test/questions/123",
            "https://cooking.stackexchange.com/questions/123#section",
            "https://cooking.stackexchange.com/questions/123?extra=1",
            "https://cooking.stackexchange.com/questions/123/slug",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(LiveTransportError, "PAYLOAD_INVALID"):
                self.transport.prepare("source", {**SOURCE_PAYLOAD, "url": url}, slot=1, budget=SOURCE_BUDGET)
        prepared = self.transport.prepare("source", SOURCE_PAYLOAD, slot=1, budget=SOURCE_BUDGET)
        with patch(BUILD_OPENER) as build, self.assertRaisesRegex(LiveTransportError, "ANONYMOUS_REQUIRED"):
            self.transport.send(prepared, secret=SECRET)
        build.assert_not_called()

    def test_both_model_shards_reject_unverified_upstream_hard_token_ceiling(self):
        for slot, payload in enumerate(self.shards, 1):
            with self.subTest(slot=slot), patch(BUILD_OPENER) as build:
                with self.assertRaisesRegex(LiveTransportError, "LIVE_MODEL_HARD_BUDGET_UNVERIFIED"):
                    self.transport.prepare("model", payload, slot=slot, budget=MODEL_BUDGET)
                prepared = PreparedLiveRequest("model", slot, MODEL_BUDGET, dump(payload))
                with self.assertRaisesRegex(LiveTransportError, "LIVE_MODEL_HARD_BUDGET_UNVERIFIED"):
                    self.transport.send(prepared, secret=SECRET)
                build.assert_not_called()

    def test_approved_model_shards_send_only_the_fixed_system_one_contract(self):
        for slot, payload in enumerate(self.shards, 1):
            with self.subTest(slot=slot), patch(BUILD_OPENER) as build:
                policy = SystemOnePolicy("packycode", digest(payload))
                prepared = self.transport.prepare("model", payload, slot=slot, budget=MODEL_BUDGET, model_policy=policy)
                response = {"model": MODEL, "usage": {"input_tokens": 124, "output_tokens": 75}, "echo": SECRET}
                open_request = build.return_value.open
                open_request.return_value = Reply(gzip.compress(dump(response).encode("utf-8")), headers={
                    "Content-Encoding": "gzip", "X-Request-Id": f"fixture-model-{slot}",
                })
                result = self.transport.send(prepared, secret=SECRET, model_policy=policy)
                request = open_request.call_args.args[0]
                open_request.assert_called_once_with(request, timeout=12)
                proxy, redirect = build.call_args.args
                self.assertEqual(proxy.proxies, {})
                self.assertIsInstance(redirect, NoRedirect)
                self.assertEqual(request.full_url, "https://cf.api.fan/v1/systemone")
                self.assertEqual(request.get_method(), "POST")
                self.assertEqual(request.get_header("Authorization"), "Bearer " + SECRET)
                self.assertEqual(request.get_header("Content-type"), "application/json")
                self.assertIsNone(request.get_header("Typesafe-danger-zone-long-context"))
                self.assertEqual(request.data, dump(payload).encode("utf-8"))
                self.assertEqual(result.provider_request_id, f"fixture-model-{slot}")
                self.assertEqual(result.response.body, {**response, "echo": "[REDACTED]"})

    def test_model_requires_explicit_matching_policy_and_frozen_payload(self):
        payload = self.shards[0]
        policy = SystemOnePolicy("packycode", digest(payload))
        prepared = self.transport.prepare("model", payload, slot=1, budget=MODEL_BUDGET, model_policy=policy)
        with patch(BUILD_OPENER) as build:
            for request, supplied in (
                (prepared, None), (prepared, SystemOnePolicy("typesafe", policy.payload_sha256)),
                (replace(prepared, payload_json=dump({**payload, "state": "A changed offline fixture."})), policy),
                (replace(prepared, model_policy=None), policy),
            ):
                with self.subTest(request=request, supplied=supplied), self.assertRaisesRegex(
                    LiveTransportError, "LIVE_MODEL_POLICY_MISMATCH",
                ):
                    self.transport.send(request, secret=SECRET, model_policy=supplied)
            build.assert_not_called()

    def test_model_shape_and_budget_are_checked_even_with_matching_policy(self):
        payload = self.shards[0]
        for invalid in (
            {**payload, "model": "jev-1.14.1"}, {**payload, "max_output_tokens": 200},
            {**payload, "state": "x" * 33_000}, {**payload, "questions": self.shards[1]["questions"]},
            {**payload, "questions": {**payload["questions"], "signal_1": {"type": "noul", "instructions": "altered"}}},
        ):
            with self.assertRaisesRegex(LiveTransportError, "LIVE_MODEL_PAYLOAD_INVALID"):
                self.transport.prepare("model", invalid, slot=1, budget=MODEL_BUDGET,
                                       model_policy=SystemOnePolicy("packycode", digest(invalid)))
        for budget in (Budget(1, 1, 500, 200, 700, 100), Budget(1, 0, 500, 200, 450, 100)):
            with self.subTest(budget=budget), self.assertRaisesRegex(LiveTransportError, "LIVE_MODEL_LIMIT_INVALID"):
                self.transport.prepare("model", payload, slot=1, budget=budget,
                                       model_policy=SystemOnePolicy("packycode", digest(payload)))

    def test_model_timeout_and_bounded_utf8_reply_never_retries(self):
        payload = self.shards[1]
        policy = SystemOnePolicy("packycode", digest(payload))
        prepared = self.transport.prepare("model", payload, slot=2, budget=MODEL_BUDGET, model_policy=policy)
        for reply, reason in (
            (TimeoutError(), "connection_interrupted"),
            (Reply(b" " * (MAX_RESPONSE_BYTES + 1)), "response_too_large"),
            (Reply(gzip.compress(b" " * (MAX_RESPONSE_BYTES + 1))), "response_too_large"),
            (Reply("{}".encode("utf-16")), "non_json_response"),
            (Reply(b'{"model":"jev-1.14.0","model":"jev-1.14.0"}'), "non_json_response"),
        ):
            with self.subTest(reason=reason), patch(BUILD_OPENER) as build:
                open_request = build.return_value.open
                if isinstance(reply, Exception):
                    open_request.side_effect = reply
                else:
                    open_request.return_value = reply
                result = self.transport.send(prepared, secret=SECRET, model_policy=policy)
                self.assertEqual(result.response.body, {"error": reason})
                open_request.assert_called_once()

    def test_redirect_or_unknown_connection_result_never_triggers_retry(self):
        prepared = self.transport.prepare("search", self.search, slot=1, budget=SEARCH_BUDGET)
        redirect = HTTPError(
            "https://api.tavily.com/search", 302, "redirect",
            {"Location": "https://example.test"}, Reply(b"{}"),
        )
        for failure, status in ((redirect, 302), (URLError("offline"), None)):
            with self.subTest(status=status), patch(BUILD_OPENER) as build:
                open_request = build.return_value.open
                open_request.side_effect = failure
                self.assertEqual(self.transport.send(prepared, secret=SECRET).response.status, status)
                open_request.assert_called_once()

    def test_duplicate_json_and_oversized_gzip_cannot_form_evidence(self):
        prepared = self.transport.prepare("source", SOURCE_PAYLOAD, slot=1, budget=SOURCE_BUDGET)
        with patch(BUILD_OPENER) as build:
            build.return_value.open.side_effect = [
                Reply(b'{"a":1,"a":2}'),
                Reply(gzip.compress(b" " * 2_000_001)),
            ]
            self.assertEqual(self.transport.send(prepared, secret=None).response.body["error"], "non_json_response")
            self.assertEqual(self.transport.send(prepared, secret=None).response.body["error"], "response_too_large")


if __name__ == "__main__":
    unittest.main()
