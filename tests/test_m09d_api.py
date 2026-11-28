"""Exercise the discovery HTTP boundary against isolated SQLite and eligible synthetic evidence."""

from dataclasses import replace
from ipaddress import ip_address
from pathlib import Path
from uuid import uuid4
import json
import socket
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.config import Settings
from src.dashboard.app import create_app
from src.discovery.workbench_config import load_catalog
from src.dashboard.personal_workspace import provision
from src.edition_policy import Deployment, Edition, LocalOwner, Permission
from src.raw_store.relation_access import RelationGrant
from test_edition_policy import fixture_root, owner_environment
import test_m09_embeddings as embedding_fixtures
from test_m09_persistence import cluster_fixture

ORIGIN = "http://127.0.0.1"
HEADERS = {"Origin": ORIGIN, "X-VOC-Action": "connectivity"}
CONNECT = socket.socket.connect


def loopback_connect(sock, address):
    if not isinstance(address, tuple) or not ip_address(address[0]).is_loopback:
        raise AssertionError("Discovery API fixture denied a non-loopback connection")
    return CONNECT(sock, address)


class DiscoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = embedding_fixtures.EmbeddingTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.assert_no_network)
        self.enterContext(patch("socket.socket.connect", new=loopback_connect))
        case = self.fixture.case
        self.scope = (case.study, case.scope, "v1")
        self.path = "/api/discovery/" + "/".join(self.scope)
        self.catalog = {self.scope: ("1.0.0", self.fixture.refs)}
        self.grants = [RelationGrant(
            "test-reviewer", "project_reviewer", "test-owner", "local:synthetic-discovery",
            "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
            frozenset({"read", "evidence", "validate"}), case.study,
        )]
        self.settings = Settings(case.db.directory)

    def client(self, *, settings=None, peer="127.0.0.1", catalog=None):
        application = create_app(
            settings or self.settings, relation_grants=lambda: self.grants,
            discovery_catalog=self.catalog if catalog is None else catalog,
            discovery_backend=self.fixture.backend,
        )
        return TestClient(application, base_url=ORIGIN, headers=HEADERS, client=(peer, 37002))

    def request(self, client, path, *, method="get", **kwargs):
        reply = getattr(client, method)(self.path + path, **kwargs)
        self.assertLess(reply.status_code, 300, reply.text)
        self.assertEqual(reply.headers["cache-control"], "no-store")
        return reply.json()

    def create(self, client):
        available = self.request(client, "/inputs")
        self.assertEqual(available["registry_version"], "1.0.0")
        ids = [row["document_id"] for row in available["inputs"]]
        self.assertEqual(len(ids), 2)
        self.assertNotIn(self.fixture.quote, json.dumps(available, ensure_ascii=False))
        return self.request(client, "/runs", method="post", json={
            "request_id": str(uuid4()), "analysis_language": "zh-CN", "output_language": "en",
            "evidence_ids": ids,
        })

    def test_create_review_replay_and_recalculate_via_local_routes(self):
        with self.client() as client, patch("src.discovery.topics._cluster_batch", side_effect=cluster_fixture):
            original = self.create(client)
            run = original["run"]
            path = "/runs/" + run["run_id"]
            self.assertEqual(self.request(client, path, params={"revision": 0}), original)
            candidate = original["candidates"][0]
            document_id = candidate["member_document_ids"][0]
            evidence = self.request(client, path + "/evidence/" + document_id)
            self.assertEqual(evidence["lineage"]["evidence_id"], next(
                row["lineage"]["evidence_id"] for row in run["members"] if row["document_id"] == document_id
            ))
            body = {"decision": "retained", "request_id": str(uuid4()), "expected_revision": 0}
            reviewed = self.request(client, path + "/candidates/0/review", method="post", json=body)
            self.assertEqual(reviewed["revision"], 1)
            self.assertEqual(reviewed["candidates"][0]["decision"], "retained")
            self.assertEqual(self.request(client, path, params={"revision": 0})["candidates"], original["candidates"])
            calculation = {"request_id": str(uuid4()), "config": {"random_seed": 17}}
            new = self.request(client, path + "/recalculate", method="post", json=calculation)
            repeated = self.request(client, path + "/recalculate", method="post", json=calculation)
            self.assertEqual(new["run"], repeated["run"])
            self.assertEqual(new["run"]["replay_of"], run["run_id"])
            self.assertEqual(new["run"]["metadata"]["operation"], "recalculation")
            self.assertEqual(new["revision"], 0)
            self.assertNotEqual(new["run"]["run_id"], run["run_id"])
            comparison = self.request(client, path + "/compare/" + new["run"]["run_id"])
            self.assertEqual(len(comparison["membership_changes"]), 2)
            self.assertIn("candidate_coverage", comparison)
            self.assertEqual(len(self.request(client, "/runs")["runs"]), 2)
            self.assertEqual(self.request(client, path)["run"], run)

    def test_revocation_fails_closed_in_views_inputs_and_operations(self):
        with self.client() as client, patch("src.discovery.topics._cluster_batch", side_effect=cluster_fixture):
            run = self.create(client)["run"]
            member = next(row for row in run["members"]
                          if row["lineage"]["record_id"] == self.fixture.interval.record_id)
            self.fixture.case.revoke_batch(self.fixture.batch)
            path = "/runs/" + run["run_id"]
            viewed = self.request(client, path)
            current = next(row for row in viewed["run"]["members"] if row["document_id"] == member["document_id"])
            self.assertFalse(current["evidence_eligible"])
            self.assertNotIn("lineage", current)
            self.assertNotIn(member["document_id"], {
                row["document_id"] for row in self.request(client, "/inputs")["inputs"]
            })
            self.assertEqual(client.get(self.path + path + "/evidence/" + member["document_id"]).status_code, 409)
            self.assertEqual(client.post(self.path + path + "/recalculate", json={
                "request_id": str(uuid4()),
            }).status_code, 409)
            self.assertEqual(client.get(self.path + path + "/compare/" + run["run_id"]).status_code, 409)

    def test_scope_origin_peer_grant_and_cloud_fail_closed(self):
        with self.client() as client:
            self.assertEqual(client.get(self.path + "/runs", headers={"Origin": "https://foreign.invalid"}).status_code, 403)
            self.assertEqual(client.get(self.path + "/runs", headers={"Origin": ""}).status_code, 403)
            foreign = "/api/discovery/" + "/".join([str(uuid4()), *self.scope[1:]]) + "/runs"
            self.assertEqual(client.get(foreign).status_code, 404)
            self.assertEqual(client.get(self.path.rsplit("/", 1)[0] + "/v2/runs").status_code, 404)
            self.assertEqual(client.post(self.path + "/runs", json={
                "request_id": str(uuid4()), "analysis_language": "en", "output_language": "en",
                "evidence_ids": ["m09-" + "0" * 64],
            }).status_code, 409)
            self.grants[0] = replace(self.grants[0], evidence_refs=frozenset({(1, "unrelated", "unrelated")}))
            self.assertEqual(client.get(self.path + "/runs").status_code, 404)
        with self.client(peer="192.0.2.10") as client:
            self.assertEqual(client.get(self.path + "/runs").status_code, 403)
        with self.client(settings=replace(self.settings, deployment=Deployment.CLOUD)) as client:
            self.assertEqual(client.get(self.path + "/runs").status_code, 403)

    def test_catalog_pins_only_references_without_content(self):
        path = self.settings.directory / "m09-discovery-synthetic.json"
        path.write_text(json.dumps([dict(zip(("study_id", "scope_id", "scope_version"), self.scope)) | {
            "registry_version": "1.0.0", "references": [
                {"kind": "mention", "record_id": ref.record.record_id, "raw_sha256": ref.record.raw_sha256,
                 "segment_revision": ref.segment_revision, "mention_id": ref.mention_id,
                 "evidence_id": ref.evidence_id, "original_language": ref.original_language}
                for ref in self.fixture.refs
            ],
        }]), encoding="utf-8")
        self.assertEqual(load_catalog(self.settings.directory), self.catalog)

    def test_personal_discovery_has_scope_read_and_separate_review_permission(self):
        directory = Path(self.enterContext(fixture_root("voc-m09d-personal-"))) / "workspace"
        binding = provision(directory, "合成主题研究", "离线场景", uuid4())
        key = tuple(binding[field] for field in ("study_id", "scope_id", "scope_version"))
        environment, proof = owner_environment(binding, permissions=[Permission.READ_CORPUS.value])
        settings = Settings(directory, edition=Edition.PERSONAL, personal_owner=LocalOwner.from_environment(environment))
        scope = "/api/discovery/" + "/".join(key)
        with self.client(settings=settings, catalog={key: ("1.0.0", ())}) as client:
            self.assertEqual(client.get(scope + "/runs").status_code, 401)
            auth = ("owner", proof)
            result = client.get(scope + "/runs", auth=auth).raise_for_status().json()
            self.assertEqual(result["runs"], [])
            self.assertFalse(result["review_available"])
            self.assertEqual(client.get(scope.rsplit("/", 1)[0] + "/v2/runs", auth=auth).status_code, 404)
            review = client.post(scope + f"/runs/{uuid4()}/candidates/0/review", auth=auth,
                                 json={"request_id": str(uuid4()), "decision": "retained", "expected_revision": 0})
            self.assertEqual(review.status_code, 403)
