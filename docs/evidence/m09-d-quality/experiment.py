"""Offline synthetic experiment for M09-D. Fitting and gold scoring are separate commands."""

import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import version
import ipaddress
from itertools import combinations
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NOISE = -1
SEEDS = (42, 17, 67)
METHODS = ("baseline", "centroid_060", "density_5d", "cosine_055", "cosine_055_margin")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def offline_runtime(model_path, app_site_packages):
    for key in tuple(os.environ):
        name = key.upper()
        if name.startswith(("VOC_", "TAVILY_", "BRAVE_", "PACKY", "JEV", "HF_", "HUGGINGFACE_", "OPENAI_",
                            "TYPESAFE_", "YOUTUBE_")) or name.endswith(("_API_KEY", "_TOKEN")):
            del os.environ[key]
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
        OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", NUMBA_NUM_THREADS="2",
        VOC_M09_MODEL_DIR=str(model_path.resolve(strict=True)),
        VOC_M09_MODEL_MANIFEST=str(ROOT / "docs/evidence/m09-a/model-assets.json"),
    )
    attempts = []

    def network_guard(event, args):
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}:
            target = args[0]
        elif event in {"socket.connect", "socket.sendto"}:
            target = args[1]
        else:
            return
        host = target[0] if isinstance(target, tuple) else target
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except (TypeError, ValueError):
            pass
        attempts.append(event)
        raise RuntimeError("M09-D quality experiment blocked a non-loopback network operation")

    sys.addaudithook(network_guard)
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    sys.path.append(str(app_site_packages.resolve(strict=True)))
    return attempts


def groups(labels):
    return {label: [i for i, assigned in enumerate(labels) if assigned == label]
            for label in sorted(set(labels) - {NOISE})}


def reject_small(labels, minimum):
    sizes = Counter(labels)
    return [label if label != NOISE and sizes[label] >= minimum else NOISE for label in labels]


def cosine_labels(vectors):
    from sklearn.cluster import AgglomerativeClustering

    fitted = AgglomerativeClustering(n_clusters=None, distance_threshold=0.55,
                                     metric="cosine", linkage="average")
    return reject_small(fitted.fit_predict(vectors).tolist(), 4)


def margin_labels(vectors, labels):
    import numpy as np

    clusters = groups(labels)
    centroids = {}
    for label, members in clusters.items():
        center = vectors[members].mean(axis=0)
        norm = np.linalg.norm(center)
        if norm:
            centroids[label] = center / norm
    filtered = labels.copy()
    for label, members in clusters.items():
        for i in members:
            # Compare against a centroid that excludes the row being assessed.
            own_center = vectors[[j for j in members if j != i]].mean(axis=0)
            norm = np.linalg.norm(own_center)
            own_score = float(vectors[i] @ (own_center / norm)) if norm else -1.0
            rival_score = max((float(vectors[i] @ center) for other, center in centroids.items()
                               if other != label), default=-1.0)
            if own_score < 0.40 or own_score - rival_score < 0.05:
                filtered[i] = NOISE
    return reject_small(filtered, 4)


def fit_variants(batch, seed, methods):
    from src.discovery.topics import TopicConfig, _cluster_batch

    def timed(function):
        start, cpu = perf_counter(), process_time()
        labels = function()
        return {"labels": list(map(int, labels)), "wall_s": perf_counter() - start,
                "cpu_s": process_time() - cpu}

    diagnostics = []
    baseline = timed(lambda: _cluster_batch(
        batch, TopicConfig(random_seed=seed), observe_diagnostics=diagnostics.extend)[1])
    variants = {"baseline": baseline}
    if "centroid_060" in methods:
        variants["centroid_060"] = timed(lambda: [
            row.topic_id if row.centroid_cosine is not None and row.centroid_cosine >= 0.60 else NOISE
            for row in diagnostics
        ] if diagnostics else baseline["labels"])
    if "density_5d" in methods:
        variants["density_5d"] = timed(lambda: _cluster_batch(
            batch, TopicConfig(random_seed=seed, n_neighbors=8, n_components=5,
                               min_cluster_size=4, min_samples=2))[1])
    if "cosine_055" in methods or "cosine_055_margin" in methods:
        cosine = timed(lambda: cosine_labels(batch.vectors))
        variants["cosine_055"] = cosine
        if "cosine_055_margin" in methods:
            margin = timed(lambda: margin_labels(batch.vectors, cosine["labels"]))
            if "cosine_055" not in methods:
                for key in ("wall_s", "cpu_s"):
                    margin[key] += cosine[key]
            variants["cosine_055_margin"] = margin
    return {name: variants[name] for name in methods}


def run_fit(args):
    attempts = offline_runtime(args.model, args.app_site_packages)
    import numpy as np
    from src.discovery.embeddings import EmbeddingBatch, PREPROCESSING_VERSION, _matrix, _row
    from test_m09_actual_model import approved_backend

    input_path = HERE / "data" / f"{args.split}-input.json"
    data = read_json(input_path)
    expected = {"id", "text", "language"}
    items = sorted(data["rows"], key=lambda row: row["id"])
    if not items or any(set(row) != expected for row in items) or len({row["id"] for row in items}) != len(items):
        raise ValueError("Invalid blind input schema or duplicate sample ID")
    backend = approved_backend()
    start, cpu = perf_counter(), process_time()
    try:
        rows = tuple(_row(SimpleNamespace(lineage=SimpleNamespace(document_id=item["id"]),
                     original_language=item["language"], original_text=item["text"]),
                     backend.profile.supported_languages) for item in items)
        vectors = _matrix(backend.encode(tuple(row.model_text for row in rows)), len(rows), backend.profile)
    finally:
        backend.close()
    embedding = {"wall_s": perf_counter() - start, "cpu_s": process_time() - cpu,
                 "model": backend.profile.model_id, "revision": backend.profile.revision,
                 "preprocessing": PREPROCESSING_VERSION, "vector_sha256": sha256(vectors.tobytes()).hexdigest()}
    batch = EmbeddingBatch(digest(input_path), backend.profile, PREPROCESSING_VERSION,
                           "synthetic-quality-only", "en", "en", rows, vectors, False)
    runs = []
    for seed in SEEDS:
        order = list(range(len(rows))) if seed == SEEDS[0] else np.random.default_rng(seed).permutation(len(rows)).tolist()
        permuted = replace(batch, rows=tuple(rows[i] for i in order), vectors=vectors[order])
        variants = fit_variants(permuted, seed, args.methods)
        for result in variants.values():
            result["assignments"] = dict(sorted(
                (rows[i].document_id, label) for i, label in zip(order, result.pop("labels"), strict=True)
            ))
        runs.append({"seed": seed, "permuted": seed != SEEDS[0], "methods": variants})
    if attempts:
        raise RuntimeError(f"Non-loopback network attempts: {len(attempts)}")
    write_new(args.output, {
        "protocol": "m09-d-quality-v1", "split": args.split, "dataset_version": data["version"],
        "input_sha256": digest(input_path), "embedding": embedding, "network_attempts": len(attempts),
        "platform": platform.platform(), "python": platform.python_version(),
        "packages": {name: version(name) for name in ("bertopic", "umap-learn", "hdbscan", "scikit-learn",
                     "sentence-transformers", "torch", "jieba", "numpy", "scipy")},
        "runs": runs,
    })
    print(f"{args.split}: {len(rows)} rows, {len(runs)} runs, non-loopback network attempts: {len(attempts)}")


def matched_metrics(assignments, gold, languages):
    from scipy.optimize import linear_sum_assignment
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    ids = list(gold)
    if not ids or set(ids) != set(assignments) or set(ids) != set(languages):
        raise ValueError("Prediction, reference and language IDs must match")
    labels = [assignments[key] for key in ids]
    expected = [gold[key] for key in ids]
    clusters = groups(labels)
    intents = sorted(set(expected) - {None})
    weighting = [[sum(expected[i] == label for i in members) for members in clusters.values()]
                 for label in intents]
    matches = {}
    if intents and clusters:
        row_ids, column_ids = linear_sum_assignment(weighting, maximize=True)
        matches = {intents[i]: list(clusters)[j] for i, j in zip(row_ids, column_ids, strict=True)
                   if weighting[i][j]}
    metrics = {}
    supported = 0
    for label in intents:
        picked = matches.get(label)
        members = clusters.get(picked, [])
        hits = sum(expected[i] == label for i in members)
        gold_size = expected.count(label)
        purity = hits / len(members) if members else None
        recall = hits / gold_size
        language_support = sorted({languages[ids[i]] for i in members if expected[i] == label})
        passes = purity is not None and purity >= 0.70 and recall >= 0.50 and len(language_support) >= 2
        supported += int(passes)
        metrics[label] = {"topic": picked, "hits": hits, "cluster_size": len(members), "gold_size": gold_size,
                          "purity": purity, "recall": recall, "matched_languages": language_support,
                          "supported": passes}
    positives = [i for i, label in enumerate(expected) if label is not None]
    negatives = [i for i, label in enumerate(expected) if label is None]
    assigned = sum(label != NOISE for label in labels)
    max_hits = sum(max(Counter(expected[i] for i in members if expected[i] is not None).values(), default=0)
                   for members in clusters.values())
    matched_hits = sum(item["hits"] for item in metrics.values())
    # Positive-only clustering indices count every predicted outlier as a separate singleton.
    prediction = [labels[i] if labels[i] != NOISE else -2 - i for i in positives]
    reference = [expected[i] for i in positives]
    return {
        "assignment_coverage": [assigned, len(ids)], "outliers": [len(ids) - assigned, len(ids)],
        "positive_coverage": [sum(labels[i] != NOISE for i in positives), len(positives)],
        "negative_assignment": [sum(labels[i] != NOISE for i in negatives), len(negatives)],
        "weighted_purity": [max_hits, assigned], "matched_recall": [matched_hits, len(positives)],
        "unsupported_candidates": [len(clusters) - supported, len(clusters)],
        "ari_positive": adjusted_rand_score(reference, prediction) if positives else None,
        "nmi_positive": normalized_mutual_info_score(reference, prediction) if positives else None,
        "intents": metrics,
    }


def stability(left, right):
    from scipy.optimize import linear_sum_assignment

    ids = sorted(left)
    clusters = [list(groups([run[key] for key in ids]).values()) for run in (left, right)]
    pairs = [{pair for group in part for pair in combinations(group, 2)} for part in clusters]
    candidates = [[set(group) for group in part] for part in clusters]
    candidate_overlap = [[len(a & b) / len(a | b) for b in candidates[1]] for a in candidates[0]]
    maximum = max(map(len, candidates))
    consistency = None
    if maximum:
        if all(candidates):
            pi, pj = linear_sum_assignment(candidate_overlap, maximize=True)
            consistency = sum(candidate_overlap[i][j] for i, j in zip(pi, pj, strict=True)) / maximum
        else:
            consistency = 0.0
    return {"coassigned_pair_jaccard": len(pairs[0] & pairs[1]) / len(pairs[0] | pairs[1])
            if pairs[0] or pairs[1] else None, "candidate_member_jaccard": consistency}


def run_score(args):
    predictions = read_json(args.predictions)
    input_path = HERE / "data" / f"{args.split}-input.json"
    gold_path = args.gold or HERE / "data" / f"{args.split}-gold.json"
    if args.split.startswith("holdout-") and args.gold is None:
        raise ValueError("Supply the owner's sealed reference file explicitly for the final evaluation")
    inputs, gold = read_json(input_path), read_json(gold_path)
    if (predictions["protocol"] != "m09-d-quality-v1" or predictions["network_attempts"] != 0
            or predictions["input_sha256"] != digest(input_path) or predictions["split"] != args.split
            or inputs["version"] != gold["version"] or predictions["dataset_version"] != inputs["version"]):
        raise ValueError("Dataset and prediction provenance mismatch")
    languages = {item["id"]: item["language"] for item in inputs["rows"]}
    results = {}
    if tuple(run["seed"] for run in predictions["runs"]) != SEEDS or any(
        set(run["methods"]) != set(args.methods) for run in predictions["runs"]
    ):
        raise ValueError("Predictions differ from the frozen seed or strategy roster")
    for name in args.methods:
        runs = [run["methods"][name] for run in predictions["runs"]]
        main = runs[0]
        results[name] = {
            "seed_42": matched_metrics(main["assignments"], gold["labels"], languages),
            "perturbed": [
                {"seed": run["seed"], **stability(main["assignments"], variant["assignments"]),
                 "metrics": matched_metrics(variant["assignments"], gold["labels"], languages)}
                for run, variant in zip(predictions["runs"][1:], runs[1:], strict=True)
            ],
            "wall_s_by_seed": [run["wall_s"] for run in runs],
            "cpu_s_by_seed": [run["cpu_s"] for run in runs],
        }
    write_new(args.output, {"protocol": predictions["protocol"], "dataset_version": gold["version"],
                            "input_sha256": digest(input_path), "gold_sha256": digest(gold_path),
                            "prediction_sha256": digest(args.predictions), "methods": results})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fit, score = commands.add_parser("fit"), commands.add_parser("score")
    for command in (fit, score):
        command.add_argument("split", choices=("dev", "validation", "holdout-mixed", "holdout-negative"))
        command.add_argument("output", type=Path)
        command.add_argument("--challenger", choices=METHODS[1:])
    fit.add_argument("--model", required=True, type=Path)
    fit.add_argument("--app-site-packages", required=True, type=Path)
    score.add_argument("--predictions", required=True, type=Path)
    score.add_argument("--gold", type=Path)
    args = parser.parse_args()
    holdout = args.split.startswith("holdout-")
    if holdout != bool(args.challenger):
        parser.error("Choose exactly one challenger for holdout splits only")
    args.methods = ("baseline", args.challenger) if holdout else METHODS
    (run_fit if args.command == "fit" else run_score)(args)


if __name__ == "__main__":
    main()
