"""Product proposals and human review checks on the caller's SQLite connection."""

from dataclasses import dataclass
import json
import re
from typing import TYPE_CHECKING
from unicodedata import normalize

from src.raw_store.store import Conflict, dump

if TYPE_CHECKING:
    from src.raw_store.mention_segments import EvidenceInterval


RELATIONS = frozenset({
    "explicit", "ambiguous", "comparison", "negated", "negation", "conflict",
    "conflicting", "pronoun", "unresolved_reference", "indirect",
})
HUMAN_DECISIONS = frozenset({"human_confirmed", "suspended", "withdrawn"})


@dataclass(frozen=True)
class ProductProposal:
    member_ref: str
    interval: "EvidenceInterval"
    mapping_revision: int
    catalog_version: str
    product_category_id: str
    basis_ref: str
    rule_version: str
    relation: str = "explicit"


@dataclass(frozen=True)
class ReviewDecision:
    mention_id: str
    evidence_id: str
    mapping_revision: int
    catalog_version: str
    product_category_id: str
    expected_sequence: int
    decision: str
    basis_ref: str
    relation: str = "explicit"


def scope_mapping(db, study_id, scope_id, mapping_revision=None, catalog_version=None):
    """Resolve an immutable scope mapping by revision or return the current one."""
    if mapping_revision is not None and (type(mapping_revision) is not int or mapping_revision < 1):
        raise ValueError("冻结范围映射版号须为正整数。")
    scope = db.execute(
        """SELECT scopes.version_no FROM study_scope_freezes freeze
           JOIN study_scopes scopes USING (study_id, scope_id)
           WHERE freeze.study_id=? AND freeze.scope_id=?""",
        (study_id, scope_id),
    ).fetchone()
    if scope is None:
        raise KeyError(scope_id)
    binding = db.execute(
        """SELECT mapping_revision, registry_version, mapping_status FROM m06_scope_binding
           WHERE study_id=? AND scope_id=? AND (? IS NULL OR mapping_revision=?)
           ORDER BY mapping_revision DESC LIMIT 1""",
        (study_id, scope_id, mapping_revision, mapping_revision),
    ).fetchone()
    result = {
        "study_id": study_id, "scope_id": scope_id, "scope_version": f"v{scope['version_no']}",
        "mapping_revision": None, "catalog_version": None, "mapping_status": "unresolved",
        "product_category_ids": [],
    }
    if binding is None:
        if mapping_revision is not None or catalog_version is not None:
            raise Conflict("指定的冻结范围映射不存在。")
        return result
    revision, version, status = binding
    if catalog_version is not None and catalog_version != version:
        raise Conflict("冻结范围映射与指定目录版不一致。")
    products = db.execute(
        """SELECT product_category_id FROM m06_scope_product
           WHERE study_id=? AND scope_id=? AND mapping_revision=? AND registry_version=?
           ORDER BY product_category_id""",
        (study_id, scope_id, revision, version),
    )
    return {
        **result, "mapping_revision": revision, "catalog_version": version, "mapping_status": status,
        "product_category_ids": [row["product_category_id"] for row in products],
    }


def _bound_product(db, study_id, scope_id, entry):
    if type(entry.mapping_revision) is not int or entry.mapping_revision < 1:
        raise ValueError("产品关系需要明确的冻结范围映射版。")
    for value in (entry.catalog_version, entry.product_category_id, entry.basis_ref):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("产品关系需要目录版、稳定产品 ID 与依据引用。")
    if not isinstance(entry.relation, str) or entry.relation not in RELATIONS:
        raise ValueError("产品关系类型无效。")
    mapping = scope_mapping(db, study_id, scope_id, entry.mapping_revision, entry.catalog_version)
    if mapping["mapping_status"] != "mapped_product" or entry.product_category_id not in mapping["product_category_ids"]:
        raise Conflict("该产品 ID 未绑定到指定冻结范围映射及目录版。")
    product = db.execute(
        """SELECT name FROM m06_product
           WHERE registry_version=? AND product_category_id=? AND status='confirmed'""",
        (entry.catalog_version, entry.product_category_id),
    ).fetchone()
    if product is None:
        raise Conflict("指定目录版没有已确认的产品。")
    return product["name"]


def _direct_reference(excerpt, term):
    text = normalize("NFC", excerpt).casefold()
    label = normalize("NFC", term).casefold().strip()
    if not label:
        return False
    if label.isascii():
        return re.search(rf"(?<![a-z0-9_]){re.escape(label)}(?![a-z0-9_])", text) is not None
    return label in text


def _unambiguous_name(db, study_id, scope_id, proposal, name):
    labels = db.execute(
        """SELECT product.name FROM m06_scope_product scoped
           JOIN m06_product product USING (registry_version, product_category_id)
           WHERE scoped.study_id=? AND scoped.scope_id=? AND scoped.mapping_revision=?
                 AND scoped.registry_version=?""",
        (study_id, scope_id, proposal.mapping_revision, proposal.catalog_version),
    )
    label = normalize("NFC", name).casefold().strip()
    return sum(normalize("NFC", row["name"]).casefold().strip() == label for row in labels) == 1


def prepare_product_proposal(db, study_id, scope_id, proposal, *, mention_id, evidence_id, excerpt):
    """Return the immutable edge and its initial mode A review values."""
    name = _bound_product(db, study_id, scope_id, proposal)
    if not isinstance(proposal.rule_version, str) or not proposal.rule_version.strip():
        raise ValueError("产品提议需要确切规则版。")
    if not isinstance(excerpt, str) or not excerpt.strip():
        raise ValueError("产品提议需要当前可核的原话区间。")
    direct = _direct_reference(excerpt, proposal.product_category_id) or (
        _direct_reference(excerpt, name) and _unambiguous_name(db, study_id, scope_id, proposal, name)
    )
    return {
        "mention_id": mention_id, "evidence_id": evidence_id,
        "catalog_version": proposal.catalog_version, "product_category_id": proposal.product_category_id,
        "link_type": proposal.relation, "decision_seq": 1,
        "decision": "proposed" if proposal.relation == "explicit" and direct else "queued",
        "basis_ref": proposal.basis_ref, "mode": "A",
        "proposal_provenance": dump({
            "scope_id": scope_id, "mapping_revision": proposal.mapping_revision,
            "catalog_version": proposal.catalog_version, "rule_version": proposal.rule_version,
            "relation": proposal.relation,
        }),
    }


def prepare_product_review(db, study_id, segment_revision, review, *, excerpt, actor_ref, grants):
    """Check a human decision against the immutable edge and current event."""
    if type(review.expected_sequence) is not int or review.expected_sequence < 1:
        raise ValueError("产品审核需要当前决定版号。")
    if not isinstance(actor_ref, str) or not actor_ref.strip():
        raise ValueError("产品审核需要可信操作者。")
    if not isinstance(review.decision, str) or review.decision not in HUMAN_DECISIONS:
        raise ValueError("产品审核决定无效。")
    confirming = review.decision == "human_confirmed"
    if confirming:
        if review.relation != "explicit" or not isinstance(excerpt, str) or not excerpt.strip():
            raise Conflict("人工确认需要明确指称及当前可核的原话区间。")
        if not isinstance(grants, dict) or review.evidence_id not in grants or any(
            type(grant) is not int or grant < 1 for grant in grants.values()
        ):
            raise Conflict("人工确认需要全部依赖证据当前的 M05 审核版。")

    key = (study_id, segment_revision, review.mention_id, review.evidence_id,
           review.catalog_version, review.product_category_id)
    edge = db.execute(
        """SELECT edge.link_type, evidence.record_id, evidence.scope_id,
                  review.decision_seq, review.decision, review.mode, review.proposal_provenance
           FROM m06_mention_product edge
           JOIN m06_segment_rev segment USING (study_id, segment_revision)
           JOIN m06_evidence evidence USING (study_id, evidence_id)
           JOIN m06_product_review review USING (
               study_id, segment_revision, mention_id, evidence_id, catalog_version, product_category_id
           )
           WHERE edge.study_id=? AND edge.segment_revision=? AND edge.mention_id=?
                 AND edge.evidence_id=? AND edge.catalog_version=? AND edge.product_category_id=?
                 AND segment.sealed=1
           ORDER BY review.decision_seq DESC LIMIT 1""",
        key,
    ).fetchone()
    if edge is None:
        raise KeyError(review.evidence_id)
    if edge["decision_seq"] != review.expected_sequence:
        raise Conflict("产品审核决定版已变化。")
    if edge["mode"] != "A":
        raise Conflict("当前仅启用 A 模式产品审核。")
    provenance = json.loads(edge["proposal_provenance"])
    if not isinstance(provenance, dict) or (
        provenance.get("scope_id"), provenance.get("mapping_revision"), provenance.get("catalog_version")
    ) != (edge["scope_id"], review.mapping_revision, review.catalog_version):
        raise Conflict("审核范围映射与原产品提议不一致。")
    same_decision = edge["decision"] == review.decision
    grants_changed = provenance.get("grants") != grants
    if (same_decision and not (confirming and grants_changed)) or (edge["decision"] == "withdrawn" and not confirming):
        raise Conflict("当前产品决定不能执行此状态变更。")
    _bound_product(db, study_id, edge["scope_id"], review)
    provenance["review_relation"] = review.relation
    if confirming:
        provenance["grants"] = grants
    return {
        "mention_id": review.mention_id, "evidence_id": review.evidence_id,
        "catalog_version": review.catalog_version, "product_category_id": review.product_category_id,
        "link_type": edge["link_type"], "record_id": edge["record_id"], "scope_id": edge["scope_id"],
        "decision_seq": review.expected_sequence + 1, "decision": review.decision,
        "basis_ref": review.basis_ref, "mode": "A",
        "proposal_provenance": dump(provenance),
    }
