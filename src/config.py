from base64 import b64decode
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from src.raw_store.credentials import CredentialVault

ROOT = Path(__file__).resolve().parents[1]
MODEL = "jev-1.14.0"
PROVIDERS = {
    "typesafe": (
        "https://api.typesafe.ai/v1/systemone",
        "TYPESAFE_API_KEY",
        "https://console.typesafe.ai/",
    ),
    "jevmodel": (
        "https://jevmodel.org/v1/systemone",
        "JEVMODEL_API_KEY",
        "https://jevmodel.org/zh/pricing/",
    ),
}
SEARCH_KEYS = {"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}
CONNECTOR_ACCOUNTS = {
    "typesafe": ("TypeSafe", "https://console.typesafe.ai/login"),
    "jevmodel": ("JevModel", "https://jevmodel.org/zh/dashboard/"),
    "tavily": ("Tavily", "https://app.tavily.com/home"),
    "brave": ("Brave", "https://api-dashboard.search.brave.com/register"),
}
CONNECTOR_KEYS = {**{name: provider[1] for name, provider in PROVIDERS.items()}, **SEARCH_KEYS}


@dataclass(frozen=True)
class Settings:
    directory: Path
    provider: str = "jevmodel"
    keys: dict = field(default_factory=dict, repr=False)
    review: str = ""
    capacity: int | None = None
    local_reviews: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls):
        base = cls.load_base()
        return base.with_local(CredentialVault(base.directory).read())

    @classmethod
    def load_base(cls):
        load_dotenv(ROOT / ".env", override=False)
        provider = os.getenv("JEV_PROVIDER", "jevmodel").strip().lower()
        if provider not in PROVIDERS:
            raise ValueError("JEV_PROVIDER 仅接受 typesafe 或 jevmodel")
        capacity = os.getenv("JEV_TOKEN_CAPACITY", "").strip()
        if capacity and (not capacity.isdecimal() or int(capacity) <= 0):
            raise ValueError("JEV_TOKEN_CAPACITY 应填写账户已知的正整数额度")
        keys = {name: os.getenv(var, "").strip() for name, var in CONNECTOR_KEYS.items()}
        directory = Path(os.getenv("VOC_DATA_DIR") or ROOT / "runtime")
        return cls(
            directory.resolve(),
            provider,
            keys,
            os.getenv("JEV_REVIEW_FILE", ""),
            int(capacity) if capacity else None,
        )

    def with_local(self, config):
        override = config.get("provider")
        keys = {name: config["keys"].get(name, self.keys.get(name)) or "" for name in CONNECTOR_KEYS}
        return replace(
            self, provider=override if override in PROVIDERS else self.provider,
            keys=keys, local_reviews=config["reviews"],
        )

    def review_status(self):
        try:
            if self.provider in self.local_reviews:
                pair = self.local_reviews[self.provider]
                raw = b64decode(pair["record"], validate=True)
                proof = b64decode(pair["attachment"], validate=True)
                return validate_review(self.provider, raw, proof)
            path = Path(self.review)
            raw = path.read_bytes()
            doc = json.loads(raw)
            if doc.get("provider") == self.provider:
                return validate_review(self.provider, raw, (path.parent / doc["evidence_file"]).read_bytes())
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            pass
        return unapproved_review()

    def account_tag(self, provider=None):
        # Local partition only. Never transmit or expose credential fingerprints.
        name = provider or self.provider
        return hashlib.sha256((name + "\n" + self.keys.get(name, "")).encode()).hexdigest()


def unapproved_review():
    return {"approved": False, "checked_at": None, "review_hash": None}


def validate_review(provider, raw, proof):
    try:
        doc = json.loads(raw)
        checked = datetime.fromisoformat(doc["checked_at"])
        required = ("zdr_enabled",) if provider == "typesafe" else (
            "subprocessors_reviewed", "retention_reviewed",
        )
        if (
            checked.tzinfo is not None and checked <= datetime.now(timezone.utc)
            and doc.get("provider") == provider and doc.get("public_text_approved") is True
            and all(isinstance(doc.get(k), str) and doc[k].strip()
                    for k in ("region", "terms_reference", "reviewer", "evidence_file"))
            and all(doc.get(k) is True for k in required)
            and proof and doc.get("evidence_sha256") == hashlib.sha256(proof).hexdigest()
        ):
            return {
                "approved": True,
                "checked_at": checked.isoformat(),
                "review_hash": hashlib.sha256(raw).hexdigest(),
            }
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        pass
    return unapproved_review()
