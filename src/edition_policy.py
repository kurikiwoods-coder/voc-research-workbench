"""Service-owned edition, principal and scope decisions for the B phase."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest
from uuid import UUID
import json
import re


POLICY_VERSION = "EDITION-V1/G-1-P-B.1"
REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}")
SCOPE_VERSION = re.compile(r"v[1-9][0-9]{0,12}")
PROOF = re.compile(r"[A-Za-z0-9_-]{43}|[0-9a-f]{64}")
PERSONAL_GATE_REASON = "个人正式准入尚未评价，等待个人审批及同批验收。"
CLOUD_REASON = "当前版本的云端特权与研究操作尚未获准。"


class Edition(StrEnum):
    PERSONAL = "PERSONAL"
    BUSINESS = "BUSINESS"


class Deployment(StrEnum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class Domain(StrEnum):
    LOCAL_WORKSPACE = "local_workspace"
    ENGINEERING = "engineering_synthetic"
    PERSONAL_VALIDATION = "personal_pre_admission"
    PERSONAL_RESEARCH = "personal_formal_research"
    BUSINESS_RESEARCH = "business_formal_research"


class Permission(StrEnum):
    READ_SCOPE = "read_scope"
    IMPORT_LOCAL = "import_local"
    EXPORT_ISSUES = "export_import_issues"
    READ_CORPUS = "read_corpus"
    REVIEW_CORPUS = "review_corpus"
    READ_FORMAL_STATUS = "read_formal_status"
    READ_PERSONAL_APPROVALS = "read_personal_approvals"
    WRITE_PERSONAL_APPROVALS = "write_personal_approvals"
    MANAGE_PERSONAL_CREDENTIALS = "manage_personal_credentials"


@dataclass(frozen=True)
class Scope:
    study_id: str
    scope_id: str
    scope_version: str


def canonical_uuid(value):
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        return None


def utc_timestamp(value):
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError
    return timestamp.astimezone(UTC)


@dataclass(frozen=True)
class Grant:
    scope: Scope
    purpose: str
    permissions: frozenset[Permission]
    evidence_ref: str
    starts_at: datetime
    expires_at: datetime

    @classmethod
    def parse(cls, data):
        keys = {"study_id", "scope_id", "scope_version", "purpose", "permissions", "evidence_ref",
                "starts_at", "expires_at"}
        if not isinstance(data, dict) or data.keys() != keys:
            raise ValueError
        study = canonical_uuid(data["study_id"])
        scope = canonical_uuid(data["scope_id"])
        version = data["scope_version"]
        if not study or not scope or not SCOPE_VERSION.fullmatch(version):
            raise ValueError
        purpose = data["purpose"]
        evidence = data["evidence_ref"]
        if purpose != "personal_research" or not REFERENCE.fullmatch(evidence):
            raise ValueError
        operations = data["permissions"]
        if not isinstance(operations, list) or not operations:
            raise ValueError
        permissions = frozenset(Permission(value) for value in operations)
        start, end = (utc_timestamp(data[key]) for key in ("starts_at", "expires_at"))
        if start >= end:
            raise ValueError
        return cls(Scope(study, scope, version), purpose, permissions, evidence, start, end)

    def active(self, at):
        return self.starts_at <= at < self.expires_at


@dataclass(frozen=True)
class LocalOwner:
    actor_ref: str
    owner_ref: str
    proof_sha256: str = field(repr=False)
    grants: tuple[Grant, ...] = ()

    @classmethod
    def from_environment(cls, environment):
        try:
            actor = environment["VOC_PERSONAL_OPERATOR_REF"]
            owner = environment["VOC_PERSONAL_OWNER_REF"]
            verifier = environment["VOC_PERSONAL_OWNER_SHA256"]
            records = environment.get("VOC_PERSONAL_PROJECT_GRANTS", "[]")
            if (not REFERENCE.fullmatch(actor) or not REFERENCE.fullmatch(owner)
                    or not re.fullmatch("[0-9a-f]{64}", verifier) or len(records) > 60_000):
                raise ValueError
            grants = json.loads(records)
            if not isinstance(grants, list):
                raise ValueError
            rules = tuple(Grant.parse(record) for record in grants)
            if len({rule.scope.study_id for rule in rules}) != len(rules):
                raise ValueError
            return cls(actor, owner, verifier, rules)
        except (KeyError, TypeError, ValueError, RecursionError):
            raise ValueError("个人版启动需要有效的本机 Owner 配置与项目授权。") from None

    def authenticates(self, proof):
        return bool(PROOF.fullmatch(proof)) and compare_digest(
            self.proof_sha256, sha256(proof.encode("ascii")).hexdigest(),
        )


@dataclass(frozen=True)
class Decision:
    edition: Edition
    deployment: Deployment
    domain: Domain
    operation: str
    gate: str
    gate_status: str
    allowed: bool
    reason: str
    actor_ref: str | None = None
    owner_ref: str | None = None
    scope: Scope | None = None
    purpose: str | None = None
    data_permissions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    policy_version: str = POLICY_VERSION


@dataclass(frozen=True)
class EditionPolicy:
    edition: Edition
    deployment: Deployment
    owner: LocalOwner | None = field(default=None, repr=False)

    def decide(self, operation, domain, *, proof="", study_id=None, current_scope=None, at=None,
               business_status="BLOCKED"):
        """Recreate decisions at the action boundary from the trusted service context."""
        local = self.deployment == Deployment.LOCAL
        personal = self.edition == Edition.PERSONAL
        decision = dict(
            edition=self.edition, deployment=self.deployment, domain=domain, operation=operation,
            gate="G-1-PERSONAL" if personal else "G-1",
            gate_status="NOT_EVALUATED" if personal else business_status,
        )
        if not local:
            return Decision(**decision, allowed=False, reason="CLOUD_NOT_APPROVED")
        if not personal:
            # Only the existing Business entry points can apply their original authorization.
            return Decision(**decision, allowed=False, reason="BUSINESS_LEGACY_AUTHORIZATION_REQUIRED")
        if self.owner is None or not self.owner.authenticates(proof):
            return Decision(**decision, allowed=False, reason="OWNER_AUTHENTICATION_REQUIRED")
        identity = dict(actor_ref=self.owner.actor_ref, owner_ref=self.owner.owner_ref)
        now = at if at is not None else datetime.now(UTC)
        match = next((rule for rule in self.owner.grants
                      if rule.scope.study_id == study_id and rule.active(now)), None)
        if match is None or current_scope is None or not current_scope(match.scope):
            return Decision(**decision, **identity, allowed=False, reason="PROJECT_SCOPE_NOT_AUTHORIZED")
        decision.update(
            **identity, scope=match.scope, purpose=match.purpose, evidence_refs=(match.evidence_ref,),
            data_permissions=tuple(sorted(match.permissions)),
        )
        if domain != Domain.LOCAL_WORKSPACE:
            return Decision(**decision, allowed=False, reason="PERSONAL_GATE_NOT_EVALUATED")
        if operation not in match.permissions or (
            operation == Permission.REVIEW_CORPUS and Permission.READ_CORPUS not in match.permissions
        ):
            return Decision(**decision, allowed=False, reason="OPERATION_NOT_AUTHORIZED")
        return Decision(**decision, allowed=True, reason="PROJECT_SCOPE_AUTHORIZED")

    def status(self, business_status="BLOCKED"):
        legacy = self.edition == Edition.BUSINESS and self.deployment == Deployment.LOCAL
        return {
            "edition": self.edition, "deployment": self.deployment, "policy_version": POLICY_VERSION,
            "gates": {"personal": {"id": "G-1-PERSONAL", "status": "NOT_EVALUATED"},
                      "business": {"id": "G-1", "status": business_status if legacy else "BLOCKED",
                                   "applies_here": legacy}},
            "workspace": "BUSINESS_LOCAL" if legacy else "SCOPED_LOCAL" if
                self.deployment == Deployment.LOCAL else "STATUS_ONLY",
            "operations": {
                "scoped_local_workspace": self.edition == Edition.PERSONAL and self.deployment == Deployment.LOCAL,
                "personal_approval": False, "personal_pre_admission": False, "personal_formal_research": False,
                "business_formal_research": legacy and business_status == "PASS",
                "legacy_connectivity": legacy,
            },
            "reason": CLOUD_REASON if self.deployment == Deployment.CLOUD else
                PERSONAL_GATE_REASON if self.edition == Edition.PERSONAL else
                None if business_status == "PASS" else "商用 G-1 仍需同批六项及当前账户审核。",
        }


def legacy_execution_allowed(settings=None, *, environment=None):
    if environment is not None and (
        environment.get("VOC_EDITION", Edition.BUSINESS) != Edition.BUSINESS
        or environment.get("VOC_DEPLOYMENT", Deployment.LOCAL) != Deployment.LOCAL
    ):
        return False
    return settings is None or (settings.edition == Edition.BUSINESS and settings.deployment == Deployment.LOCAL)
