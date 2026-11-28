"""M09-D independent synthetic holdout using the locked offline test runtime."""

from collections import Counter, defaultdict
from contextlib import ExitStack
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import test_m06_mentions as mentions
import test_m09_actual_topics as fixtures
from src.discovery.embeddings import _row
from src.discovery.topic_candidates import TopicCandidates
from src.discovery.topic_runs import TopicRuns
from src.discovery.topic_store import CANDIDATE_OUTPUT_VERSION
from src.discovery.topics import TopicConfig, _terms
from test_m09_actual_model import approved_backend


EVIDENCE = Path(__file__).resolve().parents[1] / "docs/evidence/m09-d"
INPUT_SHA256 = "38a0f4be20804a4fe9f6ea32f2c8532ceb5d2eae04040bb2317e7989083c2eb4"
GOLD_SHA256 = "3efb13bb905bb215ad9df91a7e6fb01194d2ed6da7519c1804d8b74db05e5e7e"
CONFIG = TopicConfig(
    random_seed=42, n_neighbors=10, n_components=2, min_dist=0.05,
    min_cluster_size=5, min_samples=3, top_n_words=10,
)
ANALYSIS_LANGUAGE = "zh-CN"
OUTPUT_LANGUAGE = "en-US"
CENTROID_CUTOFF = 0.60
NOISE = -1


def verified_fixture(name, expected_sha):
    encoded = (EVIDENCE / name).read_text(encoding="utf-8").encode("utf-8")
    if sha256(encoded).hexdigest() != expected_sha:
        raise ValueError(f"m09d_blind_fixture_changed:{name}")
    return encoded


def recompute_keywords(groups, texts):
    import jieba
    from bertopic.vectorizers import ClassTfidfTransformer
    from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS

    with TemporaryDirectory(prefix="voc-m09d-blind-jieba-") as cache:
        tokenizer = jieba.Tokenizer()
        tokenizer.tmp_dir = cache
        terms = {
            document: _terms(text, tokenizer.cut, ENGLISH_STOP_WORDS)
            for document, text in texts.items()
        }
    if not any(terms.values()):
        return {}
    ids = sorted(groups)
    topic_texts = [" ".join(terms[document] for document in groups[topic]) for topic in ids]
    vectorizer = CountVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False)
    counts = vectorizer.fit_transform(topic_texts)
    keywords = vectorizer.get_feature_names_out()
    weights = ClassTfidfTransformer().fit_transform(counts)
    return {
        topic: [
            {"term": keywords[index], "weight": float(weight)}
            for index, weight in sorted(
                zip(weights[row].indices, weights[row].data, strict=True),
                key=lambda item: (-item[1], keywords[item[0]]),
            )[:CONFIG.top_n_words]
            if weight > 0
        ]
        for row, topic in enumerate(ids) if topic != NOISE
    }


def variants(snapshot, texts):
    raw, filtered, retained = {}, {}, defaultdict(list)
    for member in snapshot["members"]:
        document = member["document_id"]
        topic = member["topic_id"]
        raw[document] = topic
        similarity = member["centroid_similarity"]
        review_topic = topic if similarity is not None and similarity >= CENTROID_CUTOFF else NOISE
        filtered[document] = review_topic
        retained[review_topic].append(document)
    originals = {topic["topic_id"]: topic["keywords"] for topic in snapshot["topics"] if topic["topic_id"] >= 0}
    return {
        "raw": (raw, originals),
        "centroid_exploratory": (filtered, recompute_keywords(retained, texts)),
    }


def score(rows, assignments, keywords, plan):
    from scipy.optimize import linear_sum_assignment

    themes = plan["themes"]
    gold = plan["labels"]
    documents = {sample: gold[sample] for sample in rows}
    present = sorted(set(documents.values()) & themes.keys())
    topics = sorted({topic for topic in assignments.values() if topic >= 0})
    cluster_sizes = Counter(assignments.values())
    theme_sizes = Counter(documents.values())
    overlaps = Counter((documents[sample], topic) for sample, topic in assignments.items())
    matches = {}
    if present and topics:
        weights = [[overlaps[theme, topic] for topic in topics] for theme in present]
        theme_indices, topic_indices = linear_sum_assignment(weights, maximize=True)
        matches = {
            present[i]: topics[j]
            for i, j in zip(theme_indices, topic_indices, strict=True) if weights[i][j]
        }
    theme_results = {}
    for theme in present:
        topic = matches.get(theme)
        hits = sorted(sample for sample, label in documents.items() if label == theme and assignments[sample] == topic)
        other = sorted(sample for sample, label in documents.items() if label != theme and assignments[sample] == topic)
        misses = sorted(sample for sample, label in documents.items() if label == theme and assignments[sample] != topic)
        languages = sorted({rows[sample][1] for sample in hits})
        products = sorted({rows[sample][0] for sample in hits})
        precision = len(hits) / cluster_sizes[topic] if topic is not None else None
        recall = len(hits) / theme_sizes[theme]
        threshold_met = (
            precision is not None and precision >= plan["diagnostic_precision"]
            and recall >= plan["diagnostic_recall"] and len(languages) == len(products) == 2
        )
        theme_results[theme] = {
            "familiarity": themes[theme]["familiarity"], "topic_id": topic,
            "hits": hits, "out_of_cluster": misses, "unrelated_members": other,
            "cluster_size": cluster_sizes[topic] if topic is not None else 0, "gold_size": theme_sizes[theme],
            "precision": precision, "recall": recall, "languages": languages, "products": products,
            "diagnostic_threshold_met": threshold_met,
        }
    return {
        "coverage": [len(assignments) - cluster_sizes[NOISE], len(assignments)],
        "candidate_count": len(topics),
        "supported_novel_candidate_count": sum(
            item["familiarity"] == "unknown" and item["diagnostic_threshold_met"]
            for item in theme_results.values()
        ),
        "unmatched_candidates": {
            topic: sorted(sample for sample, label in assignments.items() if label == topic)
            for topic in topics if topic not in matches.values()
        },
        "residual": {
            label: [sum(documents[sample] == label and topic == NOISE for sample, topic in assignments.items()),
                    theme_sizes[label]]
            for label in ("ambiguous", "singleton")
        },
        "themes": theme_results,
        "keywords": keywords,
        "assignments": assignments,
    }


class BlindFixtureTests(unittest.TestCase):
    def test_fixtures_are_frozen_and_blind_inputs_have_no_gold_labels(self):
        inputs = json.loads(verified_fixture("blind-input-v1.json", INPUT_SHA256))
        plan = json.loads(verified_fixture("blind-gold-v1.json", GOLD_SHA256))
        self.assertEqual(inputs["version"], plan["version"])
        self.assertEqual(inputs["provenance"], "synthetic")
        self.assertEqual(plan["cluster_config"], asdict(CONFIG))
        self.assertEqual(plan["analysis_language"], ANALYSIS_LANGUAGE)
        self.assertEqual(plan["output_language"], OUTPUT_LANGUAGE)
        self.assertEqual(plan["centroid_cutoff"], CENTROID_CUTOFF)
        self.assertEqual(plan["diagnostic_precision"], 0.75)
        self.assertEqual(plan["diagnostic_recall"], 0.75)
        self.assertEqual({name: len(batch) for name, batch in inputs["batches"].items()}, {"mixed": 32, "negative": 18})
        rows = [row for batch in inputs["batches"].values() for row in batch]
        self.assertEqual(len({row[0] for row in rows}), len(rows))
        self.assertEqual({row[0] for row in rows}, plan["labels"].keys())
        for _, product, language, text in rows:
            self.assertIn(product, ("scale", "fryer"))
            self.assertIn(language, ("en-US", "zh-CN"))
            self.assertTrue(text.strip())


@unittest.skipUnless(
    os.environ.get("VOC_M09_MODEL_DIR") and os.environ.get("VOC_M09_MODEL_MANIFEST"),
    "requires the separately provisioned local model and BERTopic runtime",
)
class BlindModelTests(unittest.TestCase):
    def _batch(self, name, entries, backend):
        products = {"scale": fixtures.SCALE, "fryer": fixtures.FRYER}
        examples = tuple(fixtures.Example(None, products[product], language, text)
                         for _, product, language, text in entries)
        case = mentions.MentionTests()
        self.addCleanup(case.doCleanups)
        fixture_ids = iter(uuid5(NAMESPACE_URL, f"voc-m09-d-holdout-v1/{name}/{index}") for index in range(1000))
        with ExitStack() as stack:
            for module in ("studies", "imports", "mentions"):
                stack.enter_context(patch(f"src.raw_store.{module}.uuid4", side_effect=fixture_ids))
            case.setUp()
            refs, by_document, evidence = fixtures.ApprovedTopicTest.build_fixture(SimpleNamespace(case=case), examples)
        service = TopicRuns(case.db, evidence, authorize_project=lambda study: study == case.study)
        run = service.create(
            backend, refs, request_id=f"blind-{name}-baseline", config=CONFIG,
            registry_version=mentions.CATALOG, analysis_language=ANALYSIS_LANGUAGE, output_language=OUTPUT_LANGUAGE,
        )
        self.assertEqual(service.get(run["run_id"]), run)
        self.assertEqual(len(run["members"]), len(examples))
        self.assertEqual(run["metadata"]["research_denominator"], 0)
        by_text = {text: sample for sample, _, _, text in entries}
        documents = {document: by_text[example.text] for document, example in by_document.items()}
        texts = {}
        for member in run["members"]:
            document = member["document_id"]
            actual = service.evidence_for(run["run_id"], document)
            self.assertEqual(actual.original_text, by_document[document].text)
            self.assertTrue(member["evidence_eligible"])
            texts[document] = _row(actual, backend.profile.supported_languages).model_text
        replay = service.replay(run["run_id"], backend, request_id=f"blind-{name}-recalculation")
        self.assertNotEqual(replay["run_id"], run["run_id"])
        self.assertEqual(replay["replay_of"], run["run_id"])
        comparison = service.compare(run["run_id"], replay["run_id"])
        self.assertTrue(comparison["same_result"])
        outcomes = variants(run, texts)
        self.assertEqual(variants(replay, texts), outcomes)
        self.assertEqual(service.get(run["run_id"]), run)
        candidates = TopicCandidates(service)
        projected = candidates.get(run["run_id"])
        self.assertEqual(projected["output_version"], CANDIDATE_OUTPUT_VERSION)
        self.assertEqual(projected["revision"], 0)
        observed = outcomes["raw"][0]
        expected_members = defaultdict(list)
        for document, topic in observed.items():
            if topic >= 0:
                expected_members[topic].append(document)
        self.assertEqual(
            {candidate["topic_id"]: candidate["member_document_ids"] for candidate in projected["candidates"]},
            dict(expected_members),
        )
        candidate_comparison = candidates.compare(run["run_id"], replay["run_id"])
        self.assertTrue(candidate_comparison["same_result"])
        self.assertTrue(all(delta == 0 for delta in candidate_comparison["candidate_coverage"]["delta"].values()))
        return run, replay, comparison, outcomes, documents, candidates, projected

    def test_actual_model_blind_batches_and_replay(self):
        inputs = json.loads(verified_fixture("blind-input-v1.json", INPUT_SHA256))
        label_bytes = verified_fixture("blind-gold-v1.json", GOLD_SHA256)
        backend = approved_backend()
        self.addCleanup(backend.close)
        fitted = {name: self._batch(name, entries, backend) for name, entries in inputs["batches"].items()}
        plan = json.loads(label_bytes)
        for name, entries in inputs["batches"].items():
            run, replay, comparison, outcomes, documents, candidates, projected = fitted[name]
            rows = {sample: (product, language) for sample, product, language, _ in entries}
            self.assertEqual({documents[doc] for doc in documents}, rows.keys())
            results = {
                variant: score(rows, {documents[doc]: topic for doc, topic in assignments.items()}, keywords, plan)
                for variant, (assignments, keywords) in outcomes.items()
            }
            review_result = None
            if name == "negative":
                false_topics = results["raw"]["unmatched_candidates"]
                if false_topics:
                    topic = min(false_topics)
                    reviewed = candidates.review(
                        run["run_id"], topic, decision="rejected", expected_revision=0,
                        request_id="blind-negative-reject", actor_ref="synthetic-reviewer",
                    )
                    historical = candidates.get(run["run_id"], revision=0)
                    self.assertEqual(historical["candidates"], projected["candidates"])
                    self.assertEqual(historical["coverage"], projected["coverage"])
                    self.assertEqual(candidates.get(run["run_id"], revision=reviewed["revision"]), reviewed)
                    self.assertEqual(reviewed["run"], run)
                    self.assertEqual(reviewed["coverage"]["candidate_count"], projected["coverage"]["candidate_count"] - 1)
                    self.assertEqual(reviewed["coverage"]["rejected_candidate_count"], 1)
                    review_result = {
                        "topic_id": topic, "previous_revision": 0, "revision": reviewed["revision"],
                        "decision": "rejected", "previous_coverage": projected["coverage"],
                        "revised_coverage": reviewed["coverage"],
                    }
            report = {
                "version": inputs["version"], "batch": name,
                "input_fixture_sha256": INPUT_SHA256, "gold_fixture_sha256": GOLD_SHA256,
                "run_id": run["run_id"], "replay_id": replay["run_id"], "status": run["status"],
                "study_id": run["study_id"], "scope_id": run["scope_id"], "scope_version": run["scope_version"],
                "same_result": comparison["same_result"], "topic_matches": comparison["topic_matches"],
                "metadata": run["metadata"], "results": results,
                "candidate_output_version": projected["output_version"],
                "candidate_projection_coverage": projected["coverage"], "synthetic_reviewer_action": review_result,
                "documents": {
                    documents[member["document_id"]]: {
                        field: member[field] for field in (
                            "document_id", "lineage", "reference", "original_language", "model_input_sha256",
                            "original_excerpt_sha256", "raw_topic_id", "membership_probability",
                            "outlier_score", "centroid_similarity",
                        )
                    } for member in run["members"]
                },
            }
            print("M09-D-BLIND " + json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False), flush=True)
