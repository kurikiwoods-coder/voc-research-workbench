"""Permanent offline coverage for the M08 provider contracts."""

import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

from src.config import Settings
from src.execution.transport import Denied, Response, network
from src.ingestion.m08_search import preview_queries, search


URL = "https://cooking.stackexchange.com/questions/100/fixture"
STAMP = "2026-11-25T12:00:00+00:00"
QUERY = {"keywords": ["kettle"], "include_terms": ["pour test"], "exclude_terms": ["sponsored"],
         "allowed_domains": ["cooking.stackexchange.com"], "language": "en", "country": "US",
         "date_from": "2025-01-01", "date_to": "2026-01-01"}


def tavily(*hits):
    return Response(200, {"results": list(hits), "usage": {"credits": 1}})


def brave(*hits):
    return Response(200, {"type": "search", "web": {"results": list(hits)}}, monthly_remaining=37, monthly_limit=50)


class M08SearchTests(unittest.TestCase):
    def setUp(self):
        self.credentials = {"tavily": "fixture-tavily-credential", "brave": "fixture-brave-credential"}
        self.settings = Settings(Path("."), keys=self.credentials)
        self.calls = []

    def run_search(self, replies, *, query=QUERY, mode="merge", providers=("tavily", "brave"), **kwargs):
        replies = iter(replies)

        def fixture(method, url, body, headers):
            self.calls.append((method, url, body, headers))
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return reply

        return search(self.settings, query, mode=mode, providers=providers, labels={"public_approved"},
                      limit=kwargs.pop("limit", 5), transport=fixture, clock=lambda: STAMP, **kwargs)

    def test_bind_credentials_and_filters_to_fixed_endpoints(self):
        result = self.run_search((tavily(), brave()), limit=25)
        method, url, body, headers = self.calls[0]
        self.assertEqual((method, url), ("POST", "https://api.tavily.com/search"))
        self.assertEqual(headers, {"Authorization": f"Bearer {self.credentials['tavily']}",
                                   "Content-Type": "application/json"})
        self.assertEqual(body["query"], 'kettle "pour test"')
        for field, expected in {
            "exact_match": True, "include_usage": True, "max_results": 20, "search_depth": "basic",
            "include_domains": ["cooking.stackexchange.com"], "include_domains_mode": "restrict", "language": "en",
            "filter_by_language": True, "country": "united states", "start_date": "2025-01-01",
            "end_date": "2026-01-01", "filter_by_published_date": True,
            "include_answer": False, "include_raw_content": False, "auto_parameters": False,
        }.items():
            self.assertEqual(body[field], expected)
        method, url, body, headers = self.calls[1]
        parsed = urlsplit(url)
        self.assertEqual((method, parsed.scheme, parsed.netloc, parsed.path, body),
                         ("GET", "https", "api.search.brave.com", "/res/v1/web/search", None))
        self.assertEqual(headers, {"X-Subscription-Token": self.credentials["brave"]})
        params = parse_qs(parsed.query)
        for field, expected in {
            "q": '"kettle" "pour test" -"sponsored" site:cooking.stackexchange.com',
            "country": "US", "search_lang": "en", "count": "20", "result_filter": "web",
            "freshness": "2025-01-01to2026-01-01", "operators_fallback": "false",
        }.items():
            self.assertEqual(params[field], [expected])
        first, second = result["attempts"]
        self.assertEqual(first["unsupported_filters"], ["exclude_terms"])
        self.assertEqual(first["filter_notes"]["country"], "ranking_boost_only")
        self.assertEqual(first["filter_notes"]["limit"], "provider_maximum_20")
        self.assertEqual(second["unsupported_filters"], [])
        self.assertNotIn("credential", json.dumps(result))

    def test_merge_keeps_both_receipts_and_excludes_provider_snippets(self):
        first = {"url": URL, "title": "A &amp; B", "content": "Tavily snippet"}
        second = {"url": URL, "title": "B", "description": "Brave snippet", "extra_snippets": ["another snippet"]}
        result = self.run_search((tavily(None, first), brave(second)))
        self.assertEqual([(hit["provider"], hit["rank"], hit["url"], hit["discovered_at"]) for hit in result["hits"]],
                         [("tavily", 2, URL, STAMP), ("brave", 1, URL, STAMP)])
        self.assertEqual(result["hits"][0]["title"], "A & B")
        serialized = json.dumps(result)
        for snippet in ("Tavily snippet", "Brave snippet", "another snippet"):
            self.assertNotIn(snippet, serialized)
        tavily_usage, brave_usage = (attempt["usage"] for attempt in result["attempts"])
        self.assertEqual((tavily_usage["unit"], tavily_usage["reported_usage"], tavily_usage["estimated_cost"],
                          tavily_usage["remaining"]), ("credit", 1, "0.008", None))
        self.assertEqual((brave_usage["unit"], brave_usage["reported_usage"], brave_usage["estimated_cost"],
                          brave_usage["remaining"], brave_usage["quota_limit"]), ("request", None, "0.005", 37, 50))
        for usage in (tavily_usage, brave_usage):
            self.assertEqual((usage["actual_requests"], usage["simulated_requests"], usage["actual_cost"]), (0, 1, None))

    def test_independent_brave_records_unsupported_locale_and_open_date(self):
        query = {**QUERY, "country": "ZZ", "date_to": None, "language": "zz"}
        result = self.run_search((Response(200, {"type": "search"}),), query=query, mode="independent", providers=("brave",))
        attempt = result["attempts"][0]
        self.assertEqual(attempt["unsupported_filters"], ["country", "language", "date_from"])
        self.assertEqual((attempt["result_count"], attempt["error"], result["hits"]), (0, None, []))
        self.assertEqual(len(self.calls), 1)

    def test_brave_supports_documented_language_codes_and_explicit_chinese_aliases(self):
        for language, expected in (("en-GB", "en-gb"), ("ja", "ja"), ("nl", "nl"), ("zh", "zh-hans"), ("zh-TW", "zh-hant")):
            with self.subTest(language=language):
                plan, = preview_queries({**QUERY, "language": language}, providers=("brave",), limit=5)
                self.assertEqual(plan["request"]["parameters"]["search_lang"], expected)
                self.assertEqual(plan["unsupported_filters"], [])

    def test_fallback_handles_provider_failures_and_keeps_primary_receipt(self):
        for response, expected in (
            (Response(429, {"error": "raw message"}, retry_after="3"), "rate_limited"),
            (Response(432, {}), "quota_exhausted"), (Response(433, {}), "quota_exhausted"),
            (Response(434, {}), "upstream_error"), (Response(503, {}), "upstream_error"),
            (TimeoutError("raw timeout"), "offline"), (Response(200, {"results": {}}), "invalid_schema"),
        ):
            with self.subTest(expected=expected):
                self.calls.clear()
                result = self.run_search((response, brave({"url": URL})), mode="fallback")
                self.assertEqual([attempt["error"] for attempt in result["attempts"]], [expected, None])
                self.assertEqual(len(self.calls), 2)
                self.assertEqual([hit["provider"] for hit in result["hits"]], ["brave"])
                self.assertNotIn("raw message", json.dumps(result))
                self.assertNotIn("raw timeout", json.dumps(result))

    def test_fallback_stops_on_auth_configuration_or_valid_empty(self):
        for response, expected in ((Response(401, {}), "invalid_key"), (Response(403, {}), "permission_denied"),
                                   (Response(400, {}), "invalid_request"), (Response(422, {}), "invalid_request"),
                                   (tavily(), None)):
            with self.subTest(expected=expected):
                self.calls.clear()
                result = self.run_search((response,), mode="fallback")
                self.assertEqual([attempt["error"] for attempt in result["attempts"]], [expected])
                self.assertEqual(len(self.calls), 1)
        self.credentials["tavily"] = ""
        result = self.run_search((), mode="fallback")
        self.assertEqual([attempt["error"] for attempt in result["attempts"]], ["missing_key"])
        self.assertEqual(result["attempts"][0]["usage"]["simulated_requests"], 0)

    def test_brave_quota_limit_is_distinct_from_rate_limit(self):
        result = self.run_search(
            (Response(429, {"error": {"code": "QUOTA_LIMITED"}}, monthly_remaining=0, monthly_limit=50), tavily()),
            mode="fallback", providers=("brave", "tavily"),
        )
        self.assertEqual([attempt["error"] for attempt in result["attempts"]], ["quota_exhausted", None])
        self.assertEqual(result["attempts"][0]["usage"]["remaining"], 0)

    def test_filter_preserves_raw_receipts_without_switching_provider(self):
        result = self.run_search((tavily({"url": URL}),), mode="fallback", eligible=lambda hit: False)
        self.assertEqual(result["hits"], [])
        self.assertEqual([hit["url"] for hit in result["attempts"][0]["hits"]], [URL])
        self.assertEqual(len(self.calls), 1)

    def test_provider_errors_and_unexpected_fields_do_not_expose_credentials(self):
        result = self.run_search((tavily({"url": URL + "?token=" + self.credentials["brave"]},
                                          {"url": URL, "title": self.credentials["tavily"]}),
                                  Response(403, {"error": self.credentials["brave"]})))
        self.assertEqual(result["hits"][0]["title"], "[REDACTED]")
        self.assertEqual(result["hits"][0]["url"], URL)
        self.assertNotIn("credential", json.dumps(result))

    def test_live_transport_unapproved_labels_and_keys_in_queries_are_blocked(self):
        options = {"mode": "independent", "providers": ("tavily",), "limit": 5}

        def unexpected(*args):
            self.fail("no request authorized")

        with self.assertRaises(Denied):
            search(self.settings, QUERY, labels={"public_approved"}, transport=network, **options)
        with self.assertRaises(Denied):
            search(self.settings, QUERY, labels={"internal_cx"}, transport=unexpected, **options)
        with self.assertRaises(Denied):
            search(self.settings, {**QUERY, "keywords": [self.credentials["brave"]]},
                   labels={"public_approved"}, transport=unexpected, **options)

    def test_provider_query_limits_fail_without_sending(self):
        query = {**QUERY, "keywords": ["x" * 601]}
        result = self.run_search((), query=query)
        self.assertEqual([attempt["error"] for attempt in result["attempts"]], ["query_too_long", "query_too_long"])
        self.assertEqual(self.calls, [])

    def test_preview_uses_the_same_credential_free_request_plan(self):
        plans = preview_queries(QUERY, providers=("tavily", "brave"), limit=5)
        self.assertEqual(self.calls, [])
        result = self.run_search((tavily(), brave()))
        for plan, attempt in zip(plans, result["attempts"]):
            self.assertEqual(plan, {key: attempt[key] for key in plan})
