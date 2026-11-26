"""Local-only API setup and sanitized provider diagnostics."""

from base64 import b64decode
from contextlib import contextmanager
from dataclasses import replace
import json
import re
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from src.config import (
    CONNECTOR_ACCOUNTS, CONNECTOR_KEYS, PACKYCODE_CONTRACT, PACKYCODE_LIVE_BLOCK,
    PROVIDERS, validate_review,
)
from src.execution.provider_diagnostics import SUMMARY, diagnostic_report, run_probe
from src.raw_store.credentials import VaultError
from src.raw_store.store import Busy, Conflict

CONNECTORS = {
    "typesafe": {
        "docs": "https://docs.typesafe.ai/api/list-models",
        "guide": "登录控制台，选择组织，在 API Keys 创建密钥。公开文本处理请向官方申请零数据留存。",
        "purpose": "用 Jev 对用户原话做结构化判断。",
        "unit": "供应商货币账户",
        "review_docs": "https://help.typesafe.ai/articles/9520184411",
    },
    "jevmodel": {
        "docs": "https://jevmodel.org/zh/docs/",
        "guide": "登录控制台，在 API keys 新建密钥。随后核对数据留存和转发链的审查记录。",
        "purpose": "用 Jev 对用户原话做结构化判断。",
        "unit": "输入 tokens",
    },
    "packycode": {
        "docs": "https://docs.packyapi.com/docs/token/2-group.html",
        "guide": "在 PackyCode 控制台创建绑定 typesafe-officially 分组的独立密钥，在本页保存。",
        "purpose": "Jev SystemOne 候选通道。",
        "unit": "供应商货币账户",
        "review_docs": "https://docs.packyapi.com/docs/tos/service-specific-terms.html",
    },
    "tavily": {
        "docs": "https://docs.tavily.com/documentation/api-reference/endpoint/search",
        "guide": "登录 Tavily 控制台，在 API Keys 创建并复制密钥。",
        "purpose": "发现公开网页，再回源核对许可和原话。",
        "unit": "搜索积分",
    },
    "brave": {
        "docs": "https://api-dashboard.search.brave.com/documentation/guides/authentication",
        "guide": "注册 Brave Search API，启用 Web Search 套餐，再到 API Keys 新建密钥。",
        "purpose": "发现公开网页，再回源核对许可和原话。",
        "unit": "搜索请求",
    },
}
FUTURE = [
    {
        "id": "youtube", "label": "YouTube", "stage": "P0", "status": "PLANNED",
        "signup": "https://console.cloud.google.com/",
        "docs": "https://developers.google.com/youtube/data/guides/authentication",
        "guide": "在 Google Cloud 启用 YouTube Data API v3，从凭证页创建该 API 的密钥。",
        "purpose": "采集符合权限的公开视频评论。", "unit": "配额单位",
    },
    {
        "id": "forms", "label": "Google Forms", "stage": "P1", "status": "PLANNED",
        "signup": "https://console.cloud.google.com/",
        "docs": "https://developers.google.com/workspace/forms/api/quickstart/python",
        "guide": "在 Google Cloud 启用 Forms API，配置 OAuth 同意界面并创建 OAuth 客户端。",
        "purpose": "在账户授权后回收问卷响应。", "unit": "读写请求配额",
    },
]
RECORD_LIMIT = 32 * 1024
ATTACHMENT_LIMIT = 1024 * 1024


class LocalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KeyInput(LocalBody):
    key: SecretStr


class ReviewInput(LocalBody):
    record: str = Field(repr=False)
    attachment: str = Field(repr=False)


class DiagnosticInput(LocalBody):
    request_key: UUID


def body(model, limit, *, label="配置内容或附件", explain=None):
    async def parse(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "请从工作台提交 JSON。")
        buffer = bytearray()
        async for chunk in request.stream():
            if len(buffer) + len(chunk) > limit:
                raise HTTPException(413, f"{label}过大。")
            buffer.extend(chunk)
        try:
            return model.model_validate_json(buffer)
        except (ValidationError, ValueError) as exc:
            message = explain(exc) if explain else "配置格式无效，请检查输入。"
            raise HTTPException(422, message) from None

    return parse


@contextmanager
def edit(local):
    try:
        with local.store.writer():
            yield
    except (Busy, Conflict) as exc:
        raise HTTPException(409, str(exc)) from None
    except VaultError as exc:
        raise HTTPException(503, str(exc)) from None


def known(provider, allowed=CONNECTOR_KEYS):
    if provider not in allowed:
        raise HTTPException(404, "此供应商当前没有可用的本机配置操作。")


def register_setup(app):
    @app.put("/api/setup/{provider}/key")
    def put_key(provider: str, data: KeyInput = Depends(body(KeyInput, 4096))):
        known(provider)
        key = data.key.get_secret_value().strip()
        if not re.fullmatch(r"[!-~]{1,512}", key):
            raise HTTPException(422, "请输入 1 至 512 个无空格的可打印字符。")
        with edit(app.state):
            config = app.state.vault.read()
            previous_key = app.state.settings.with_local(config).keys.get(provider)
            config["keys"][provider] = key
            review = config["reviews"].get(provider)
            if provider == "packycode" and key != previous_key:
                config["reviews"].pop(provider, None)
            elif (provider != "packycode" and not previous_key and isinstance(review, dict)
                    and "account_tag" in review and review["account_tag"] is None):
                review["account_tag"] = app.state.settings.with_local(config).account_tag(provider)
            app.state.vault.write(config)
        return {"configured": True}

    @app.delete("/api/setup/{provider}/key")
    def delete_key(provider: str):
        known(provider)
        with edit(app.state):
            config = app.state.vault.read()
            if app.state.settings.keys.get(provider):
                config["keys"][provider] = None
            else:
                config["keys"].pop(provider, None)
            if provider == "packycode":
                config["reviews"].pop(provider, None)
            app.state.vault.write(config)
        return {"configured": False}

    @app.put("/api/setup/jev/{provider}")
    def select_provider(provider: str):
        known(provider, PROVIDERS)
        with edit(app.state):
            config = app.state.vault.read()
            config["provider"] = provider
            app.state.vault.write(config)
        return {"provider": provider}

    @app.put("/api/setup/{provider}/review")
    def put_review(provider: str, data: ReviewInput = Depends(body(ReviewInput, 1_500_000))):
        known(provider, PROVIDERS)
        try:
            raw, proof = b64decode(data.record, validate=True), b64decode(data.attachment, validate=True)
        except (ValueError, TypeError):
            raise HTTPException(422, "请同时选择审查 JSON 和它对应的证明附件。") from None
        if len(raw) > RECORD_LIMIT or len(proof) > ATTACHMENT_LIMIT:
            raise HTTPException(413, "审查记录最多 32 KB，证明附件最多 1 MB。")
        review = validate_review(provider, raw, proof)
        if not review["approved"]:
            raise HTTPException(422, "审批字段、供应商或附件摘要未通过核验，请核对后重新导入。")
        # Persist the original signed-off documents locally. Ignore the JSON's file path.
        with edit(app.state):
            config = app.state.vault.read()
            settings = app.state.settings.with_local(config)
            account = settings.account_tag(provider) if settings.keys.get(provider) else None
            if provider == "packycode" and account is None:
                raise HTTPException(409, "请先保存当前 PackyCode 凭证，再导入此账户的审查材料。")
            config["reviews"][provider] = {**data.model_dump(), "account_tag": account}
            app.state.vault.write(config)
        return {"approved": True, "checked_at": review["checked_at"]}

    @app.post("/api/setup/wizard")
    def dismiss_wizard():
        with edit(app.state):
            config = app.state.vault.read()
            config["wizard_seen"] = True
            app.state.vault.write(config)
        return {"wizard_seen": True}

    @app.post("/api/setup/{provider}/diagnostics")
    def diagnose(provider: str, data: DiagnosticInput = Depends(body(DiagnosticInput, 1024))):
        known(provider)
        if provider == "packycode":
            raise HTTPException(409, PACKYCODE_LIVE_BLOCK)
        with edit(app.state):
            settings = app.state.settings.with_local(app.state.vault.read())
            return run_probe(settings, app.state.diagnostics, provider, str(data.request_key))


def recent_tests(store, cfg, provider):
    return [
        diagnostic_report(row) for row in store.rows(
            "SELECT r.id AS run_id,e.* FROM evidence e JOIN attempts a ON a.id=e.attempt_id "
            "JOIN runs r ON r.id=a.run_id WHERE r.account_tag=? AND e.name=? "
            "AND e.mode='provider_connection_diagnostic' ORDER BY e.id DESC LIMIT 5",
            (cfg.account_tag(provider), SUMMARY),
        )
    ]


def search_quota(store, cfg, provider, latest):
    value = "json_extract(e.response_json,'$.credits')" if provider == "tavily" else "1"
    source = (
        " FROM evidence e JOIN attempts a ON a.id=e.attempt_id JOIN runs r ON r.id=a.run_id "
        "WHERE r.account_tag=? AND e.name=? AND e.mode='provider_connection_diagnostic'"
    )
    args = (cfg.account_tag(provider), SUMMARY)
    total = store.one(
        f"SELECT COUNT(*) AS n,COUNT({value}) AS metered,SUM({value}) AS used"
        + source + " AND e.status_code=200", args,
    )
    synced = store.one(
        "SELECT e.checked_at" + source
        + " AND json_extract(e.response_json,'$.monthly_remaining') IS NOT NULL ORDER BY e.id DESC LIMIT 1",
        args,
    )
    return {
        "remaining": latest.get("monthly_remaining"),
        "capacity": latest.get("monthly_limit"),
        "last_synced_at": synced["checked_at"] if synced else None,
        "local_usage": total["used"] if total["n"] and total["n"] == total["metered"] else None,
        "usage_scope": "本机诊断",
    }


def setup_view(base, cfg, local, diagnostics, jev_quota, error=None):
    entries = []
    for name, env_var in CONNECTOR_KEYS.items():
        label, signup = CONNECTOR_ACCOUNTS[name]
        is_jev = name in PROVIDERS
        configured = bool(cfg.keys.get(name))
        review_state = replace(cfg, provider=name).review_status() if is_jev else None
        history = recent_tests(diagnostics, cfg, name) if not error else []
        last = history[0] if history else {}
        if not configured:
            status = "NOT_CONFIGURED"
        elif review_state is not None and not review_state["approved"]:
            status = "REVIEW_REQUIRED"
        else:
            status = last.get("status", "NOT_TESTED")
            if status == "REVIEW_REQUIRED":
                status = "NOT_TESTED"
        if is_jev:
            quota = jev_quota(replace(cfg, provider=name))
            usage = {
                "remaining": quota["remaining"], "capacity": quota["capacity"],
                "last_synced_at": quota["last_synced_at"], "local_usage": quota["input_tokens"],
                "usage_scope": "本机验收与诊断", "warning": quota["warning"],
            }
            if name == "packycode":
                usage.update(
                    candidate_contract=PACKYCODE_CONTRACT, billing=quota["billing"],
                    live_test_allowed=False, purchase_url=quota["purchase_url"],
                )
        else:
            usage = search_quota(diagnostics, cfg, name, last)
        entries.append({
            "id": name, "label": label, "signup": signup, "env_var": env_var,
            **CONNECTORS[name], **usage,
            "stage": "P0-0", "group": "jev" if is_jev else "search",
            "selected": is_jev and cfg.provider == name,
            "configured": configured, "status": status,
            "credential_source": (
                "local" if local["keys"].get(name) else "environment" if configured and base.keys.get(name)
                else "disabled" if name in local["keys"] else None
            ),
            "review": {"approved": review_state["approved"], "checked_at": review_state["checked_at"]}
            if review_state is not None else None,
            "recent_tests": history,
        })
    selected = next(entry for entry in entries if entry["selected"])
    return {
        "providers": entries, "future": FUTURE, "wizard_seen": local.get("wizard_seen", False),
        "error": error, "provider": cfg.provider,
        "prerequisites": {
            "jev_key": selected["configured"], "jev_review": selected["review"]["approved"],
            "search_key": any(p["configured"] for p in entries if p["group"] == "search"),
        },
    }
