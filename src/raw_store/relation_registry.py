"""Registry snapshot preparation for the C4 combination transaction."""

from dataclasses import asdict, dataclass
import re

from src.raw_store.mentions import _insert, _reference
from src.raw_store.store import Conflict


@dataclass(frozen=True)
class TaskDefinition:
    category_id: str
    name: str
    definition: str
    inclusion_criteria: str
    exclusion_criteria: str
    discovery: str = "preset"
    lifecycle_status: str = "confirmed"
    version: str = "1.0.0"


@dataclass(frozen=True)
class IntentDefinition:
    intent_id: str
    name: str
    definition: str
    inclusion_criteria: str
    exclusion_criteria: str
    lifecycle_status: str = "confirmed"
    survey_validation_status: str = "unvalidated"
    version: str = "1.0.0"


@dataclass(frozen=True)
class PublishedProductRef:
    catalog_version: str
    product_category_id: str


def registry_version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?", value,
    ):
        raise ValueError("请输入有效的注册表版本。")
    return value


def registry_head(db):
    row = db.execute("SELECT registry_version FROM m06_registry_head").fetchone()
    return row[0] if row is not None else None


def validate_definitions(intent, tasks):
    intent_states = {"candidate", "pending_parent", "confirmed", "rejected", "merged", "retired"}
    if intent.lifecycle_status not in intent_states:
        raise ValueError("意图状态无效。")
    if intent.survey_validation_status not in {"unvalidated", "validating", "validated", "failed"}:
        raise ValueError("问卷验证状态无效。")
    _reference(intent.intent_id)
    seen = set()
    for task in tasks:
        _reference(task.category_id)
        if task.category_id in seen or task.lifecycle_status not in intent_states - {"pending_parent"}:
            raise ValueError("任务标识重复或状态无效。")
        if task.discovery not in {"preset", "discovered"}:
            raise ValueError("任务发现方式无效。")
        seen.add(task.category_id)
    for definition in (intent, *tasks):
        registry_version(definition.version)
        for value in (definition.name, definition.definition, definition.inclusion_criteria, definition.exclusion_criteria):
            if not isinstance(value, str) or len(value) > 4000:
                raise ValueError("共享定义字段无效。")
        if not definition.name.strip() or not definition.definition.strip():
            raise ValueError("请输入共享名称及定义。")


def parent_violations(db, version, primary, secondaries, *, confirm, tasks=()):
    violations = []
    if primary is None and confirm:
        violations.append("PRIMARY_REQUIRED")
    categories = ((*secondaries, primary) if primary is not None else secondaries)
    if len(set(categories)) != len(categories):
        violations.append("TASK_EDGE_DUPLICATE")
    current = {task.category_id: task.lifecycle_status for task in tasks}
    for category in categories:
        _reference(category)
        state = current.get(category)
        if state is None:
            row = db.execute(
                "SELECT lifecycle_status FROM m06_task WHERE registry_version=? AND category_id=?", (version, category),
            ).fetchone()
            state = row[0] if row is not None else None
        if state != "confirmed":
            violations.append("TASK_NOT_CONFIRMED")
            break
    return violations


def inherited_representatives(db, parent, study_id, intent_id):
    rows = db.execute(
        """SELECT intent_id, study_id, segment_revision, mention_id, evidence_id FROM m06_representative
           WHERE registry_version=? AND intent_id<>? ORDER BY intent_id, segment_revision, mention_id, evidence_id""",
        (parent, intent_id),
    ).fetchall()
    if any(row["study_id"] != study_id for row in rows):
        raise Conflict("该发行包含其他授权范围，须通过联合审核。")
    return rows


def stage_registry(db, version, parent, command_id, timestamp, intent, tasks, primary, secondaries,
                   inherited_refs, new_refs, study_id, revision):
    _insert(db, "m06_registry", registry_version=version, parent_version=parent,
            created_at=timestamp, command_id=command_id)
    db.execute(
        """INSERT INTO m06_product
           SELECT ?, product_category_id, name, description, parent_id, status, version
           FROM m06_product WHERE registry_version=?""", (version, parent),
    )
    pending_tasks = {task.category_id: task for task in tasks}
    for row in db.execute("SELECT * FROM m06_task WHERE registry_version=? ORDER BY category_id", (parent,)):
        changed = pending_tasks.pop(row["category_id"], None)
        values = asdict(changed) if changed is not None else dict(row)
        _insert(db, "m06_task", **(values | {"registry_version": version}))
    for task in pending_tasks.values():
        _insert(db, "m06_task", registry_version=version, **asdict(task))
    db.execute(
        """INSERT INTO m06_intent
           SELECT ?, intent_id, name, definition, inclusion_criteria, exclusion_criteria, lifecycle_status,
                  primary_category_id, primary_marker, survey_validation_status, version
           FROM m06_intent WHERE registry_version=? AND intent_id<>?""",
        (version, parent, intent.intent_id),
    )
    _insert(db, "m06_intent", registry_version=version, primary_category_id=primary, **asdict(intent))
    db.execute(
        """INSERT INTO m06_intent_task
           SELECT ?, intent_id, category_id, is_primary, task_status
           FROM m06_intent_task WHERE registry_version=? AND intent_id<>?""",
        (version, parent, intent.intent_id),
    )
    for category in (*secondaries, *((primary,) if primary is not None else ())):
        _insert(db, "m06_intent_task", registry_version=version, intent_id=intent.intent_id,
                category_id=category, is_primary=int(category == primary))
    for row in inherited_refs:
        _insert(db, "m06_representative", registry_version=version, **dict(row))
    for mention_id, evidence_id in new_refs:
        _insert(db, "m06_representative", registry_version=version, intent_id=intent.intent_id,
                study_id=study_id, segment_revision=revision, mention_id=mention_id, evidence_id=evidence_id)


def protect_published_products(db, version, references):
    for reference in references:
        # The publisher supplies only references backed by an active release.
        if db.execute(
            "SELECT 1 FROM m06_registry WHERE registry_version=? AND sealed=1", (reference.catalog_version,),
        ).fetchone() is None:
            raise Conflict("已发布引用需要已封存的目录版。")
        previous = reference.product_category_id
        visited = set()
        while previous is not None:
            if previous in visited:
                raise Conflict("已发布目录的祖先链无法核对。")
            visited.add(previous)
            historical, proposed = (
                db.execute(
                    """SELECT parent_id, status FROM m06_product
                       WHERE registry_version=? AND product_category_id=?""",
                    (catalog, previous),
                ).fetchone() for catalog in (reference.catalog_version, version)
            )
            if historical is None or proposed is None or historical["status"] != "confirmed" \
                    or proposed["status"] != "confirmed" or historical["parent_id"] != proposed["parent_id"]:
                raise Conflict("已发布引用的品类或祖先需要有效替代审核。")
            previous = historical["parent_id"]
