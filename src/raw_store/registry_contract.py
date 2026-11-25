"""Shared M07 field rules and legacy candidate compatibility."""

from datetime import date
import re

from src.raw_store.relation_registry import registry_version


DEFINITION_FIELDS = ("name", "definition", "inclusion_criteria", "exclusion_criteria")
SURVEY_STATES = ("unvalidated", "validating", "validated", "failed")
IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


def identifier(value):
    if not isinstance(value, str) or re.fullmatch(IDENTIFIER, value) is None:
        raise ValueError("请使用有效的注册表标识。")
    return value


def definition_fields(values):
    result = {}
    for key in DEFINITION_FIELDS:
        value = values.get(key, "")
        if not isinstance(value, str) or len(value) > 4000:
            raise ValueError("定义字段格式或长度无效。")
        result[key] = value.strip()
    return result


def missing_definition(definition):
    return [field.upper() + "_REQUIRED" for field in DEFINITION_FIELDS if not definition[field]]


def legacy_candidates(document):
    """Import definitions into a candidate view without importing source material."""
    version = registry_version(document["registry_version"])
    candidates = []
    seen = set()
    for row in document["intents"]:
        intent = identifier(row["intent_id"])
        if intent in seen:
            raise ValueError("旧注册表意图标识重复。")
        seen.add(intent)
        primary = row.get("primary_category_id")
        categories = tuple(identifier(value) for value in row.get("category_ids", ()))
        if len(categories) != len(set(categories)):
            raise ValueError("旧注册表任务边重复。")
        if primary is not None and identifier(primary) not in categories:
            raise ValueError("旧注册表主任务边缺失。")
        entity_version = row["version"]
        if re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", entity_version):
            entity_version += ".0"
        first_seen = row.get("first_discovered_at")
        candidates.append({
            "intent_id": intent, "registry_version": version,
            "entity_version": registry_version(entity_version), **definition_fields(row),
            "lifecycle_status": "candidate" if primary else "pending_parent",
            "survey_validation_status": "unvalidated", "primary_category_id": primary,
            "category_ids": list(categories), "category_assignments": [
                {"category_id": category, "role": "primary" if category == primary else "secondary"}
                for category in categories
            ],
            "first_discovered_at": date.fromisoformat(first_seen).isoformat() if first_seen else None,
            "approved_shared_examples": [], "change_log": [],
        })
    return candidates
