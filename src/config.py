from dataclasses import dataclass, field
import json
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

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


@dataclass(frozen=True)
class Settings:
    directory: Path
    provider: str = "jevmodel"
    keys: dict = field(default_factory=dict, repr=False)
    review: str = ""
    capacity: int | None = None

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        provider = os.getenv("JEV_PROVIDER", "jevmodel").strip().lower()
        if provider not in PROVIDERS:
            raise ValueError("JEV_PROVIDER 仅接受 typesafe 或 jevmodel")
        capacity = os.getenv("JEV_TOKEN_CAPACITY", "").strip()
        if capacity and (not capacity.isdecimal() or int(capacity) <= 0):
            raise ValueError("JEV_TOKEN_CAPACITY 应填写账户已知的正整数额度")
        variables = {provider: PROVIDERS[provider][1], **SEARCH_KEYS}
        keys = {name: os.getenv(var, "").strip() for name, var in variables.items()}
        directory = Path(os.getenv("VOC_DATA_DIR") or ROOT / "runtime")
        return cls(
            directory.resolve(),
            provider,
            keys,
            os.getenv("JEV_REVIEW_FILE", ""),
            int(capacity) if capacity else None,
        )

    def review_status(self):
        from datetime import datetime, timezone

        try:
            path = Path(self.review)
            raw = path.read_bytes()
            doc = json.loads(raw)
            checked = datetime.fromisoformat(doc["checked_at"])
            valid = checked.tzinfo is not None and checked <= datetime.now(timezone.utc)
            valid = (
                valid
                and doc.get("provider") == self.provider
                and doc.get("public_text_approved") is True
            )
            valid = valid and all(
                isinstance(doc.get(k), str) and doc[k].strip()
                for k in ("region", "terms_reference", "reviewer", "evidence_file")
            )
            proof = (path.parent / doc["evidence_file"]).read_bytes()
            valid = (
                valid and bool(proof) and doc.get("evidence_sha256") == hashlib.sha256(proof).hexdigest()
            )
            if self.provider == "typesafe":
                valid = valid and doc.get("zdr_enabled") is True
            else:
                valid = (
                    valid
                    and doc.get("subprocessors_reviewed") is True
                    and doc.get("retention_reviewed") is True
                )
            if valid:
                return {
                    "approved": True,
                    "checked_at": doc["checked_at"],
                    "review_hash": hashlib.sha256(raw).hexdigest(),
                }
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return {"approved": False, "checked_at": None, "review_hash": None}

    def account_tag(self):
        # Local partition only. Never transmit or expose credential fingerprints.
        return hashlib.sha256(
            (self.provider + "\n" + self.keys.get(self.provider, "")).encode()
        ).hexdigest()
