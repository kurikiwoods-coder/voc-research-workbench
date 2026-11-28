"""Append-only Personal supplier approvals and current qualification projection."""

from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import uuid4

from src.edition_policy import REFERENCE, utc_timestamp
from src.raw_store.personal_approval_evidence import OPTIONAL_RISKS, REQUIRED_EVIDENCE, evidence_status
from src.raw_store.store import Conflict, dump


IDENTITY = ("provider", "channel_ref", "model", "account_ref", "credential_revision")
EVIDENCE_FIELDS = ("evidence_ref", "kind", "sha256", "terms_version", "verified_at", "expires_at")
RISK_FIELDS = {"kind", "reason", "impact", "safeguards", "responsible_ref", "expires_at", "review_basis"}
REQUEST_FIELDS = (set(IDENTITY) - {"credential_revision"}) | {
    "expires_at", "budget_unit", "budget_limit", "evidence_refs", "risks", "request_key",
}
EVENT_COLS = (
    "event_id", "kind", "prior_event_id", "edition", "study_id", "scope_id", "scope_version", "purpose",
    *IDENTITY, "policy_version", "actor_ref", "owner_ref", "authorization_ref", "effective_at", "expires_at",
    "budget_unit", "budget_limit", "risks", "request_sha256", "request_key", "evidence_count",
)


def reference(value):
    return isinstance(value, str) and bool(REFERENCE.fullmatch(value))


def request_value(body, kind):
    keys = REQUEST_FIELDS if kind == "submitted" else {"request_key"}
    if not isinstance(body, dict) or body.keys() != keys or not reference(body.get("request_key")):
        raise ValueError
    if kind != "submitted":
        return body
    if (body["provider"] != "packycode" or not all(reference(body[name]) for name in
            ("model", "account_ref", "channel_ref")) or body["budget_unit"] != "TOKENS"
            or type(body["budget_limit"]) is not int or not 0 < body["budget_limit"] < 2**63):
        raise ValueError
    refs = body["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 30 or not all(map(reference, refs)) or len(refs) != len(set(refs)):
        raise ValueError
    risks = body["risks"]
    if not isinstance(risks, list) or len(risks) > len(OPTIONAL_RISKS):
        raise ValueError
    unique = set()
    checked = []
    for risk in risks:
        if (not isinstance(risk, dict) or risk.keys() != RISK_FIELDS
                or risk["kind"] not in OPTIONAL_RISKS or risk["kind"] in unique
                or not reference(risk["responsible_ref"]) or not reference(risk["review_basis"])):
            raise ValueError
        if not all(isinstance(risk[name], str) and 0 < len(risk[name].strip()) <= 500
                   and risk[name].isprintable() for name in ("reason", "impact", "safeguards")):
            raise ValueError
        unique.add(risk["kind"])
        checked.append({**risk, "expires_at": utc_timestamp(risk["expires_at"]).isoformat()})
    return {**body, "expires_at": utc_timestamp(body["expires_at"]).isoformat(),
            "evidence_refs": sorted(refs), "risks": sorted(checked, key=lambda item: item["kind"])}


def current_evidence(event, refs, registry, at):
    selected = [registry[ref] for ref in refs if ref in registry]
    applicable = [row for row in registry.values()
                  if all(event[key] == row[key] for key in IDENTITY if key != "credential_revision")]
    if any(row["status"] == "PROHIBITED" for row in applicable):
        return [], ["PURPOSE_PROHIBITED"]
    if len(selected) != len(refs) or any(
        any(event[key] != row[key] for key in IDENTITY) or evidence_status(row, at) != "VERIFIED"
        or utc_timestamp(row["expires_at"]) < utc_timestamp(event["expires_at"]) for row in selected
    ):
        return [], ["EVIDENCE_NOT_CURRENT"]
    missing = set(REQUIRED_EVIDENCE) - {row["kind"] for row in selected}
    if missing:
        return selected, ["MISSING_" + kind for kind in sorted(missing)]
    if len({row["terms_version"] for row in selected}) != 1:
        return selected, ["TERMS_VERSION_MISMATCH"]
    if any(row["kind"] == "BUDGET_CONTROL" and (row["budget_limit"] < event["budget_limit"]
            or row["budget_unit"] != event["budget_unit"]) for row in selected):
        return selected, ["BUDGET_OUTSIDE_VERIFIED_LIMIT"]
    risks = json.loads(event["risks"])
    if any(row["mandatory_risks"] for row in applicable if evidence_status(row, at) == "VERIFIED"):
        return selected, ["MANDATORY_RISK_REQUIRES_EVIDENCE"]
    if any(risk["responsible_ref"] != event["owner_ref"] or
           not at < utc_timestamp(risk["expires_at"]) <= utc_timestamp(event["expires_at"]) for risk in risks):
        return selected, ["RISK_REVIEW_REQUIRED"]
    return selected, []


def saved_evidence(db, event_id):
    return [dict(row) for row in db.execute(
        "SELECT " + ", ".join(EVIDENCE_FIELDS) + " FROM personal_approval_evidence WHERE event_id=?",
        (event_id,),
    )]


def event_reasons(event, decision, credential, registry, evidence, at):
    if utc_timestamp(event["expires_at"]) <= at:
        return ["APPROVAL_EXPIRED"]
    if (event["policy_version"] != decision.policy_version or event["owner_ref"] != decision.owner_ref
            or event["actor_ref"] != decision.actor_ref
            or event["authorization_ref"] != decision.evidence_refs[0]):
        return ["AUTHORIZATION_CHANGED"]
    if not credential["configured"] or any(
        event[field] != credential[field] for field in IDENTITY if field != "model"
    ):
        return ["CREDENTIAL_CHANGED"]
    if len(evidence) != event["evidence_count"]:
        return ["EVIDENCE_SNAPSHOT_INCOMPLETE"]
    rows, reasons = current_evidence(event, [row["evidence_ref"] for row in evidence], registry, at)
    projected = {row["evidence_ref"]: tuple(row[key] for key in EVIDENCE_FIELDS) for row in rows}
    if not reasons and any(projected.get(row["evidence_ref"]) != tuple(row[key] for key in EVIDENCE_FIELDS)
                           for row in evidence):
        return ["EVIDENCE_CHANGED"]
    return reasons


def scope_args(decision):
    return (decision.scope.study_id, decision.scope.scope_id, decision.scope.scope_version, decision.purpose)


SCOPED = "study_id=? AND scope_id=? AND scope_version=? AND purpose=?"


def projection(db, event, decision, credential, registry, at):
    successor = db.execute(
        "SELECT kind FROM personal_provider_approval_events WHERE prior_event_id=?", (event["event_id"],),
    ).fetchone()
    reasons = []
    if event["kind"] == "revoked" or (successor and successor["kind"] == "revoked"):
        status = "REVOKED"
    elif successor:
        status = "SUPERSEDED"
    else:
        evidence = saved_evidence(db, event["event_id"])
        reasons = event_reasons(event, decision, credential, registry, evidence, at)
        if reasons == ["APPROVAL_EXPIRED"]:
            status = "EXPIRED"
        elif event["kind"] == "submitted":
            status = "PENDING"
        else:
            status = "INVALIDATED" if reasons else "ACTIVE"
    visible = ("event_id", "kind", "provider", "model", "channel_ref", "account_ref", "scope_id",
               "scope_version", "purpose", "effective_at", "expires_at", "budget_unit", "budget_limit")
    return {field: event[field] for field in visible} | {"status": status, "reasons": reasons}


def list_approvals(db, decision, credential, registry, at):
    return [
        projection(db, row, decision, credential, registry, at)
        for row in db.execute(
            "SELECT * FROM personal_provider_approval_events WHERE " + SCOPED +
            " ORDER BY effective_at DESC, rowid DESC",
            scope_args(decision),
        )
    ]


def write_event(db, decision, credential, registry, kind, parent_id, body, at):
    digest = sha256(dump([kind, parent_id, body]).encode("utf-8")).hexdigest()
    replay = db.execute(
        "SELECT * FROM personal_provider_approval_events WHERE " + SCOPED + " AND request_key=?",
        (*scope_args(decision), body["request_key"]),
    ).fetchone()
    if replay:
        if replay["request_sha256"] != digest or replay["owner_ref"] != decision.owner_ref:
            raise Conflict("IDEMPOTENCY_CONFLICT")
        return projection(db, replay, decision, credential, registry, at)

    if kind == "submitted":
        if utc_timestamp(body["expires_at"]) <= at:
            raise Conflict("APPROVAL_EXPIRED")
        if not credential["configured"] or any(
            body[field] != credential[field] for field in ("provider", "channel_ref", "account_ref")
        ):
            raise Conflict("CREDENTIAL_CHANGED")
        event = {**body, "credential_revision": credential["credential_revision"],
                 "risks": dump(body["risks"]), "prior_event_id": None}
        selected = [registry[ref] for ref in body["evidence_refs"] if ref in registry]
        if len(selected) != len(body["evidence_refs"]) or any(
            any(row[field] != event[field] for field in IDENTITY) for row in selected
        ):
            raise Conflict("EVIDENCE_NOT_CURRENT")
        if any(risk["responsible_ref"] != decision.owner_ref for risk in body["risks"]):
            raise Conflict("RISK_REVIEW_REQUIRED")
    else:
        parent = db.execute(
            "SELECT * FROM personal_provider_approval_events WHERE " + SCOPED + " AND event_id=?",
            (*scope_args(decision), parent_id),
        ).fetchone()
        if parent is None:
            raise KeyError
        if (parent["kind"] == "revoked" or kind == "approved" and parent["kind"] != "submitted"
                or db.execute("SELECT 1 FROM personal_provider_approval_events WHERE prior_event_id=?",
                              (parent_id,)).fetchone()):
            raise Conflict("EVENT_VERSION_CHANGED")
        event = dict(parent) | {"prior_event_id": parent_id}
        selected = saved_evidence(db, parent_id)
        if kind == "approved":
            reasons = event_reasons(parent, decision, credential, registry, selected, at)
            if reasons:
                raise Conflict(reasons[0])
            approved = db.execute(
                """SELECT * FROM personal_provider_approval_events WHERE """ + SCOPED + """
                   AND kind='approved' AND provider=? AND channel_ref=? AND model=? AND account_ref=?
                   AND NOT EXISTS (SELECT 1 FROM personal_provider_approval_events child
                                   WHERE child.prior_event_id=personal_provider_approval_events.event_id)""",
                (*scope_args(decision), *(event[field] for field in IDENTITY if field != "credential_revision")),
            )
            if approved.fetchone() is not None:
                raise Conflict("REVOKE_PRIOR_APPROVAL_FIRST")
    event.update(zip(("study_id", "scope_id", "scope_version", "purpose"), scope_args(decision)))
    event.update(event_id=str(uuid4()), kind=kind, edition=decision.edition,
                 policy_version=decision.policy_version, actor_ref=decision.actor_ref, owner_ref=decision.owner_ref,
                 authorization_ref=decision.evidence_refs[0], effective_at=at.isoformat(),
                 request_key=body["request_key"], request_sha256=digest, evidence_count=len(selected))
    db.execute(
        "INSERT INTO personal_provider_approval_events (" + ", ".join(EVENT_COLS) +
        ") VALUES (" + ", ".join("?" for _ in EVENT_COLS) + ")",
        tuple(event[key] for key in EVENT_COLS),
    )
    db.executemany(
        "INSERT INTO personal_approval_evidence (event_id, " + ", ".join(EVIDENCE_FIELDS) +
        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(event["event_id"], *(row[key] for key in EVIDENCE_FIELDS)) for row in selected],
    )
    return projection(db, event, decision, credential, registry, at)
