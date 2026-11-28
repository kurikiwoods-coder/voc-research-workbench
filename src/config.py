from base64 import b64decode
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from src.edition_policy import Deployment, Edition, LocalOwner, legacy_execution_allowed
from src.raw_store.credentials import CredentialVault
from src.raw_store.runtime_binding import bind_directory

ROOT = Path(__file__).resolve().parents[1]
MODEL = "jev-1.14.0"
PACKYCODE_CONTRACT = {
    "group": "typesafe-officially",
    "model": MODEL,
    "base_url": "https://cf.api.fan",
    "endpoint": "https://cf.api.fan/v1/systemone",
    "endpoint_evidence": "DOCUMENTED",
    "live_status": "NOT_TESTED",
    "input_usd_per_million": "0.294",
    "output_usd_per_million": "0",
    "rate_source": "PackyAPI 公开价目倍率与负责人配置截图，实际账户扣费待核验",
}
PACKYCODE_LIVE_BLOCK = "PackyCode 真实调用尚未放行，请先完成本账户供应商审查及预检准备。"
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
    "packycode": (
        PACKYCODE_CONTRACT["endpoint"],
        "PACKYCODE_API_KEY",
        "https://www.packyapi.ai/pricing",
    ),
}
SEARCH_KEYS = {"tavily": "TAVILY_API_KEY", "brave": "BRAVE_API_KEY"}
CONNECTOR_ACCOUNTS = {
    "typesafe": ("TypeSafe", "https://console.typesafe.ai/login"),
    "jevmodel": ("JevModel", "https://jevmodel.org/zh/dashboard/"),
    "packycode": ("PackyCode", "https://www.packyapi.ai/register"),
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
    local_key_overrides: frozenset[str] = field(default_factory=frozenset, repr=False)

    edition: Edition = Edition.BUSINESS
    deployment: Deployment = Deployment.LOCAL
    personal_owner: LocalOwner | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.edition not in set(Edition) or self.deployment not in set(Deployment):
            raise ValueError("VOC_EDITION 或 VOC_DEPLOYMENT 设置无效。")
        if self.edition == Edition.PERSONAL and self.deployment == Deployment.LOCAL:
            if not isinstance(self.personal_owner, LocalOwner):
                raise ValueError("个人版本机启动需要可信 Owner 配置。")
        elif self.personal_owner is not None:
            raise ValueError("当前版本或部署方式不能加载个人 Owner 配置。")

    @classmethod
    def load(cls):
        base = cls.load_base()
        if not legacy_execution_allowed(base):
            return base
        directory = bind_directory(base.directory, base.edition)
        return base.with_local(CredentialVault(directory).read())

    @classmethod
    def load_base(cls):
        load_dotenv(ROOT / ".env", override=False)
        directory_config = os.getenv("VOC_DATA_DIR")
        directory = Path(directory_config or ROOT / "runtime")
        try:
            edition = Edition(os.getenv("VOC_EDITION", "BUSINESS"))
            deployment = Deployment(os.getenv("VOC_DEPLOYMENT", "LOCAL"))
        except ValueError:
            raise ValueError("VOC_EDITION 或 VOC_DEPLOYMENT 设置无效。") from None
        owner = None
        if edition == Edition.PERSONAL and deployment == Deployment.LOCAL:
            if not directory_config or not directory.is_absolute():
                raise ValueError("个人版需要专用的绝对 VOC_DATA_DIR 路径。")
            owner = LocalOwner.from_environment(os.environ)
        if edition != Edition.BUSINESS or deployment != Deployment.LOCAL:
            return cls(directory.resolve(), edition=edition, deployment=deployment, personal_owner=owner)
        provider = os.getenv("JEV_PROVIDER", "jevmodel").strip().lower()
        if provider not in PROVIDERS:
            raise ValueError("JEV_PROVIDER 仅接受 " + "、".join(PROVIDERS))
        capacity = os.getenv("JEV_TOKEN_CAPACITY", "").strip()
        if capacity and (not capacity.isdecimal() or int(capacity) <= 0):
            raise ValueError("JEV_TOKEN_CAPACITY 应填写账户已知的正整数额度")
        keys = {name: os.getenv(var, "").strip() for name, var in CONNECTOR_KEYS.items()}
        return cls(
            directory.resolve(), provider, keys, os.getenv("JEV_REVIEW_FILE", ""),
            int(capacity) if capacity else None,
        )

    def with_local(self, config):
        override = config.get("provider")
        keys = {name: config["keys"].get(name, self.keys.get(name)) or "" for name in CONNECTOR_KEYS}
        return replace(
            self, provider=override if override in PROVIDERS else self.provider,
            keys=keys, local_reviews=config["reviews"],
            local_key_overrides=frozenset(name for name in CONNECTOR_KEYS if keys[name] != (self.keys.get(name) or "")),
        )

    def review_status(self):
        if not legacy_execution_allowed(self):
            return unapproved_review()
        try:
            if self.provider in self.local_reviews:
                pair = self.local_reviews[self.provider]
                if pair.get("account_tag") != self.account_tag():
                    return unapproved_review()
                raw = b64decode(pair["record"], validate=True)
                proof = b64decode(pair["attachment"], validate=True)
                return validate_review(self.provider, raw, proof)
            if self.provider == "packycode" or self.provider in self.local_key_overrides:
                return unapproved_review()
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
        if provider == "packycode":
            required += (
                "training_use_reviewed", "deletion_reviewed", "upstream_reviewed", "zdr_terms_reviewed",
            )
            if (
                any(doc.get(key) != PACKYCODE_CONTRACT[key] for key in ("group", "model", "endpoint"))
                or not isinstance(doc.get("upstream_reference"), str) or not doc["upstream_reference"].strip()
            ):
                return unapproved_review()
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
