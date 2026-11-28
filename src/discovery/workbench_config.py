"""Trusted local configuration for the isolated M09 workbench."""

import json
from pathlib import Path

from src.config import ROOT
from src.discovery.embedding_backend import (
    EmbeddingProfile, LOCAL_BACKEND, LOCAL_BACKEND_VERSION, LocalSentenceTransformer,
    local_runtime_version, manifest_fingerprint,
)
from src.discovery.embedding_inputs import FixtureRecord, MentionEvidence, SamplingEvidence


def load_catalog(directory):
    """Read pinned synthetic references from the local workspace, never from an HTTP body."""
    path = directory / "m09-discovery-synthetic.json"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig") as stream:
        entries = json.load(stream)
    catalog = {}
    for entry in entries:
        scope = tuple(entry[name] for name in ("study_id", "scope_id", "scope_version"))
        if scope in catalog:
            raise ValueError("Duplicate frozen M09 scope.")
        refs = []
        for row in entry["references"]:
            details = {key: value for key, value in row.items() if key != "kind"}
            if row["kind"] == "mention":
                record = FixtureRecord(*scope, details.pop("record_id"), details.pop("raw_sha256"))
                refs.append(MentionEvidence(record, **details))
            elif row["kind"] == "sampling":
                refs.append(SamplingEvidence(**details))
            else:
                raise ValueError("Unknown M09 synthetic reference type.")
        catalog[scope] = (entry["registry_version"], tuple(refs))
    return catalog


def approved_local_backend(model_directory):
    model_directory = Path(model_directory)
    if not model_directory.is_absolute() or not model_directory.is_dir():
        raise ValueError("M09 needs an existing absolute local model path.")
    manifest_path = ROOT / "docs/evidence/m09-a/model-assets.json"
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))
    profile = EmbeddingProfile(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        manifest_fingerprint(assets), 384, ("zh", "en"), 128, 4, True,
        LOCAL_BACKEND, LOCAL_BACKEND_VERSION, local_runtime_version(),
    )
    return LocalSentenceTransformer(model_directory, profile, assets)
