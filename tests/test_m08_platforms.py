"""M08-C platform policy and Unicode evidence regressions with offline fixtures."""

from hashlib import sha256
import unittest

from src.ingestion.m08_platforms import (
    EXTRACTION_VERSION, FIXTURE_LICENSE, MAX_BODY_BYTES, REDDIT, STACK, YOUTUBE,
    FixtureReply, exact_segments, platform_catalog, project_fixture, retrieve_fixture,
)
from src.ingestion.public_source import DOMAIN


STAMP = "2026-11-23T11:12:13+00:00"
VIDEO = "m0800010001"
ALL = dict.fromkeys(("discover", "access", "store", "research", "transmit"), "approved")


def forum_question(**overrides):
    return {
        "question_id": 9786, "link": f"https://{DOMAIN}/q/9786", "title": "Fixture question",
        "body": "<p>我要在😀之后<br>继续e\u0301。<span hidden>hidden</span></p>",
        "owner": {"display_name": "Synthetic &amp; approved", "profile_image": "private fixture attribute"},
        "creation_date": 1_700_000_000, "last_edit_date": 1_700_000_100, "content_license": "CC BY-SA 4.0",
    } | overrides


def video_comment(**overrides):
    return {"snippet": {"videoId": VIDEO, "topLevelComment": {
        "id": "fixture-comment", "snippet": {
            "authorDisplayName": "Synthetic author", "publishedAt": STAMP,
            "textOriginal": "第一句😀。\nSecond e\u0301 line.", "textDisplay": "Displayed text",
        } | overrides,
    }}}


class PlatformFixtureTests(unittest.TestCase):
    def project(self, source, kind, item, **overrides):
        options = {
            "reply": FixtureReply(200, item), "object_id": "9786", "permissions": ALL,
            "fetched_at": STAMP, "attribution_approved": True, "content_role": "user_quote",
        }
        return project_fixture(source, kind, **(options | overrides))

    def youtube_comment(self, item, **overrides):
        return self.project(YOUTUBE, "comment", item, **({"object_id": "fixture-comment", "parent_id": VIDEO}
                                                         | overrides))

    def test_forum_objects_have_separate_identity_and_grants(self):
        question = self.project(STACK, "question", forum_question())
        self.assertEqual(question["status"], "segments_extracted")
        self.assertEqual(question["title"], "Fixture question")
        self.assertEqual(question["attribution"], "Synthetic & approved")
        self.assertEqual(question["modified_at"], "2023-11-14T22:15:00+00:00")
        self.assertNotIn("profile_image", question)
        answer = forum_question(answer_id=8543, link=f"https://{DOMAIN}/questions/9786/thread/8543#8543")
        denied = self.project(STACK, "answer", answer, object_id="8543", parent_id="9786",
                              permissions=ALL | {"store": "unknown"})
        self.assertEqual(denied["status"], "storage_blocked")
        self.assertTrue(denied["accessible"])
        self.assertIsNone(denied["body"])
        self.assertNotIn("attribution", denied)
        approved = self.project(STACK, "answer", answer, object_id="8543", parent_id="9786")
        self.assertEqual(approved["status"], "segments_extracted")
        self.assertEqual(approved["canonical_url"], question["canonical_url"])
        self.assertEqual(approved["source_locator"], f"https://{DOMAIN}/a/8543")
        comment = forum_question(comment_id=3421, post_id=8543, post_type="answer", content_license=None,
                                 link=f"https://{DOMAIN}/questions/9786/thread/8543#comment3421_8543")
        denied = self.project(STACK, "comment", comment, object_id="3421", parent_id="8543")
        self.assertEqual(denied["status"], "storage_blocked")
        approved = self.project(STACK, "comment", comment | {"content_license": "CC BY-SA 3.0"},
                                object_id="3421", parent_id="8543")
        self.assertEqual(approved["status"], "segments_extracted")
        self.assertIsNone(approved["modified_at"])
        self.assertEqual(approved["license_reference"], "https://creativecommons.org/licenses/by-sa/3.0/")
        self.assertEqual(approved["source_locator"], f"https://{DOMAIN}/a/8543#comment3421_8543")

    def test_access_research_and_attribution_are_independent(self):
        pending = self.project(STACK, "question", forum_question(), permissions=ALL | {"access": "revoked"})
        self.assertEqual(pending["status"], "permission_blocked")
        self.assertFalse(pending["accessible"])
        stored = self.project(STACK, "question", forum_question(), permissions=ALL | {"research": "restricted"})
        self.assertEqual(stored["status"], "body_verified")
        self.assertEqual(stored["extraction_reason"], "research_permission")
        self.assertTrue(stored["body"])
        self.assertEqual(stored["segments"], [])
        restricted = self.project(STACK, "question", forum_question(), attribution_approved=False)
        self.assertEqual(restricted["status"], "storage_blocked")
        self.assertIsNone(restricted["body"])
        missing = self.project(STACK, "question", forum_question(owner={}))
        self.assertEqual(missing["status"], "unverified_attribution_or_timestamp")
        self.assertIsNone(missing["body"])
        allowed = self.project(STACK, "question", forum_question(), permissions=ALL | {"transmit": "unknown"})
        self.assertEqual(allowed["status"], "segments_extracted")

    def test_contextual_roles_and_search_summaries_cannot_make_segments(self):
        for role in ("background", "product_or_merchant", "internal", "synthetic", None):
            with self.subTest(role=role):
                result = self.project(STACK, "question", forum_question(), content_role=role)
                self.assertEqual(result["status"], "body_verified")
                self.assertEqual(result["segments"], [])
        video = {"id": VIDEO, "snippet": {"title": "Fixture video", "description": "Merchant description",
                 "publishedAt": STAMP, "channelTitle": "Synthetic channel"}}
        metadata = self.project(YOUTUBE, "metadata", video, object_id=VIDEO)
        self.assertEqual(metadata["status"], "metadata_verified")
        self.assertIsNone(metadata["body"])
        description = self.project(YOUTUBE, "description", video, object_id=VIDEO)
        self.assertEqual(description["content_role"], "product_or_merchant")
        self.assertEqual(description["body"], "Merchant description")
        self.assertEqual(description["segments"], [])
        search = video | {"id": {"kind": "youtube#video", "videoId": VIDEO}}
        search_result = self.project(YOUTUBE, "search", search, object_id=VIDEO, permissions={"discover": "approved"})
        self.assertEqual(search_result["status"], "discovered")
        self.assertNotIn("Merchant description", str(search_result))
        self.assertIsNone(search_result["raw_sha256"])
        self.assertEqual(search_result["segments"], [])

    def test_youtube_original_needs_authorized_representation(self):
        available = self.youtube_comment(video_comment())
        self.assertEqual(available["status"], "segments_extracted")
        self.assertEqual(available["license_reference"], FIXTURE_LICENSE)
        self.assertNotIn("Displayed text", available["body"])
        unavailable = self.youtube_comment(video_comment(textOriginal=None))
        self.assertEqual(unavailable["status"], "original_unavailable")
        self.assertIsNone(unavailable["body"])
        self.assertEqual(unavailable["segments"], [])
        wrong_fields = self.youtube_comment(video_comment(videoId="m0800010002"))
        self.assertEqual(wrong_fields["status"], "unverified_object")
        for kind, expected in (("reply", "deferred"), ("caption_track", "authorization_required"),
                               ("caption_text", "owner_authorization_required")):
            with self.subTest(kind=kind):
                result = self.project(YOUTUBE, kind, video_comment(), object_id=VIDEO)
                self.assertEqual(result["status"], expected)
                self.assertIsNone(result["body"])

    def test_fixed_url_size_media_and_failure_boundaries(self):
        for link in (
            "https://127.0.0.1/q/9786", f"http://{DOMAIN}/q/9786", f"https://{DOMAIN}/q/9787",
            f"https://{DOMAIN}/q/9786#other-object", f"https://{DOMAIN}/unregistered/9786",
            f"https://{DOMAIN}.example.com/q/9786", f"https://{DOMAIN}/q/9786?redirect=true",
        ):
            with self.subTest(link=link):
                result = self.project(STACK, "question", forum_question(link=link))
                self.assertEqual(result["status"], "unverified_object")
                self.assertIsNone(result["body"])
        for reply, status in (
            (FixtureReply(404), "source_unavailable"), (FixtureReply(303), "redirect_refused"),
            (FixtureReply(None), "source_unavailable"), (FixtureReply(429), "quota_blocked"),
            (FixtureReply(403, error="commentsDisabled"), "comments_disabled"),
            (FixtureReply(403, error="quotaExceeded"), "quota_blocked"),
            (FixtureReply(200, forum_question(), media_type="text/html"), "unverified_response"),
            (FixtureReply(200, forum_question(body="😀" * (MAX_BODY_BYTES // 4 + 1))), "invalid_body"),
            (FixtureReply(200, forum_question(body="\ud800")), "invalid_body"),
        ):
            with self.subTest(status=status):
                result = self.project(STACK, "question", None, reply=reply)
                self.assertEqual(result["status"], status)
                self.assertIsNone(result["body"])
                self.assertEqual(result["segments"], [])

    def test_unicode_intervals_and_hashes_match_stored_text(self):
        chunks = ("<script>disallowed</script><div hidden>discard <div><script>inner</script>unused</div></div>",
                  "<p>试😀<b>用</b>&amp;继续e\u0301。<span style='display: none;'>inactive</span></p>",
                  "<p><span aria-hidden='true'>unseen</span>Now finish.</p>")
        raw = "".join(chunks)
        result = self.project(STACK, "question", forum_question(body=raw))
        body = "试😀用&继续e\u0301。\nNow finish."
        self.assertEqual(result["body"], body)
        self.assertEqual(result["raw_sha256"], sha256(body.encode("utf-8")).hexdigest())
        self.assertEqual(result["response_body_sha256"], sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(result["segments"][1]["start"], 10)
        for segment in result["segments"]:
            self.assertEqual(body[segment["start"]:segment["end"]], segment["text"])
            self.assertEqual(segment["extraction_version"], EXTRACTION_VERSION)
        self.assertEqual(exact_segments(" \t\r\n"), [])
        self.assertEqual(self.project(STACK, "question", forum_question(body=chunks[0]))["status"], "empty_body")

    def test_reddit_structural_fixture_cannot_grant_access(self):
        def listing(kind):
            return {"kind": "Listing", "data": {"children": [{"kind": kind, "data": {"body": "private fixture"}}]}}

        for operation, item in (
            ("search", listing("t3")), ("metadata", listing("t3")),
            ("post", [listing("t3"), listing("t1")]), ("comment", [listing("t3"), listing("t1")]),
        ):
            with self.subTest(operation=operation):
                result = self.project(REDDIT, operation, item)
                self.assertEqual(result["status"], "blocked_candidate")
                self.assertTrue(result["fixture_shape_verified"])
                self.assertFalse(result["accessible"])
                self.assertNotIn("private fixture", str(result))
        self.assertFalse(self.project(REDDIT, "search", listing("t1"))["fixture_shape_verified"])
        for code, expected in ((401, "permission_blocked"), (429, "quota_blocked"), (503, "source_unavailable")):
            with self.subTest(code=code):
                self.assertEqual(self.project(REDDIT, "post", None, reply=FixtureReply(code))["status"], expected)
        self.assertEqual(retrieve_fixture(REDDIT, batch_no=1, limit=10), [])

    def test_catalogue_and_deterministic_fixture_identity(self):
        catalogue = {row["source_id"]: row for row in platform_catalog()}
        self.assertTrue(all(set(row["permissions"].values()) == {"unknown"} for row in catalogue.values()))
        self.assertEqual(catalogue[REDDIT]["enabled_status"], "blocked_candidate")
        self.assertEqual(catalogue[REDDIT]["allowed_operations"], [])
        quota = {obj["kind"]: obj for obj in catalogue[YOUTUBE]["object_capabilities"]}
        self.assertEqual(quota["search"]["quota_bucket"], "search_query")
        self.assertEqual(quota["comment"]["quota_bucket"], "quota_unit")
        self.assertEqual(quota["caption_text"]["quota_units"], 200)
        pieces = []
        for index, source_id in enumerate((STACK, YOUTUBE, STACK), 1):
            rows = retrieve_fixture(source_id, batch_no=index, limit=18, published_date="2025-02-11", fetched_at=STAMP)
            self.assertEqual(rows, retrieve_fixture(source_id, batch_no=index, limit=18,
                                                  published_date="2025-02-11", fetched_at=STAMP))
            for row in rows:
                self.assertEqual(row["role"], "synthetic")
                self.assertEqual(row["published_at"], "2025-02-11T00:00:00+00:00")
                self.assertEqual(row["fetched_at"], STAMP)
                pieces.extend(row["segments"])
        self.assertEqual(len(pieces), 108)


if __name__ == "__main__":
    unittest.main()
