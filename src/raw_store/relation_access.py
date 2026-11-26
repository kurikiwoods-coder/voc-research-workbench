"""Trusted server-side authorization for C4 project projections and commands."""

from dataclasses import dataclass
from datetime import datetime

from src.raw_store.mentions import _reference


ROLE_OPERATIONS = {
    "owner": frozenset({"read", "evidence", "validate", "attribute", "registry_draft"}),
    "researcher": frozenset({"read", "evidence"}),
    "project_reviewer": frozenset({"read", "evidence", "validate", "attribute", "registry_draft"}),
    "registry_reviewer": frozenset({"read", "evidence", "validate", "publish_registry", "registry_draft"}),
    "governance_reviewer": frozenset({"read", "evidence", "audit"}),
    "report_reader": frozenset(),
}


@dataclass(frozen=True)
class RelationGrant:
    actor_ref: str
    role: str
    granted_by: str
    basis_ref: str
    starts_at: str
    expires_at: str
    operations: frozenset[str]
    study_id: str | None = None
    evidence_refs: frozenset[tuple[int, str, str]] | None = None
    revoked_at: str | None = None

    def active(self, at):
        try:
            for reference in (self.actor_ref, self.granted_by, self.basis_ref):
                _reference(reference)
            start, end = (datetime.fromisoformat(value) for value in (self.starts_at, self.expires_at))
            revoked = datetime.fromisoformat(self.revoked_at) if self.revoked_at else None
            return start <= at < end and (revoked is None or at < revoked)
        except (TypeError, ValueError):
            return False


class RelationAccess:
    def __init__(self, resolver, timestamp):
        self.at = datetime.fromisoformat(timestamp)
        grants = tuple(resolver()) if resolver is not None else ()
        self.grants = tuple(grant for grant in grants if isinstance(grant, RelationGrant) and grant.active(self.at))
        # A single request authenticates one principal, even when several roles apply.
        actors = {grant.actor_ref for grant in self.grants}
        self.actor = next(iter(actors)) if len(actors) == 1 else None

    def permits(self, operation, study_id, evidence=None, *, entire_project=False):
        if self.actor is None or (study_id is None) != (operation == "publish_registry"):
            return False
        for grant in self.grants:
            if (grant.study_id != study_id or operation not in grant.operations
                    or operation not in ROLE_OPERATIONS.get(grant.role, ())):
                continue
            if grant.evidence_refs is None:
                return True
            if not entire_project and (evidence is None or evidence in grant.evidence_refs):
                return True
        return False

    def require(self, operation, study_id, evidence=None):
        if not self.permits(operation, study_id, evidence):
            if operation in {"read", "evidence"}:
                raise KeyError(study_id)
            raise PermissionError("当前授权不允许执行该操作。")

    def require_revision(self, study_id, revision):
        if self.permits("read", study_id, entire_project=True):
            return
        if self.actor is not None:
            for grant in self.grants:
                if (grant.study_id == study_id and grant.evidence_refs and "read" in grant.operations
                        and "read" in ROLE_OPERATIONS.get(grant.role, ())
                        and any(reference[0] == revision for reference in grant.evidence_refs)):
                    return
        raise KeyError(study_id)

    def same_as(self, other, study_id):
        if self.actor != other.actor:
            return False
        relevant = {study_id, None}
        old = [grant for grant in self.grants if grant.study_id in relevant]
        return old == [grant for grant in other.grants if grant.study_id in relevant]
