"""Derive a Personal D same-batch result from current, archived evidence."""

from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit

from src.config import MODEL
from src.execution import jev
from src.execution.packycode_preflight import inspect_body
from src.execution.transport import Response, number
from src.ingestion.public_source import DOMAIN, SITE, fetch_forum_post, post_id
from src.raw_store.store import dump


REQUIREMENTS = tuple(f"C0-{index}" for index in range(1, 7))
SLOTS = (("search", 1), ("source", 1), ("model", 1), ("model", 2))
PROVIDERS = {"search": "tavily", "source": "stackexchange", "model": "packycode"}
EVIDENCE_STATE = {"approved", "executing", "reconciliation", "evidence_review", "complete"}
REGISTRY = "b031aa1275b8b2b6"
INDEX = "18e87696ba7bc015"
ISOLATION_CHECKS = frozenset({
    "edition", "cross_project", "unapproved_provider", "invalid_credential",
    "credential_rotation", "approval_revocation", "expiry", "source_ineligible",
    "budget", "offline", "timeout", "rate_limit", "upstream", "contract",
    "unknown_charge", "restore_replay", "synthetic_isolation",
})


def _digest(value):
    return sha256(dump(value).encode("utf-8")).hexdigest()


def _read(read_archive, ref):
    if not isinstance(ref, str) or not ref:
        return {}
    try:
        artifact = read_archive(ref)
        _digest(artifact)
    except (KeyError, OSError, ValueError, TypeError):
        return {}
    return artifact if isinstance(artifact, dict) else {}


def _linked_requests(view, current_grant_ids, read_archive):
    batch_id = view["batch"]["batch_id"]
    grants = {grant["grant_id"]: grant for grant in view["grants"]
              if grant["grant_id"] in current_grant_ids and grant["batch_id"] == batch_id}
    receipts = {receipt["request_id"]: receipt for receipt in view["receipts"]}
    linked = {}
    for request in view["requests"]:
        slot = request["operation"], request["slot"]
        if request["batch_id"] != batch_id or slot not in SLOTS:
            continue
        grant, receipt = grants.get(request["grant_id"]), receipts.get(request["request_id"])
        if (grant is None or receipt is None or (grant["operation"], grant["slot"]) != slot
                or request["state"] not in {"reconciliation", "settled"}
                or receipt["response_status"] != 200
                or any(receipt[field] != grant[field] for field in ("provider", "account_ref", "model"))
                or receipt["provider"] != PROVIDERS[slot[0]]
                or receipt["request_sha256"] != request["payload_sha256"]
                or receipt["request_sha256"] != grant["payload_sha256"]):
            continue
        artifact = _read(read_archive, receipt["evidence_ref"])
        payload, response = artifact.get("request"), artifact.get("response")
        if (isinstance(payload, dict) and isinstance(response, dict) and artifact.get("batch_id") == batch_id
                and artifact.get("request_id") == request["request_id"]
                and _digest(payload) == request["payload_sha256"]
                and _digest(response) == receipt["response_sha256"]):
            linked[slot] = (request, grant, receipt, payload, response)
    return linked


def _depends(child, parent, *, same_source=True):
    return (child[1]["depends_on"] == parent[0]["request_id"]
            and child[1]["depends_on_sha256"] == parent[2]["response_sha256"]
            and (not same_source or child[1]["source_ref"] == parent[1]["source_ref"]))


def _source_url_matches(value, source_id):
    if post_id(value) != source_id:
        return False
    parts = urlsplit(value)
    return not parts.query and not parts.fragment


def _source_provenance(provenance, citation, source_id, grant):
    if (not isinstance(provenance, dict) or not _source_url_matches(provenance.get("final_url"), source_id)
            or provenance.get("method") != citation["method"]
            or provenance.get("classification") != "public_approved"
            or provenance.get("license_url") != citation["license_url"]):
        return False
    try:
        collected = datetime.fromisoformat(provenance["collected_at"])
        published = datetime.fromisoformat(citation["published_at"])
        start = datetime.fromisoformat(grant["valid_from"])
        end = datetime.fromisoformat(grant["expires_at"])
        return collected.utcoffset() == UTC.utcoffset(collected) and published <= collected and start <= collected < end
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _source_pass(search, source):
    if not search or not source or not _depends(source, search, same_source=False):
        return False
    request, response = source[3:5]
    url = request.get("url")
    source_id = post_id(url)
    results = search[4].get("results")
    if (source_id is None or request != {"url": f"https://{DOMAIN}/questions/{source_id}", "site": SITE, "filter": "withbody"}
            or search[1]["source_ref"] != DOMAIN or search[1]["source_sha256"] != _digest(DOMAIN)
            or search[2]["source_sha256"] != _digest(DOMAIN) or search[3].get("include_domains") != [DOMAIN]
            or not isinstance(results, list)
            or not any(isinstance(hit, dict) and hit.get("url") == url
                       and _source_url_matches(hit.get("actual_url"), source_id) for hit in results[:5])
            or source[1]["source_sha256"] != _digest(url) or source[2]["source_sha256"] != _digest(url)):
        return False
    _, _, citation = fetch_forum_post(
        source_id, "tavily", transport=lambda *_: Response(200, response),
    )
    return (citation["verified"] and _digest(citation["text"]) == source[2]["quote_sha256"]
            and _source_provenance(response.get("provenance"), citation, source_id, source[1]))


def _model_checks(source, first, second, reviewed_model_input_sha256):
    if (not source or not first or not second or not _depends(first, source) or not _depends(second, first)
            or any(first[1][field] != second[1][field] for field in
                   ("account_ref", "channel_ref", "credential_revision", "question_version", "approval_event_id"))
            or first[1]["channel_ref"] != "typesafe-officially"
            or not first[1]["question_version"] or not first[1]["approval_event_id"]
            or not isinstance(reviewed_model_input_sha256, str)
            or not isinstance(first[3].get("state"), str) or second[3].get("state") != first[3]["state"]
            or any(part[2]["quote_sha256"] != reviewed_model_input_sha256
                   or _digest(part[3]["state"]) != reviewed_model_input_sha256
                   or part[2]["source_sha256"] != source[2]["source_sha256"]
                   or part[1]["source_sha256"] != source[2]["source_sha256"] for part in (first, second))):
        return False, False
    merged = {}
    contract_ok = True
    for part, expected in zip((first, second), jev.split(jev.questions()), strict=True):
        payload, response = part[3:5]
        asked, answers = payload.get("questions"), response.get("answers")
        if (payload.get("model") != MODEL or response.get("model") != MODEL
                or part[2]["model"] != MODEL or not isinstance(asked, dict) or set(asked) != set(expected)
                or not isinstance(answers, dict) or set(answers) != set(asked) or set(answers) & merged.keys()):
            return False, False
        if _question_contract(asked, expected):
            _, gaps = inspect_body(asked, response)
            contract_ok = contract_ok and not gaps
        else:
            contract_ok = False
        merged.update(answers)
    return len(merged) == 11, contract_ok


def _question_contract(asked, expected):
    for key, question in asked.items():
        if not isinstance(question, dict) or question.get("type") != expected[key]["type"]:
            return False
        if key == "intent":
            criteria = question.get("criteria")
            if (not isinstance(criteria, dict) or len(criteria) != 12
                    or criteria.get("None") != expected[key]["criteria"]["None"]
                    or any(not isinstance(label, str) or not label for label in criteria.values())):
                return False
        elif key != "in_registry" and question != expected[key]:
            return False
    return True


def _usage_and_cost(linked, view, proof):
    if set(linked) != set(SLOTS):
        return False
    charges = proof.get("charges")
    if (proof.get("sqlite_reopened") is not True or proof.get("restart_readback") is not True
            or proof.get("idempotent_readback") is not True or proof.get("duplicate_charge_prevented") is not True
            or proof.get("integrity_check") != "ok" or proof.get("foreign_key_violations") != 0
            or proof.get("currency") != view["batch"]["currency"] or not isinstance(charges, dict)):
        return False
    batch = view["batch"]
    credits = 0
    usage_fields = ("input_tokens", "output_tokens", "total_tokens")
    tokens = dict.fromkeys(usage_fields, 0)
    actual_amounts = []
    for slot, (request, _, receipt, _, response) in linked.items():
        charge = charges.get(request["request_id"])
        actual = receipt.get("reconciled_units")
        if actual is None:
            actual = receipt.get("actual_units")
        if (request["state"] != "settled" or number(actual) is None or actual > request["units"]
                or not isinstance(charge, dict) or number(charge.get("actual_units")) != actual
                or not isinstance(charge.get("bill_ref"), str) or not charge["bill_ref"]
                or receipt.get("provider_request_id") != charge.get("provider_request_id")
                or receipt["provider"] != charge.get("provider") or receipt["account_ref"] != charge.get("account_ref")):
            return False
        usage = response.get("usage")
        if slot[0] == "model":
            if (not receipt.get("provider_request_id") or receipt.get("balance_status") not in {"verified", "unsynced"}
                    or not isinstance(usage, dict) or any(
                number(usage.get(field)) is None or usage[field] != receipt[field]
                or usage[field] > request[field] for field in usage_fields
            ) or receipt["total_tokens"] != receipt["input_tokens"] + receipt["output_tokens"]):
                return False
            for field in usage_fields:
                tokens[field] += usage[field]
        elif slot[0] == "search":
            if (not isinstance(usage, dict) or number(usage.get("credits")) is None
                    or usage["credits"] != 1 or usage["credits"] != receipt["credits"]
                    or usage["credits"] > request["credits"]):
                return False
            credits += usage["credits"]
        actual_amounts.append(actual)
    totals = {"request_limit": len(linked), "credit_limit": credits, "input_limit": tokens["input_tokens"],
              "output_limit": tokens["output_tokens"], "token_limit": tokens["total_tokens"],
              "cost_limit": sum(actual_amounts)}
    return (len(charges) == len(SLOTS) and all(
        number(batch.get(limit)) is not None and value <= batch[limit] for limit, value in totals.items()
    ) and number(batch.get("single_cost")) is not None and max(actual_amounts) <= batch["single_cost"])


def _ref_proof(view, check, reviewed_refs, read_archive):
    batch_id = view["batch"]["batch_id"]
    kind = "formal_live" if check == "C0-4" else "formal_offline"
    for item in reversed(view["evidence"]):
        reference = item["evidence_ref"], item["evidence_sha256"]
        if (item["batch_id"] == batch_id and item["requirement"] == check
                and item["kind"] == kind and reference in reviewed_refs):
            proof = _read(read_archive, item["evidence_ref"])
            if (proof.get("batch_id") == batch_id and proof.get("requirement") == check
                    and _digest(proof) == item["evidence_sha256"]):
                return proof, item["evidence_ref"]
    return {}, None


def _isolation_pass(proof):
    cases = proof.get("formal_cases")
    return (proof.get("passed") is True
            and proof.get("synthetic_cases") == 36 and proof.get("blocked_before_transport") == 36
            and type(proof.get("private_transport_calls")) is int and proof["private_transport_calls"] == 0
            and type(proof.get("external_requests")) is int and proof["external_requests"] == 0
            and isinstance(cases, dict) and all(cases.get(case) is True for case in ISOLATION_CHECKS))


def _recall_pass(proof, approved_versions):
    counts, probes = proof.get("counts"), proof.get("queries")
    if (proof.get("passed") is not True or not isinstance(counts, dict)
            or type(counts.get("intents")) is not int or counts["intents"] < 30
            or counts.get("products") != 2 or counts.get("tasks") != 3 or proof.get("orphan_links") != 0
            or proof.get("dataset") != "synthetic_smoke" or proof.get("research_denominator") != 0
            or (proof.get("registry_version"), proof.get("index_version")) != approved_versions
            or type(proof.get("k")) is not int or not 1 <= proof["k"] <= 19
            or not isinstance(probes, list) or len(probes) < 2):
        return False
    tested_pairs = set()
    for probe in probes:
        if not isinstance(probe, dict):
            return False
        choices, candidates = probe.get("choice_options"), probe.get("candidates")
        query_product, evidence_product = probe.get("query_product"), probe.get("evidence_product")
        if (probe.get("cross_product_hit") is not True or not isinstance(query_product, str)
                or not isinstance(evidence_product, str) or query_product == evidence_product
                or probe.get("noul_guard") != "in_registry" or not isinstance(candidates, list)
                or not all(isinstance(candidate, dict) and isinstance(candidate.get("intent_id"), str)
                           for candidate in candidates)):
            return False
        intent_ids = [candidate["intent_id"] for candidate in candidates]
        if (len(intent_ids) != proof["k"] or len(set(intent_ids)) != len(intent_ids) or "None" in intent_ids
                or probe.get("expected") not in intent_ids or choices != [*intent_ids, "None"]):
            return False
        tested_pairs.add((query_product, evidence_product))
    return len(tested_pairs) >= 2


def evaluate_formal_batch(view, *, currently_authorized=False, current_grant_ids=(),
                          reviewed_refs=(), reviewed_model_input_sha256=None,
                          approved_recall_versions=(REGISTRY, INDEX), read_archive=lambda _: None):
    """Use a canonical ledger view and server-verified authorization and archive bindings.

    The trusted caller supplies current grant IDs, an authorized source transformation
    digest, independently approved recall versions, and the accepted (ref, sha256)
    pairs for offline evidence. The reader
    resolves local receipt evidence to {batch_id, request_id, request, response}
    without network I/O.
    A receipt digest and a typed evidence reference alone cannot mark a check PASS.
    """
    batch = view["batch"]
    batch_id = batch["batch_id"]

    def result(passed, blocker, kind, *refs, failed=False):
        return {
            "batch_id": batch_id, "status": "PASS" if passed else "FAIL" if failed else "BLOCKED",
            "reason": None if passed else blocker, "kind": kind,
            "evidence_refs": [ref for ref in refs if ref is not None],
        }

    if (batch.get("mode") != "formal_live" or batch.get("edition") != "PERSONAL"
            or batch.get("purpose") != "g1_personal_acceptance"
            or batch.get("state") not in EVIDENCE_STATE or currently_authorized is not True):
        return {check: result(False, "formal_batch_not_current", "missing") for check in REQUIREMENTS}

    archived = _linked_requests(view, frozenset(current_grant_ids), read_archive)
    linked = {slot: part for slot, part in archived.items() if part[2]["eligible"] == 1}
    search, source, first, second = (linked.get(slot) for slot in SLOTS)
    source_passed = _source_pass(search, source)
    identity, contract = _model_checks(source if source_passed else None, first, second, reviewed_model_input_sha256)
    model_receipts = [part[2] for slot, part in archived.items() if slot[0] == "model"]
    model_refs = [receipt["evidence_ref"] for receipt in model_receipts]
    model_gap = any(receipt.get("reason") == "schema_gap" for receipt in model_receipts)
    source_refs = [part[2]["evidence_ref"] for part in (search, source) if part is not None]
    accounting, accounting_ref = _ref_proof(view, "C0-4", reviewed_refs, read_archive)
    isolation, isolation_ref = _ref_proof(view, "C0-5", reviewed_refs, read_archive)
    recall, recall_ref = _ref_proof(view, "C0-6", reviewed_refs, read_archive)
    return {
        "C0-1": result(identity, "missing_verified_8_plus_3_response", "formal_live", *model_refs),
        "C0-2": result(contract, "schema_gap" if identity or model_gap else "missing_verified_model_response",
                       "formal_live", *model_refs),
        "C0-3": result(source_passed, "missing_permitted_search_source_chain", "formal_live", *source_refs),
        "C0-4": result(source_passed and identity and _usage_and_cost(linked, view, accounting),
                       "missing_verified_usage_charge_or_readback", "formal_live", *source_refs, *model_refs,
                       accounting_ref),
        "C0-5": result(_isolation_pass(isolation), "isolation_drill_failed" if isolation.get("passed") is False
                       else "missing_current_isolation_drill", "formal_offline", isolation_ref,
                       failed=isolation.get("passed") is False),
        "C0-6": result(_recall_pass(recall, approved_recall_versions),
                       "global_recall_failed" if recall.get("passed") is False else "missing_current_global_recall",
                       "formal_offline", recall_ref, failed=recall.get("passed") is False),
    }
