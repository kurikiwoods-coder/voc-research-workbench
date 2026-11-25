"""M08 URL and page-access regression with synthetic responses only."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import unittest
from unittest.mock import Mock

from src.execution.transport import Response, network
from src.ingestion.m08_retrieval import (
    MAX_BODY_BYTES, MAX_REDIRECTS, MAX_URL_LENGTH, NORMALIZATION_VERSION, UnsafeUrl,
    normalize_url, retrieve_stackexchange, validate_redirect_chain,
)
from src.ingestion.public_source import DOMAIN


ORIGIN = f"https://{DOMAIN}"
URL = f"{ORIGIN}/q/9786"
POST_URL = f"{ORIGIN}/questions/9786/synthetic-fixture"
EXCERPT = "This imagined page contains a synthetic product question."
HTML = f"<p>{EXCERPT} Here is another sentence.</p>"
FIXTURE_TIME = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)


def page(**overrides):
    item = {
        "question_id": 9786, "link": POST_URL, "body": HTML,
        "owner": {"display_name": "Synthetic author"}, "creation_date": 1_700_000_000,
        "content_license": "CC BY-SA 4.0",
    }
    return Response(200, {"items": [{**item, **overrides}]})


class URLNormalizationTests(unittest.TestCase):
    def test_identity_removes_fragment_but_preserves_query_values_and_order(self):
        result = normalize_url(
            "HTTPS://EXAMPLE.COM:443/path%20one?kind=one&kind=two&preview=&context=a%26b#heading",
            {"example.com"},
        )
        self.assertEqual(result, "https://example.com/path%20one?kind=one&kind=two&preview=&context=a%26b")
        self.assertEqual(normalize_url("http://example.com:80", {"example.com"}), "http://example.com/")

    def test_allowlist_is_exact_and_refuses_nonpublic_or_invalid_authorities(self):
        hosts = {"example.com", "localhost", "127.0.0.1", "10.1.2.3", "example.internal"}
        for raw in (
            "https://other.example.com/", "https://example.com.example.org/", "https://localhost/",
            "https://127.0.0.1/", "https://10.1.2.3/", "https://[::1]/", "https://example.internal/",
            "https://user" + "@" + "example.com/", "https://example.com:8443/", "https://example.com./",
            "file:///example.txt", "https://example.com/with space", "https://example.com/%q0",
            "https://example.com/a\\b", "https://example.com/\nnext", "https://example.com:99999/",
            "https://example.com/" + "x" * MAX_URL_LENGTH,
        ):
            with self.subTest(raw=raw[:100]):
                with self.assertRaises(UnsafeUrl):
                    normalize_url(raw, hosts)

    def test_redirects_preserve_context_and_validate_every_hop(self):
        chain = validate_redirect_chain("http://example.com/q/1", [
            "https://example.com/q/1",
            "/questions/1?valid=a&valid=b",
        ], {"example.com"})
        self.assertEqual(chain, ("https://example.com/q/1", "https://example.com/questions/1?valid=a&valid=b"))
        for locations in (
            ["https://example.net/", "/question"], ["/first", "http://example.com/q/1"],
            ["/first", "//127.0.0.1/"], ["/one", "/q/1"], ["///example.com/"],
            [f"/hop/{index}" for index in range(MAX_REDIRECTS + 1)],
        ):
            with self.subTest(locations=locations):
                with self.assertRaises(UnsafeUrl):
                    validate_redirect_chain("https://example.com/q/1", locations, {"example.com"})


class StackExchangeRetrievalTests(unittest.TestCase):
    def retrieve(self, transport, **overrides):
        options = {
            "url": URL, "allowed_domains": {DOMAIN}, "access_status": "approved",
            "transport": transport, "clock": lambda: FIXTURE_TIME,
        }
        return retrieve_stackexchange(**(options | overrides))

    def test_fixed_api_fetch_returns_page_metadata_without_excerpt_approval(self):
        transport = Mock(return_value=page())
        result = self.retrieve(transport, redirect_locations=[POST_URL])
        transport.assert_called_once_with(
            "GET", "https://api.stackexchange.com/2.3/questions/9786?site=cooking&filter=withbody", None, {},
        )
        self.assertEqual(result["status"], "accessible")
        self.assertTrue(result["accessible"])
        self.assertEqual(result["original_url"], URL)
        self.assertEqual(result["canonical_url"], URL)
        self.assertEqual(result["final_url"], POST_URL)
        self.assertEqual(result["redirect_chain"], [POST_URL])
        self.assertEqual(result["normalization_version"], NORMALIZATION_VERSION)
        self.assertEqual(result["fetched_at"], FIXTURE_TIME.isoformat())
        self.assertEqual(result["published_at"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(result["content_sha256"], sha256(HTML.encode()).hexdigest())
        self.assertEqual(result["license_reference"], "https://creativecommons.org/licenses/by-sa/4.0/")
        self.assertEqual(result["permission_status"], "pending")
        self.assertIsNone(result["quote"])
        self.assertNotIn(EXCERPT, json.dumps(result))

    def test_unknown_revoked_or_restricted_access_stops_before_transport(self):
        transport = Mock()
        for access, status in (
            ("pending", "permission_pending"), ("unknown", "permission_pending"),
            ("revoked", "permission_denied"), ("restricted", "permission_denied"),
            ("expired", "permission_denied"), ("background", "permission_denied"),
        ):
            with self.subTest(access=access):
                result = self.retrieve(transport, access_status=access, excerpt_status="approved")
                self.assertEqual(result["status"], status)
                self.assertFalse(result["accessible"])
                self.assertIsNone(result["quote"])
        transport.assert_not_called()

    def test_unapproved_route_redirect_and_real_transport_are_refused(self):
        transport = Mock()
        for url, locations in (
            (f"http://{DOMAIN}/q/9786", ()),
            (f"{URL}?answer=77", ()),
            (f"{URL}#answer-77", ()),
            (f"{ORIGIN}/questions/9786/title/77", ()),
            (URL, [f"{ORIGIN}/q/9787"]),
            (URL, [f"{POST_URL}#answer-77"]),
            (URL, ["https://example.net/questions/9786"]),
        ):
            with self.subTest(url=url, locations=locations):
                result = self.retrieve(transport, url=url, redirect_locations=locations)
                self.assertEqual(result["status"], "permission_denied")
                self.assertEqual(result["permission_status"], "denied")
                self.assertFalse(result["accessible"])
        transport.assert_not_called()
        self.assertEqual(self.retrieve(network)["reason"], "fixture_transport_required")

    def test_extraction_requires_source_license_and_independent_excerpt_approval(self):
        result = self.retrieve(Mock(return_value=page()), excerpt_status="approved")
        self.assertEqual(result["status"], "quote_extracted")
        self.assertEqual(result["quote"]["text"], EXCERPT)
        self.assertEqual(result["quote"]["author"], "Synthetic author")
        self.assertEqual(result["quote"]["license"], "CC BY-SA 4.0")
        self.assertTrue(result["quote"]["synthetic"])
        self.assertEqual(result["quote"]["research_denominator"], 0)
        unknown = self.retrieve(Mock(return_value=page(content_license="unknown")), excerpt_status="approved")
        self.assertEqual(unknown["status"], "permission_pending")
        self.assertTrue(unknown["accessible"])
        self.assertIsNone(unknown["quote"])
        self.assertIsNone(unknown["license_reference"])
        revoked = self.retrieve(Mock(return_value=page()), excerpt_status="revoked")
        self.assertEqual(revoked["status"], "permission_denied")
        self.assertEqual(revoked["permission_status"], "revoked")
        self.assertTrue(revoked["accessible"])
        self.assertIsNone(revoked["quote"])

    def test_empty_page_or_missing_attribution_does_not_yield_excerpt(self):
        for overrides in ({"body": "<p></p>"}, {"owner": {}}, {"creation_date": None}):
            with self.subTest(overrides=overrides):
                result = self.retrieve(Mock(return_value=page(**overrides)), excerpt_status="approved")
                self.assertEqual(result["status"], "extraction_failed")
                self.assertTrue(result["accessible"])
                self.assertIsNone(result["quote"])

    def test_pre_epoch_date_is_preserved_for_historical_synthetic_scope(self):
        result = self.retrieve(Mock(return_value=page(creation_date=-86_400)))
        self.assertEqual(result["status"], "accessible")
        self.assertEqual(result["published_at"], "1969-12-31T00:00:00+00:00")

    def test_script_and_style_are_excluded_from_licensed_excerpts(self):
        non_content = "<script>Invisible script text.</script><style>Invisible style text.</style>"
        with_text = non_content + HTML
        result = self.retrieve(Mock(return_value=page(body=with_text)), excerpt_status="approved")
        self.assertEqual(result["status"], "quote_extracted")
        self.assertEqual(result["quote"]["text"], EXCERPT)
        self.assertEqual(result["content_sha256"], sha256(with_text.encode()).hexdigest())
        empty = self.retrieve(Mock(return_value=page(body=non_content)), excerpt_status="approved")
        self.assertEqual(empty["status"], "extraction_failed")
        self.assertTrue(empty["accessible"])
        self.assertIsNone(empty["quote"])

    def test_unverified_source_identity_or_oversize_response_is_inaccessible(self):
        for reply in (
            page(question_id=9787), page(question_id="9786"), page(link=f"{ORIGIN}/q/9787"),
            page(link=f"{POST_URL}#answer-77"),
            page(link="https://example.com/q/9786"), page(body="语" * (MAX_BODY_BYTES // 3 + 1)),
            Response(200, {"items": []}), Response(200, {"items": [None]}),
        ):
            with self.subTest(reply=reply.status):
                result = self.retrieve(Mock(return_value=reply), excerpt_status="approved")
                self.assertEqual(result["status"], "inaccessible")
                self.assertFalse(result["accessible"])
                self.assertIsNone(result["quote"])

    def test_errors_timeout_and_redirect_never_expose_provider_response_or_retry(self):
        for status, reason in (
            (None, "offline"), (302, "redirect_refused"), (401, "invalid_key"),
            (403, "permission_denied"), (429, "rate_limited"), (503, "upstream_error"),
        ):
            with self.subTest(status=status):
                transport = Mock(return_value=Response(status, {"error_message": "Untrusted fixture detail"}))
                result = self.retrieve(transport)
                self.assertEqual(result["status"], "inaccessible")
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("Untrusted fixture detail", json.dumps(result))
                transport.assert_called_once()
        transport = Mock(side_effect=TimeoutError("Untrusted fixture detail"))
        result = self.retrieve(transport)
        self.assertEqual(result["status"], "inaccessible")
        self.assertEqual(result["reason"], "offline")
        self.assertNotIn("Untrusted fixture detail", json.dumps(result))
        transport.assert_called_once()
