"""Versioned candidate review over the currently eligible M09 topic snapshot."""

from collections import defaultdict
from itertools import combinations

from src.discovery.topic_store import CANDIDATE_DECISIONS, CANDIDATE_OUTPUT_VERSION
from src.edition_policy import REFERENCE
from src.raw_store.store import Conflict


def _validate_revision(revision):
    if type(revision) is not int or not 0 <= revision < 2**63 - 1:
        raise ValueError("m09_invalid_candidate_revision")


def _candidate_rows(run, reviews):
    documents = defaultdict(list)
    for member in run["members"]:
        if member["evidence_eligible"]:
            documents[member["topic_id"]].append(member["document_id"])
    latest_review = {review["topic_id"]: review for review in reviews}

    candidates = []
    for topic in run["topics"]:
        topic_id = topic["topic_id"]
        if topic_id == -1:
            continue
        eligible = topic["evidence_eligible"]
        terms = [keyword["term"] for keyword in topic["keywords"]]
        review = latest_review.get(topic_id, {})
        candidates.append({
            "candidate_id": f"{run['run_id']}:{topic_id}",
            "topic_id": topic_id,
            "description": " / ".join(terms[:3]) or None,
            "keywords": topic["keywords"],
            "representative_document_ids": topic["representative_document_ids"],
            "member_document_ids": documents[topic_id] if eligible else [],
            "member_count": topic["member_count"],
            "evidence_eligible": eligible,
            "decision": review.get("decision", "pending"),
            "decision_revision": review.get("revision", 0),
            "decision_actor_ref": review.get("actor_ref"),
            "decided_at": review.get("decided_at"),
        })
    return candidates


def _coverage(run, candidates):
    supported = [
        candidate for candidate in candidates
        if candidate["evidence_eligible"] and candidate["decision"] != "rejected"
    ]
    return {
        "input_count": len(run["members"]),
        "eligible_count": sum(member["evidence_eligible"] for member in run["members"]),
        "candidate_count": len(supported),
        "candidate_document_count": sum(candidate["member_count"] for candidate in supported),
        "outlier_count": sum(member["topic_id"] == -1 for member in run["members"]),
        "rejected_candidate_count": sum(candidate["decision"] == "rejected" for candidate in candidates),
        "restricted_candidate_count": sum(not candidate["evidence_eligible"] for candidate in candidates),
    }


def _relationships(candidates):
    """Show shared snapshot keywords and their Jaccard similarity."""
    by_term = defaultdict(list)
    term_counts = {}
    for candidate in candidates:
        topic = candidate["topic_id"]
        terms = {keyword["term"] for keyword in candidate["keywords"]}
        term_counts[topic] = len(terms)
        for term in terms:
            by_term[term].append(topic)
    shared_terms = defaultdict(list)
    for term, topics in sorted(by_term.items()):
        for pair in combinations(topics, 2):
            shared_terms[pair].append(term)
    return [
        {
            "left_topic_id": left,
            "right_topic_id": right,
            "shared_terms": terms,
            "similarity": len(terms) / (term_counts[left] + term_counts[right] - len(terms)),
        }
        for (left, right), terms in sorted(shared_terms.items())
    ]


class TopicCandidates:
    """Read-only topic projections with append-only candidate review decisions."""

    def __init__(self, runs):
        self.runs = runs
        self._store = runs._store

    def get(self, run_id, *, revision=None):
        if revision is not None:
            _validate_revision(revision)
        run = self.runs.get(run_id)
        output_version, latest, selected, reviews = self._store.candidate_reviews(run_id, revision)
        if output_version != CANDIDATE_OUTPUT_VERSION:
            raise Conflict("m09_candidate_output_version_unsupported")
        candidates = _candidate_rows(run, reviews)
        return {
            "run": run,
            "output_version": output_version,
            "revision": selected,
            "latest_revision": latest,
            "candidates": candidates,
            "coverage": _coverage(run, candidates),
            "topic_relationships": _relationships(candidates),
        }

    def review(self, run_id, topic_id, *, decision, expected_revision, request_id, actor_ref):
        _validate_revision(expected_revision)
        if type(topic_id) is not int or topic_id < 0:
            raise ValueError("m09_invalid_candidate_topic")
        if not isinstance(decision, str) or decision not in CANDIDATE_DECISIONS:
            raise ValueError("m09_invalid_candidate_decision")
        if not isinstance(request_id, str) or not REFERENCE.fullmatch(request_id):
            raise ValueError("m09_invalid_request_id")
        if not isinstance(actor_ref, str) or not REFERENCE.fullmatch(actor_ref):
            raise ValueError("m09_invalid_candidate_actor")

        view = self.get(run_id)
        candidate = next((item for item in view["candidates"] if item["topic_id"] == topic_id), None)
        if candidate is None:
            raise KeyError(topic_id)
        if not candidate["evidence_eligible"]:
            raise Conflict("m09_candidate_evidence_ineligible")
        revision = self._store.review_candidate(run_id, topic_id, decision, expected_revision, request_id, actor_ref)
        return self.get(run_id, revision=revision)

    def compare(self, left_run_id, right_run_id, *, left_revision=None, right_revision=None):
        left = self.get(left_run_id, revision=left_revision)
        right = self.get(right_run_id, revision=right_revision)
        comparison = self.runs.compare(left_run_id, right_run_id)
        left_candidates = {item["topic_id"]: item for item in left["candidates"]}
        right_candidates = {item["topic_id"]: item for item in right["candidates"]}
        matches = [
            {
                **match,
                "left_decision": left_candidates[match["left_topic_id"]]["decision"],
                "right_decision": right_candidates[match["right_topic_id"]]["decision"],
                "similarity": match["shared_documents"] / match["union_documents"],
            }
            for match in comparison["topic_matches"]
        ]
        left_coverage, right_coverage = left["coverage"], right["coverage"]
        return {
            **comparison,
            "output_version": CANDIDATE_OUTPUT_VERSION,
            "left_revision": left["revision"],
            "right_revision": right["revision"],
            "candidate_coverage": {
                "left": left_coverage,
                "right": right_coverage,
                "delta": {key: right_coverage[key] - count for key, count in left_coverage.items()},
            },
            "candidate_matches": matches,
            "unmatched_candidate_topics": {
                "left": sorted(left_candidates.keys() - {item["left_topic_id"] for item in matches}),
                "right": sorted(right_candidates.keys() - {item["right_topic_id"] for item in matches}),
            },
        }
