"""Owner-only local execution for explicitly approved Personal acceptance batches."""

import argparse
from contextlib import closing
from getpass import getpass
from datetime import UTC, datetime
from html import escape
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
import warnings

from src.config import MODEL, Settings
from src.dashboard.edition_access import has_scope
from src.dashboard.personal_governance import governance_decision
from src.edition_policy import Deployment, Domain, Edition, EditionPolicy, Permission, REFERENCE, utc_timestamp
from src.execution.personal_admission import digest, model_payloads, search_payload, source_identity
from src.execution.personal_live_evidence import evaluate_formal_batch
from src.execution.personal_live_transport import PersonalLiveTransport
from src.execution.transport import number, redact
from src.ingestion.public_source import DOMAIN, LICENSES, SITE, fetch_forum_post, post_id
from src.raw_store.credentials import VaultError
from src.raw_store.personal_live_authority import AuthorityError, PersonalLiveAuthority
from src.raw_store.personal_validation import ACTIVE, BatchContext, Budget, OperationGrant, Receipt, ValidationLedger
from src.raw_store.personal_validation_credentials import validation_binding
from src.raw_store.runtime_binding import APPLICATION_IDS
from src.raw_store.store import Conflict, Store


MATERIAL = {"account_evidence", "api_access", "terms", "risk", "allowance", "rates"}
DEPLOYMENT_SUBJECT = "live-owner-deployment"


def _reference(value):
    return isinstance(value, str) and REFERENCE.fullmatch(value)


def _observed_source_url(url):
    parsed = urlsplit(url)
    return parsed._replace(query="", fragment="").geturl()


def _project_reply(operation, payload, reply):
    body = reply.body if isinstance(reply.body, dict) else {}
    if operation == "search":
        hits = []
        for hit in body.get("results", [])[:5] if isinstance(body.get("results"), list) else ():
            try:
                canonical = source_identity(hit["url"])
                hits.append({"url": canonical, "actual_url": _observed_source_url(hit["url"])})
            except (TypeError, KeyError, ValueError):
                continue
        usage = body.get("usage")
        credits = number(usage.get("credits")) if isinstance(usage, dict) else None
        valid = reply.status == 200 and bool(hits) and credits == 1
        return {"results": hits, "usage": {"credits": credits}}, valid, credits, None
    if operation == "source":
        _, _, citation = fetch_forum_post(post_id(payload["url"]), "tavily", transport=lambda *_: reply)
        if not citation["verified"]:
            return {"items": []}, False, None, None
        projected = {
            "question_id": int(citation["post_id"]), "link": payload["url"],
            "body": "<p>" + escape(citation["text"]) + "</p>", "content_license": citation["license"],
            "owner": {"display_name": citation["author"]},
            "creation_date": int(utc_timestamp(citation["published_at"]).timestamp()),
        }
        provenance = {
            "collected_at": datetime.now(UTC).isoformat(),
            "final_url": _observed_source_url(citation["url"]), "method": citation["method"],
            "license_url": citation["license_url"], "classification": "public_approved",
        }
        return {"items": [projected], "provenance": provenance}, True, None, digest(citation["text"])
    raise Conflict("LIVE_MODEL_HARD_BUDGET_UNVERIFIED")


class LiveAdmission:
    def __init__(self, store, policy, study_id, proof, authority_directory):
        if (policy.edition != Edition.PERSONAL or policy.deployment != Deployment.LOCAL
                or policy.owner is None or not policy.owner.authenticates(proof)):
            raise Conflict("LIVE_OWNER_AUTHENTICATION_REQUIRED")
        self.store = store
        self.policy = policy
        self.study_id = study_id
        self._proof = proof
        self.authority = PersonalLiveAuthority(authority_directory, database=store.path)
        self.ledger = ValidationLedger(store, live_continuity=self.authority.check)
        self.transport = PersonalLiveTransport()
        with store.db() as db:
            self.context = self._context(db)

    def _context(self, db):
        decision = self.policy.decide(
            Permission.WRITE_PERSONAL_APPROVALS, Domain.LOCAL_WORKSPACE,
            proof=self._proof, study_id=self.study_id, current_scope=lambda scope: has_scope(db, scope),
        )
        if not decision.allowed:
            raise Conflict("LIVE_OWNER_SCOPE_REQUIRED")
        bound = governance_decision(decision, self.policy.owner)
        return BatchContext(
            bound.scope.study_id, bound.scope.scope_id, bound.scope.scope_version,
            bound.actor_ref, bound.owner_ref, bound.evidence_refs[0], bound.policy_version,
        )

    def _owner(self, db, batch, grant):
        return self._context(db) == self.context

    def _owner_fingerprint(self):
        owner = self.policy.owner
        grants = [
            [item.scope.study_id, item.scope.scope_id, item.scope.scope_version, item.purpose,
             sorted(item.permissions), item.evidence_ref, item.starts_at.isoformat(), item.expires_at.isoformat()]
            for item in owner.grants
        ]
        return digest([owner.actor_ref, owner.owner_ref, owner.proof_sha256, grants])

    def provision(self, approved):
        if (approved.keys() != {"owner_ref", "study_id", "scope_id", "scope_version", "evidence_ref"}
                or any(approved[field] != getattr(self.context, field) for field in
                       ("owner_ref", "study_id", "scope_id", "scope_version"))
                or not _reference(approved["evidence_ref"])):
            raise Conflict("LIVE_DEPLOYMENT_APPROVAL_MISMATCH")
        with self.ledger._transaction() as db:
            if not self._owner(db, None, None):
                raise Conflict("LIVE_OWNER_SCOPE_REQUIRED")
            previous = self.ledger.current_authority(db, self.context, DEPLOYMENT_SUBJECT)
            if previous is not None:
                self._require_deployment(db)
                if previous["evidence_ref"] != approved["evidence_ref"]:
                    raise Conflict("LIVE_DEPLOYMENT_APPROVAL_MISMATCH")
                return previous["revision"]
            revision = self.authority.deployment_record(self._owner_fingerprint(), approved["evidence_ref"], create=True)
            self.ledger._authority_event(db, self.context, DEPLOYMENT_SUBJECT, revision, "current",
                                         approved["evidence_ref"])
            return revision

    def _require_deployment(self, db):
        record = self.ledger.current_authority(db, self.context, DEPLOYMENT_SUBJECT)
        if (record is None or record["state"] != "current" or record["revision"] !=
                self.authority.deployment_record(self._owner_fingerprint(), record["evidence_ref"])):
            raise Conflict("LIVE_DEPLOYMENT_BINDING_REQUIRED")

    def draft(self, approved):
        if (approved.keys() != {"starts_at", "expires_at", "budget", "currency", "decimals", "single_cost",
                               "evidence_ref", "owner_ref", "study_id", "scope_id", "scope_version"}
                or any(approved[field] != getattr(self.context, field) for field in
                       ("owner_ref", "study_id", "scope_id", "scope_version"))):
            raise Conflict("LIVE_BATCH_APPROVAL_MISMATCH")
        with self.store.db() as db:
            self._require_deployment(db)
        terms = {key: approved[key] for key in
                 ("starts_at", "expires_at", "currency", "decimals", "single_cost", "evidence_ref")}
        batch = self.ledger.draft(self.context, budget=Budget(**approved["budget"]), recheck=self._owner, **terms)
        self.authority.register_batch(batch)
        return batch["batch_id"]

    def _batch(self, db, batch_id):
        self._require_deployment(db)
        batch = self.ledger.batch(db, batch_id, self.context)
        if not self._owner(db, batch, None) or batch["mode"] != "formal_live":
            raise Conflict("LIVE_BATCH_APPROVAL_MISMATCH")
        return batch

    def _material(self, packet):
        operation, slot = packet["operation"], packet["slot"]
        target = packet["target"]
        if operation == "search":
            if target != DOMAIN:
                raise Conflict("LIVE_SEARCH_DOMAIN_NOT_APPROVED")
            return search_payload(packet["query"]), ""
        if source_identity(target) != target or packet.get("license") not in LICENSES:
            raise Conflict("LIVE_SOURCE_NOT_APPROVED")
        if operation == "source":
            return {"url": target, "site": SITE, "filter": "withbody"}, ""
        if operation == "model" and type(slot) is int and slot in (1, 2):
            pairs = packet["choices"]
            if not isinstance(pairs, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in pairs):
                raise Conflict("LIVE_MODEL_CHOICES_INVALID")
            choices = dict(pairs)
            if len(choices) != len(pairs) or digest(packet["text"]) != packet["model_input_sha256"]:
                raise Conflict("LIVE_MODEL_CHOICES_INVALID")
            shards = model_payloads(packet["text"], choices)
            return shards[slot - 1], "personal-d-live-v1." + digest([pairs, shards])
        raise Conflict("LIVE_OPERATION_INVALID")

    def _approved_operation(self, batch_id, packet):
        if packet["batch_id"] != batch_id or packet["owner_ref"] != self.context.owner_ref:
            raise Conflict("LIVE_OPERATION_APPROVAL_MISMATCH")
        notes = packet["material"]
        operation = packet["operation"]
        required = MATERIAL | ({"source_permission", "retention", "attribution"} if operation != "search" else set())
        if (operation != "search" and not _reference(packet.get("source_ref"))
                or notes.keys() != required or not all(_reference(ref) for ref in notes.values())):
            raise Conflict("LIVE_APPROVAL_MATERIAL_REQUIRED")
        payload, version = self._material(packet)
        estimate = Budget(**packet["limit"])
        if digest(payload) != packet["payload_sha256"]:
            raise Conflict("LIVE_PAYLOAD_DIGEST_MISMATCH")
        prepared = self.transport.prepare(operation, payload, slot=packet["slot"], budget=estimate)
        approval = OperationGrant(
            operation=operation, provider=packet["provider"], slot=packet["slot"],
            account_ref=packet["account_ref"], channel_ref=packet["channel_ref"],
            credential_revision=packet["credential_revision"], model=MODEL if operation == "model" else "",
            approval_event_id=packet.get("approval_event_id"), material_revision=digest(packet),
            source_ref=DOMAIN if operation == "search" else packet["source_ref"],
            source_sha256=digest(packet["target"]), payload_sha256=packet["payload_sha256"],
            question_version=version, valid_from=packet["valid_from"], expires_at=packet["expires_at"],
            limit=estimate, account_limit=Budget(**packet["account_limit"]), evidence_ref=packet["evidence_ref"],
            depends_on=packet.get("depends_on"), depends_on_sha256=packet.get("depends_on_sha256"),
        )
        return approval, payload, prepared

    def _current_operation(self, db, batch, grant, packet, payload):
        self._require_deployment(db)
        if not self._owner(db, batch, grant) or grant["material_revision"] != digest(packet):
            raise Conflict("LIVE_OPERATION_APPROVAL_MISMATCH")
        self._verify_reconciled_charges(db, batch)
        if grant["operation"] == "source":
            parent, parent_batch, parent_grant = self.ledger._request(db, grant["depends_on"], self.context)
            if (parent_batch["batch_id"] != batch["batch_id"] or not self.authority.check(db, batch, parent_grant)
                    or not parent_grant["valid_from"] <= self.ledger._now() < parent_grant["expires_at"]):
                raise Conflict("LIVE_SOURCE_SEARCH_NOT_CURRENT")
            validation_binding(self.store, db, self.context, parent_grant)
            evidence = self.authority.read_archive(batch, parent_grant, parent, grant["depends_on_sha256"])
            if not any(hit["url"] == payload["url"] for hit in evidence["response"]["results"]):
                raise Conflict("LIVE_SOURCE_NOT_IN_APPROVED_SEARCH")
        return validation_binding(self.store, db, self.context, grant)

    def authorize(self, batch_id, packet):
        approval, payload, _ = self._approved_operation(batch_id, packet)

        def check(db, batch, grant):
            self._current_operation(db, batch, grant, packet, payload)
            return True

        grant = self.ledger.authorize(batch_id, self.context, approval, check)
        with self.store.db() as db:
            self.authority.authorize(self._batch(db, batch_id), grant)
        return grant["grant_id"]

    def execute(self, batch_id, grant_id, packet):
        approval, payload, prepared = self._approved_operation(batch_id, packet)
        secret = None

        def check(db, batch, grant):
            nonlocal secret
            secret = self._current_operation(db, batch, grant, packet, payload)
            return True

        request = self.ledger.reserve(
            batch_id, self.context, grant_id, approval.slot, approval.payload_sha256, approval.limit, check,
        )
        request_id = request["request_id"]
        if request["state"] != "reserved" or self.ledger.claim(request_id, self.context, check) is None:
            return {"request_id": request_id, "dispatched": False}

        def owns_claim(db, batch, grant):
            return batch["batch_id"] == batch_id and grant["grant_id"] == grant_id

        try:
            with self.ledger._transaction() as db:
                claimed, batch, grant = self.ledger._request(db, request_id, self.context)
                if (batch["batch_id"] != batch_id or grant["grant_id"] != grant_id
                        or batch["state"] not in ACTIVE or claimed["state"] != "claimed"):
                    raise Conflict("LIVE_SEND_RIGHT_UNAVAILABLE")
                self.ledger._authorize_operation(db, self.context, batch, grant, check)
                self.ledger._recheck_reserved_budget(db, batch, grant, claimed)
                if not self.authority.claim(batch, grant, claimed):
                    raise Conflict("LIVE_SEND_RIGHT_UNAVAILABLE")
                if not self.authority.check(db, batch, grant):
                    raise Conflict("LIVE_SEND_RIGHT_UNAVAILABLE")
            reply = self.transport.send(prepared, secret=secret)
            response, valid, credits, quote_sha = _project_reply(approval.operation, payload, reply.response)
            if approval.operation == "source" and valid:
                valid = response["items"][0]["content_license"] == packet["license"]
                if not valid:
                    response, quote_sha = {"items": []}, None
            ref = self.authority.archive(batch, grant, request, payload, response)
            receipt = Receipt(
                digest(response), reply.response.status, ref, reply.provider_request_id,
                credits=credits, actual_units=0 if approval.operation == "source" and valid else None,
                balance_status="not_applicable" if approval.operation == "source" else "unsynced",
                valid=valid, reason="schema_gap" if reply.response.status == 200 else "http_or_transport_failure",
                source_sha256=approval.source_sha256, quote_sha256=quote_sha,
            )
            result = self.ledger.receipt(request_id, self.context, receipt, check)
        except Exception:
            self.ledger.mark_unknown(request_id, self.context, "send_or_receipt_outcome_unknown", owns_claim)
            return {"request_id": request_id, "state": "reconciliation"}
        finally:
            secret = None
        return {"request_id": request_id, "dispatched": True, "eligible": bool(result["eligible"])}

    def stop(self, batch_id, state):
        if state not in {"paused", "revoked"}:
            raise Conflict("LIVE_OPERATION_INVALID")
        with self.ledger._transaction() as db:
            batch = self._batch(db, batch_id)
            self.authority.revoke(batch)
        return self.ledger.transition(batch_id, self.context, state, "owner_" + state, self._owner)["state"]

    def inspect(self, batch_id):
        with self.store.db() as db:
            self._require_deployment(db)
        view = self.ledger.view(batch_id, self.context, self._owner)
        batch = view["batch"]
        if batch["mode"] != "formal_live":
            raise Conflict("LIVE_BATCH_APPROVAL_MISMATCH")
        grants = {grant["grant_id"]: grant for grant in view["grants"]}
        receipts = {receipt["request_id"]: receipt for receipt in view["receipts"]}
        results = []
        for request in view["requests"]:
            grant = grants.get(request["grant_id"])
            receipt = receipts.get(request["request_id"])
            projection = {key: request[key] for key in ("request_id", "operation", "slot", "state")}
            if receipt and grant:
                projection.update({key: receipt[key] for key in (
                    "provider_request_id", "response_status", "response_sha256", "credits", "quote_sha256", "eligible",
                )})
                if request["operation"] == "search" and receipt["eligible"] == 1:
                    artifact = self.authority.read_archive(batch, grant, request, receipt["response_sha256"])
                    projection["hits"] = artifact["response"]["results"]
            results.append(projection)
        return {"batch_id": batch_id, "state": batch["state"], "requests": results, "remaining": view["remaining"]}

    def recover(self, batch_id):
        with self.store.db() as db:
            self._batch(db, batch_id)
        return self.ledger.recover(batch_id, self.context, self._owner)["state"]

    def _verify_reconciled_charges(self, db, batch):
        for reconciliation in db.execute("""
            SELECT c.* FROM personal_validation_reconciliations c
            JOIN personal_validation_requests q USING (request_id) WHERE q.batch_id=?
        """, (batch["batch_id"],)):
            request, _, grant = self.ledger._request(db, reconciliation["request_id"], self.context)
            try:
                proof = self.authority.read_charge(batch, grant, request, reconciliation["evidence_ref"])
            except AuthorityError:
                raise Conflict("LIVE_RECONCILIATION_EVIDENCE_UNAVAILABLE") from None
            if (proof["actual_units"], proof["bill_ref"]) != (
                    reconciliation["actual_units"], reconciliation["subject_ref"]):
                raise Conflict("LIVE_RECONCILIATION_EVIDENCE_UNAVAILABLE")

    def resume(self, batch_id):
        with self.store.db() as db:
            self._batch(db, batch_id)

        def recheck(db, batch, grant):
            if not self._owner(db, batch, grant) or not self.authority.check(db, batch, None):
                return False
            self._verify_reconciled_charges(db, batch)
            view = self.ledger._view(db, batch, self.context)
            receipts = {receipt["request_id"]: receipt for receipt in view["receipts"]}
            return (bool(view["requests"]) and batch["starts_at"] <= self.ledger._now() < batch["expires_at"]
                    and all(request["state"] == "settled"
                            and receipts.get(request["request_id"], {}).get("eligible") == 1
                            for request in view["requests"]))

        return self.ledger.transition(batch_id, self.context, "approved", "charge_review_complete", recheck)["state"]

    def reconcile(self, batch_id, proof):
        if (not isinstance(proof, dict) or proof.keys() != {"request_id", "provider", "account_ref",
                "provider_request_id", "currency", "actual_units", "bill_ref"}):
            raise Conflict("LIVE_RECONCILIATION_PROOF_MISMATCH")
        request_id = proof["request_id"]
        with self.store.db() as db:
            batch = self._batch(db, batch_id)
            request, _, grant = self.ledger._request(db, request_id, self.context)
            receipt = db.execute(
                "SELECT * FROM personal_validation_receipts WHERE request_id=?", (request_id,),
            ).fetchone()
            prior = db.execute("""
                SELECT evidence_ref FROM personal_validation_reconciliations
                WHERE request_id=? ORDER BY sequence DESC LIMIT 1
            """, (request_id,)).fetchone()
        if (request["batch_id"] != batch_id or not self.authority.verify_claim(batch, grant, request)
                or any(proof[key] != grant[key] for key in ("provider", "account_ref"))
                or not _reference(proof["provider_request_id"])
                or (receipt is not None and receipt["provider_request_id"]
                    and receipt["provider_request_id"] != proof["provider_request_id"])
                or proof["currency"] != batch["currency"] or number(proof["actual_units"]) is None
                or not _reference(proof["bill_ref"])):
            raise Conflict("LIVE_RECONCILIATION_PROOF_MISMATCH")
        if prior is None:
            if request["state"] != "reconciliation":
                raise Conflict("VALIDATION_NOT_AWAITING_RECONCILIATION")
            if receipt is not None and receipt["actual_units"] not in {None, proof["actual_units"]}:
                raise Conflict("VALIDATION_RECONCILIATION_CONFLICT")
            ref = self.authority.archive_charge(batch, grant, request, proof)
        else:
            ref = prior["evidence_ref"]

        def verify(db, current_batch, current_grant):
            if not self._owner(db, current_batch, current_grant):
                return False
            if self.authority.read_charge(current_batch, current_grant, request, ref) != proof:
                raise Conflict("VALIDATION_RECONCILIATION_CONFLICT")
            return True

        result = self.ledger.reconcile(request_id, self.context, proof["actual_units"], proof["bill_ref"], ref, verify)
        return {"request_id": request_id, "actual_units": result["actual_units"]}

    def review(self, batch_id, requirement, proof):
        if requirement == "C0-2" and (
            proof.keys() != {"source_request_id", "source_quote_sha256", "model_input_sha256", "redaction_ref"}
            or not _reference(proof["redaction_ref"])
        ):
            raise Conflict("LIVE_TRANSFORMATION_REVIEW_MISMATCH")
        with self.store.db() as db:
            batch = self._batch(db, batch_id)
            if requirement == "C0-2":
                request, parent_batch, grant = self.ledger._request(db, proof["source_request_id"], self.context)
                receipt = db.execute(
                    "SELECT * FROM personal_validation_receipts WHERE request_id=?", (request["request_id"],),
                ).fetchone()
                transformed = proof["model_input_sha256"]
                if (parent_batch["batch_id"] != batch_id or request["operation"] != "source"
                        or request["state"] != "settled" or not receipt or not receipt["eligible"]
                        or receipt["quote_sha256"] != proof["source_quote_sha256"]
                        or not isinstance(transformed, str) or len(transformed) != 64
                        or any(character not in "0123456789abcdef" for character in transformed)
                        or not self.authority.has_archive(batch, grant, request, receipt["response_sha256"])):
                    raise Conflict("LIVE_TRANSFORMATION_REVIEW_MISMATCH")
        ref, sha = self.authority.archive_review(batch, requirement, proof)
        kind = "formal_live" if requirement in {"C0-2", "C0-4"} else "formal_offline"
        self.ledger.add_evidence(batch_id, self.context, requirement, kind, ref, sha, "owner_reviewed", self._owner)
        return ref

    def matrix(self, batch_id):
        with self.store.db() as db:
            db.execute("BEGIN")
            return self._matrix(db, self._batch(db, batch_id))

    def _matrix(self, db, batch):
        view = self.ledger._view(db, batch, self.context)
        current, reviewed, archives, charges = set(), set(), {}, {}
        for grant in view["grants"]:
            try:
                self.ledger._require_send_authority(db, batch, grant)
                self.ledger._authorize_operation(db, self.context, batch, grant, self._owner)
                validation_binding(self.store, db, self.context, grant)
            except (ValueError, VaultError):
                continue
            current.add(grant["grant_id"])
        grants = {item["grant_id"]: item for item in view["grants"]}
        receipts = {item["request_id"]: item for item in view["receipts"]}
        reconciled = {item["request_id"]: item for item in view["reconciliations"]}
        for request in view["requests"]:
            request_id = request["request_id"]
            receipt = receipts.get(request_id)
            grant = grants.get(request["grant_id"])
            if not receipt or not grant or receipt["evidence_ref"] != f"live-receipt-{request_id}":
                continue
            try:
                archives[receipt["evidence_ref"]] = self.authority.read_archive(
                    batch, grant, request, receipt["response_sha256"],
                )
                if request_id in reconciled:
                    entry = reconciled[request_id]
                    proof = self.authority.read_charge(batch, grant, request, entry["evidence_ref"])
                    if proof["actual_units"] == entry["actual_units"] and proof["bill_ref"] == entry["subject_ref"]:
                        charges[request_id] = {key: proof[key] for key in (
                            "actual_units", "bill_ref", "provider_request_id", "provider", "account_ref",
                        )}
                elif request["operation"] == "source" and receipt["actual_units"] == 0:
                    charges[request_id] = {
                        "actual_units": 0, "bill_ref": receipt["evidence_ref"],
                        **{key: receipt[key] for key in ("provider_request_id", "provider", "account_ref")},
                    }
            except ValueError:
                continue
        model_input_sha256 = None
        for item in view["evidence"]:
            try:
                artifact = self.authority.read_review(
                    batch, item["requirement"], item["evidence_ref"], item["evidence_sha256"],
                )
            except ValueError:
                continue
            if item["requirement"] == "C0-4" and artifact.get("charges") != charges:
                continue
            if item["requirement"] == "C0-2":
                source = receipts.get(artifact.get("source_request_id"))
                if (source and source["eligible"] and source["evidence_ref"] in archives
                        and artifact.get("source_quote_sha256") == source["quote_sha256"]):
                    model_input_sha256 = artifact.get("model_input_sha256")
                continue
            archives[item["evidence_ref"]] = artifact
            reviewed.add((item["evidence_ref"], item["evidence_sha256"]))
        return evaluate_formal_batch(
            view, currently_authorized=self.authority.check(db, batch, None)
            and batch["starts_at"] <= self.ledger._now() < batch["expires_at"],
            current_grant_ids=current, reviewed_refs=reviewed, reviewed_model_input_sha256=model_input_sha256,
            read_archive=archives.get,
        )

    def complete(self, batch_id):
        def verified(db, batch, grant):
            return all(result["status"] == "PASS" for result in self._matrix(db, batch).values())

        with self.store.db() as db:
            batch = self._batch(db, batch_id)
        if batch["state"] not in {"evidence_review", "complete"}:
            self.ledger.transition(batch_id, self.context, "evidence_review", "formal_evidence_verified", self._owner,
                                   formal_review=verified)
        return self.ledger.transition(batch_id, self.context, "complete", "formal_evidence_verified", self._owner,
                                      formal_review=verified)["state"]


def _packet(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink() or path.stat().st_size > 256_000:
        raise Conflict("LIVE_LOCAL_PACKET_REQUIRED")
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise Conflict("LIVE_PACKET_DUPLICATE_KEY")
        return result
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    if not isinstance(value, dict) or redact(value) != value:
        raise Conflict("LIVE_PACKET_HAS_RESTRICTED_FIELDS")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--batch")
    parser.add_argument("--grant")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--requirement", choices=("C0-2", "C0-4", "C0-5", "C0-6"))
    parser.add_argument("operation", choices=("provision", "draft", "authorize", "execute", "pause", "revoke", "recover", "resume",
                                              "reconcile", "review", "inspect", "matrix", "complete"))
    args = parser.parse_args()
    try:
        if os.environ.get("VOC_PERSONAL_LIVE_PRE_ADMISSION") != "1":
            raise Conflict("LIVE_DEPLOYMENT_DISABLED")
        settings = Settings.load_base()
        if settings.edition != Edition.PERSONAL or settings.deployment != Deployment.LOCAL:
            raise Conflict("LIVE_DEPLOYMENT_DISABLED")
        policy = EditionPolicy(settings.edition, settings.deployment, settings.personal_owner)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            proof = getpass("本机 Owner 身份证明：")
        if not policy.owner.authenticates(proof):
            raise Conflict("LIVE_OWNER_AUTHENTICATION_REQUIRED")
        path = settings.directory / "connectivity.sqlite3"
        if not path.is_file() or path.is_symlink():
            raise Conflict("LIVE_APPROVED_WORKSPACE_REQUIRED")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_IDS[Edition.PERSONAL]:
                raise Conflict("LIVE_APPROVED_WORKSPACE_REQUIRED")
            if db.execute("PRAGMA user_version").fetchone()[0] != 11:
                raise Conflict("LIVE_APPROVED_MIGRATION_REQUIRED")
        authority = os.environ.get("VOC_PERSONAL_LIVE_AUTHORITY_DIR", "")
        engine = LiveAdmission(Store(settings.directory, edition=settings.edition), policy, args.study, proof, authority)
        packet = _packet(args.packet) if args.packet else None
        if args.operation == "provision":
            result = {"deployment_revision": engine.provision(packet)}
        elif args.operation == "draft":
            result = {"batch_id": engine.draft(packet)}
        elif args.operation == "authorize":
            result = {"grant_id": engine.authorize(args.batch, packet)}
        elif args.operation == "execute":
            result = engine.execute(args.batch, args.grant, packet)
        elif args.operation in {"pause", "revoke"}:
            result = {"state": engine.stop(args.batch, args.operation + "d")}
        elif args.operation == "recover":
            result = {"state": engine.recover(args.batch)}
        elif args.operation == "resume":
            result = {"state": engine.resume(args.batch)}
        elif args.operation == "reconcile":
            result = engine.reconcile(args.batch, packet)
        elif args.operation == "review":
            result = {"evidence_ref": engine.review(args.batch, args.requirement, packet)}
        elif args.operation == "inspect":
            result = engine.inspect(args.batch)
        elif args.operation == "complete":
            result = {"state": engine.complete(args.batch)}
        else:
            result = engine.matrix(args.batch)
    except (ValueError, VaultError, OSError, sqlite3.Error, KeyError, TypeError, AttributeError, Warning) as exc:
        code = str(exc)
        parser.exit(1, (code if code.isascii() and code.replace("_", "").isalpha() and code.isupper()
                        else "LIVE_OPERATION_REJECTED") + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
