"""Local Personal approval evidence. Only the protected service registry attests material."""

from datetime import UTC, datetime
import json
from pathlib import Path
import re
import stat

from src.edition_policy import REFERENCE, utc_timestamp


REQUIRED_EVIDENCE = (
    "ACCOUNT_API_RIGHTS", "PROVIDER_TERMS", "SOURCE_RIGHTS",
    "DATA_PROTECTION", "BUDGET_CONTROL", "PROJECT_AUTHORIZATION",
)
OPTIONAL_RISKS = (
    "ENTERPRISE_DPA", "ZDR", "UPSTREAM_PROVIDERS", "PROCESSING_REGION",
    "PROCUREMENT", "MULTI_PARTY_APPROVAL",
)
EVIDENCE_STATES = {"VERIFIED", "UNKNOWN", "PROHIBITED", "REVOKED"}
REGISTRY_NAME = "personal-approval-registry.json"


def read_registry(directory, scope, purpose):
    path = Path(directory) / REGISTRY_NAME
    try:
        info = path.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if reparse or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return {}
        with path.open("rb") as stream:
            encoded = stream.read(262_145)
        if len(encoded) > 262_144:
            return {}
        records = json.loads(encoded)
        if not isinstance(records, list):
            return {}
        registry = {}
        for row in records:
            if not isinstance(row, dict):
                return {}
            if (row.get("study_id"), row.get("scope_id"), row.get("scope_version"), row.get("purpose")) != (
                scope.study_id, scope.scope_id, scope.scope_version, purpose,
            ):
                continue
            ref = row["evidence_ref"]
            if ref in registry or not REFERENCE.fullmatch(ref):
                return {}
            for field in ("provider", "channel_ref", "account_ref", "model", "terms_version", "credential_revision"):
                if not REFERENCE.fullmatch(row[field]):
                    return {}
            if (row["kind"] not in REQUIRED_EVIDENCE or row["status"] not in EVIDENCE_STATES
                    or not re.fullmatch("[0-9a-f]{64}", row["sha256"])):
                return {}
            verified = utc_timestamp(row["verified_at"])
            expires = utc_timestamp(row["expires_at"])
            if verified >= expires:
                return {}
            mandatory = row.get("mandatory_risks", [])
            if not isinstance(mandatory, list) or any(kind not in OPTIONAL_RISKS for kind in mandatory):
                return {}
            if row["kind"] == "BUDGET_CONTROL" and (
                row.get("budget_unit") != "TOKENS" or type(row.get("budget_limit")) is not int
                or not 0 < row["budget_limit"] < 2**63
            ):
                return {}
            registry[ref] = {
                **row, "verified_at": verified.isoformat(), "expires_at": expires.isoformat(),
                "mandatory_risks": mandatory,
            }
        return registry
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {}


def evidence_status(row, at):
    if row["status"] != "VERIFIED":
        return row["status"]
    if utc_timestamp(row["expires_at"]) <= at:
        return "EXPIRED"
    if utc_timestamp(row["verified_at"]) > at:
        return "UNKNOWN"
    return "VERIFIED"


def evidence_projection(registry, at=None):
    at = at or datetime.now(UTC)
    return [
        {key: row[key] for key in ("evidence_ref", "kind", "expires_at")}
        | {"status": evidence_status(row, at)}
        for row in registry.values()
    ]
