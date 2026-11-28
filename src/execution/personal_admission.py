"""Server-side Personal D execution for isolated fixtures."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import sqlite3
from urllib.parse import urlsplit
from fastapi import HTTPException

from src.config import MODEL
from src.dashboard.personal_governance import effective_binding, governance_decision
from src.edition_policy import Deployment, Domain, Edition, Permission, REFERENCE, utc_timestamp
from src.execution import jev
from src.execution.transport import Response, network, number, outbound, redact
from src.ingestion.m08_retrieval import normalize_url
from src.ingestion.m08_search import _query_parameters
from src.ingestion.public_source import DOMAIN, LICENSES, fetch_forum_post, post_id
from src.raw_store.credentials import VaultError
from src.raw_store.personal_approval_evidence import read_registry
from src.raw_store.personal_approvals import SCOPED, projection, scope_args
from src.raw_store.personal_credentials import PersonalCredentials
from src.raw_store.personal_validation import BatchContext, Budget, Receipt, ValidationLedger
from src.raw_store.personal_validation_credentials import validation_binding
from src.raw_store.store import Conflict, dump


QUESTION_VERSION = "personal-d-engineering-v1"


def digest(value):
    return sha256(dump(value).encode("utf-8")).hexdigest()


def source_identity(url):
    normalized = normalize_url(url, {DOMAIN})
    parsed = urlsplit(normalized)
    ident = post_id(normalized)
    if ident is None or parsed.query:
        raise ValueError("SOURCE_OUTSIDE_D_SCOPE")
    return f"https://{DOMAIN}/questions/{ident}"


def search_payload(query):
    parameters, unsupported, notes = _query_parameters("tavily", query, 5)
    if (parameters.get("include_domains") != [DOMAIN] or unsupported or notes
            or redact(parameters) != parameters):
        raise ValueError("SEARCH_OUTSIDE_D_SCOPE")
    return parameters


def model_payloads(text, options):
    if (not isinstance(text, str) or not 12 <= len(text) <= 400
            or not text.isprintable() or redact(text) != text):
        raise ValueError("MODEL_INPUT_NOT_APPROVED")
    if (not isinstance(options, dict) or len(options) != 11
            or any(not isinstance(key, str) or not REFERENCE.fullmatch(key)
                   or not isinstance(value, str) or not 1 <= len(value) <= 240
                   or not value.isprintable() for key, value in options.items())
            or redact(options) != options):
        raise ValueError("MODEL_QUESTION_SET_INVALID")
    questions = jev.questions()
    questions["intent"] = jev.intent_question(options)
    questions["in_registry"]["instructions"] = (
        "Does the passage express any of these intents: " + "; ".join(options.values()) + "?"
    )
    return tuple({"model": MODEL, "state": text, "questions": asked} for asked in jev.split(questions))


@dataclass(frozen=True)
class SourcePermission:
    ref: str
    url: str
    license_name: str
    classification: str
    expires_at: str
    model_input_sha256: str

    def current(self, at):
        return (
            self.license_name in LICENSES and self.classification == "public_approved"
            and at < utc_timestamp(self.expires_at) and source_identity(self.url) == self.url
        )


@dataclass(frozen=True)
class FixtureReply:
    response: Response
    evidence_ref: str
    provider_request_id: str | None = None
    actual_units: int | None = None


def _active_material(ledger, db, context, subject, revision):
    row = ledger.current_authority(db, context, subject)
    return row is not None and row["state"] == "current" and row["revision"] == revision


def question_version(payloads):
    return QUESTION_VERSION + "." + digest([payload["questions"] for payload in payloads])


def _c_approval(store, db, decision, grant, at, estimate):
    vault = PersonalCredentials(store.directory, study_id=decision.scope.study_id, scope_id=decision.scope.scope_id)
    binding = effective_binding(db, decision, vault)
    event = db.execute(
        "SELECT * FROM personal_provider_approval_events WHERE event_id=? AND " + SCOPED,
        (grant["approval_event_id"], *scope_args(decision)),
    ).fetchone()
    if not event or event["kind"] != "approved" or utc_timestamp(event["effective_at"]) > at:
        return False
    if any(event[field] != grant[field] for field in ("provider", "account_ref", "channel_ref",
                                                     "credential_revision", "model")):
        return False
    if event["budget_unit"] != "TOKENS":
        return False
    other_shards = db.execute(
        """SELECT q.total_tokens AS reserved, r.total_tokens AS observed
           FROM personal_validation_requests q JOIN personal_validation_grants g USING(grant_id)
           LEFT JOIN personal_validation_receipts r USING(request_id)
           WHERE g.approval_event_id=? AND g.grant_id<>?
             AND (SELECT state FROM personal_validation_request_events e WHERE e.request_id=q.request_id
                  ORDER BY sequence DESC LIMIT 1)<>'released'""",
        (event["event_id"], grant["grant_id"]),
    )
    if estimate.total_tokens + sum(max(row["reserved"], row["observed"] or 0) for row in other_shards) > event["budget_limit"]:
        return False
    registry = read_registry(vault.directory, decision.scope, decision.purpose)
    return projection(db, event, decision, binding, registry, at)["status"] == "ACTIVE"


class PersonalAdmission:
    """The application does not install a supplier transport or expose a dispatch route."""

    def __init__(self, store, *, fixture_transport=None):
        if fixture_transport is network or (fixture_transport is not None and not callable(fixture_transport)):
            raise ValueError("PERSONAL_VALIDATION_REQUIRES_FIXTURE_TRANSPORT")
        self.store = store
        self.transport = fixture_transport
        self.ledger = ValidationLedger(store, engineering_fixture=fixture_transport is not None)

    def recheck(self, context, authorize, *, owner, source=None, operation=None, payload=None, estimate=None,
                model_version=None):
        def check(db, batch, grant):
            try:
                decision = authorize(db)
                if (not decision.allowed or decision.domain != Domain.LOCAL_WORKSPACE
                        or decision.edition != Edition.PERSONAL or decision.deployment != Deployment.LOCAL
                        or decision.operation != Permission.WRITE_PERSONAL_APPROVALS
                        or Permission.WRITE_PERSONAL_APPROVALS not in decision.data_permissions):
                    return False
                decision = governance_decision(decision, owner)
                if context != BatchContext(
                    decision.scope.study_id, decision.scope.scope_id, decision.scope.scope_version,
                    decision.actor_ref, decision.owner_ref, decision.evidence_refs[0], decision.policy_version,
                ):
                    return False
                if grant is None:
                    return True
                at = datetime.now(UTC)
                if source is None or not source.current(at) or grant["source_ref"] != source.ref:
                    return False
                source_sha = digest(source.url)
                if grant["source_sha256"] != source_sha or not _active_material(
                    self.ledger, db, context, "source:" + source.ref, digest(asdict(source))
                ):
                    return False
                if grant["operation"] != operation or grant["payload_sha256"] != digest(payload):
                    return False
                if not _active_material(self.ledger, db, context, "risk:" + grant["provider"],
                                        grant["material_revision"]):
                    return False
                if not _active_material(
                    self.ledger, db, context, f"limits:{grant['operation']}:{grant['slot']}",
                    digest({"payload": grant["payload_sha256"], "limits": asdict(estimate),
                            "provider": grant["provider"], "account": grant["account_ref"],
                            "channel": grant["channel_ref"], "credential": grant["credential_revision"]})
                ):
                    return False
                if operation != "search":
                    parent = db.execute(
                        """SELECT r.source_sha256, r.quote_sha256, g.question_version, g.approval_event_id,
                                  g.provider, g.material_revision, g.operation, g.account_ref,
                                  g.channel_ref, g.credential_revision, g.expires_at
                           FROM personal_validation_receipts r JOIN personal_validation_requests q USING(request_id)
                           JOIN personal_validation_grants g USING(grant_id) WHERE r.request_id=?""",
                        (grant["depends_on"],),
                    ).fetchone()
                    if (parent is None or parent["source_sha256"] != source_sha
                            or utc_timestamp(parent["expires_at"]) <= at
                            or not _active_material(self.ledger, db, context, "risk:" + parent["provider"],
                                                    parent["material_revision"])):
                        return False
                    validation_binding(self.store, db, context, dict(parent))
                if operation == "model":
                    if (grant["question_version"] != model_version
                            or (grant["slot"] == 2 and (parent["question_version"] != model_version
                                                      or parent["approval_event_id"] != grant["approval_event_id"]))
                            or digest(payload["state"]) != source.model_input_sha256
                            or parent["quote_sha256"] != source.model_input_sha256
                            or not _c_approval(self.store, db, decision, grant, at, estimate)):
                        return False
                secret[0] = validation_binding(self.store, db, context, grant)
                return True
            except (HTTPException, VaultError, Conflict, TypeError, ValueError, OSError):
                return False

        secret = [None]
        return check, secret

    def execute(self, batch_id, context, grant, *, source, estimate, authorize, owner,
                query=None, text=None, options=None):
        if self.transport is None or not isinstance(estimate, Budget):
            raise Conflict("VALIDATION_TRANSPORT_DISABLED")
        operation, slot = grant["operation"], grant["slot"]
        model_version = None
        if operation == "search":
            payload = search_payload(query)
        elif operation == "source":
            payload = {"url": source_identity(source.url), "site": "cooking", "filter": "withbody"}
        elif operation == "model":
            payloads = model_payloads(text, options)
            payload = payloads[slot - 1]
            model_version = question_version(payloads)
            if estimate.input_tokens == 0 or estimate.output_tokens == 0:
                raise ValueError("VALIDATION_MODEL_LIMITS_REQUIRED")
        else:
            raise ValueError("INVALID_VALIDATION_OPERATION")
        if operation == "search" and estimate.credits < 1:
            raise ValueError("VALIDATION_SEARCH_LIMITS_REQUIRED")
        check, secret = self.recheck(
            context, authorize, owner=owner, source=source, operation=operation, payload=payload, estimate=estimate,
            model_version=model_version,
        )
        request = self.ledger.reserve(batch_id, context, grant["grant_id"], slot, digest(payload), estimate, check)
        request_id = request["request_id"]
        if request["state"] != "reserved" or self.ledger.claim(request_id, context, check) is None:
            return {"request_id": request_id, "dispatched": False}
        def owns_claim(db, batch, bound_grant):
            return batch["batch_id"] == batch_id and bound_grant["grant_id"] == request["grant_id"]

        try:
            receipt = self._dispatch(operation, payload, source, secret[0], request_id)
        except Exception:
            self.ledger.mark_unknown(request_id, context, "transport_outcome_unknown", owns_claim)
            return {"request_id": request_id, "dispatched": True, "state": "reconciliation"}
        finally:
            secret[0] = None
        try:
            result = self.ledger.receipt(request_id, context, receipt, check)
        except (sqlite3.Error, OSError):
            self.ledger.mark_unknown(request_id, context, "receipt_commit_unknown", owns_claim)
            return {"request_id": request_id, "dispatched": True, "state": "reconciliation"}
        finally:
            secret[0] = None
        return {"request_id": request_id, "dispatched": True, "receipt": result}

    def _dispatch(self, operation, payload, source, secret, request_id):
        captured = []

        def send(method, url, body, headers):
            reply = self.transport(method, url, body, headers)
            if not isinstance(reply, FixtureReply):
                raise ValueError("INVALID_FIXTURE_REPLY")
            captured.append(reply)
            return reply.response

        labels = {"public_approved"}
        headers = {"Idempotency-Key": request_id}
        if secret is not None:
            headers["Authorization"] = "Bearer " + secret
        source_sha, quote_sha = None, None
        credits = input_tokens = output_tokens = total_tokens = None
        reason = "schema_gap"
        if operation == "source":
            _, _, citation = fetch_forum_post(
                post_id(payload["url"]), "tavily", secrets=(secret,),
                transport=lambda method, url, body, _: send(method, url, body, headers),
            )
            valid = (
                citation.get("verified") and _matches(citation["url"], source.url)
                and citation["license"] == source.license_name
            )
            if valid:
                source_sha = digest(source.url)
                quote_sha = digest(citation["text"])
        else:
            reply = outbound("tavily" if operation == "search" else "packycode", labels=labels,
                             method="POST", body=payload, headers=headers, transport=send)
            obj = reply.body if isinstance(reply.body, dict) else {}
            if operation == "search":
                results, usage = obj.get("results"), obj.get("usage")
                valid = isinstance(results, list) and any(
                    isinstance(hit, dict) and _matches(hit.get("url"), source.url) for hit in results[:5]
                )
                credits = number(usage.get("credits")) if isinstance(usage, dict) else None
                source_sha = digest(source.url) if valid else None
            else:
                identity, gaps = jev.validate(payload["questions"], obj)
                valid = identity and not gaps
                input_tokens, output_tokens = jev.input_tokens(obj), jev.output_tokens(obj)
                if input_tokens is not None and output_tokens is not None:
                    total_tokens = number(input_tokens + output_tokens)
                source_sha, quote_sha = digest(source.url), digest(payload["state"])
        result = captured[0]
        reply = result.response
        valid = bool(valid and reply.status == 200)
        if reply.status is None:
            reason = "transport_outcome_unknown"
        elif 300 <= reply.status < 400:
            reason = "redirect_blocked"
        elif valid:
            reason = "fixture_response_valid"
        return Receipt(
            digest(redact(reply.body, (secret,))), reply.status, result.evidence_ref, result.provider_request_id,
            model=MODEL if operation == "model" else "", credits=credits, input_tokens=input_tokens,
            output_tokens=output_tokens, total_tokens=total_tokens, actual_units=result.actual_units,
            valid=valid, reason=reason, source_sha256=source_sha, quote_sha256=quote_sha,
        )


def _matches(candidate, approved_url):
    try:
        return source_identity(candidate) == approved_url
    except ValueError:
        return False
