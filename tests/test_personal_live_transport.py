import gzip
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler

from src.execution.personal_admission import search_payload
from src.execution.personal_live_transport import (
    LiveTransportError, PersonalLiveTransport, PreparedLiveRequest,
)
from src.execution.transport import NoRedirect
from src.raw_store.personal_validation import Budget


SEARCH_BUDGET = Budget(1, 1, 0, 0, 0, 0)
SOURCE_BUDGET = Budget(1, 0, 0, 0, 0, 0)
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
        budget = Budget(1, 0, 500, 200, 700, 100)
        for slot in (1, 2):
            with self.subTest(slot=slot), patch(BUILD_OPENER) as build:
                with self.assertRaisesRegex(LiveTransportError, "LIVE_MODEL_HARD_BUDGET_UNVERIFIED"):
                    self.transport.prepare("model", {}, slot=slot, budget=budget)
                prepared = PreparedLiveRequest("model", slot, budget, "{}")
                with self.assertRaisesRegex(LiveTransportError, "LIVE_MODEL_HARD_BUDGET_UNVERIFIED"):
                    self.transport.send(prepared, secret=SECRET)
                build.assert_not_called()

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
