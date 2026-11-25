"""C4 HTTP and browser regression against real Uvicorn and synthetic SQLite."""

from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit
from uuid import uuid4

from playwright.sync_api import expect

from corpus_browser import add_batch, open_record, verify_quote
from src.raw_store.mentions import EvidenceInterval, MentionStore
from src.raw_store.relations import RelationGrant, RelationStore
from src.raw_store.store import Store
from test_m06_constraints import command, insert, registry, seal_registry
from test_m06_mentions import BASIS, CATALOG, PRODUCT_A, PRODUCT_B, MentionTests
from test_m06_relations_transactions import INTENT, MAIN_TASK, OTHER_TASK, PRIMARY, SECONDARY


CANDIDATE = "INTENT-UNPARENTED"
PRODUCTS = {PRODUCT_A: "电子秤", PRODUCT_B: "空气炸锅"}
FIXTURES = {
    PRODUCT_A: ("秤的合成来源.csv", "合成夹具：断网后仍想称重。<b>测试文本</b>"),
    PRODUCT_B: ("炸锅的合成来源.csv", "合成夹具：断网后仍能操作空气炸锅。"),
}
GRANT_FILE = "synthetic-c4-study.txt"


def relation_fixture_grants(directory):
    path = Path(directory) / GRANT_FILE
    if not path.is_file():
        return ()
    return tuple(RelationGrant(
        "synthetic-reviewer", "project_reviewer", "synthetic-owner", "local:browser-fixture",
        "2000-01-01T00:00:00Z", "2099-01-01T00:00:00Z",
        frozenset({"attribute", "evidence", "read", "validate"}), study_id,
    ) for study_id in path.read_text("ascii").splitlines())


def project(page, base, headers, name):
    response = page.request.post(f"{base}/api/studies", headers=headers, data={
        "name": name, "request_key": str(uuid4()), "scope": {"mode": "open", "topic": "合成断网场景"},
    })
    expect(response).to_be_ok()
    result = response.json()
    response = page.request.post(
        f"{base}/api/studies/{result['study_id']}/scopes/{result['scope']['scope_id']}/freeze", headers=headers,
    )
    expect(response).to_be_ok()
    return response.json()


def definitions_and_mapping(store, study, scope, supports):
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        registry(db, CATALOG)
        for product, name in PRODUCTS.items():
            insert(db, "m06_product", registry_version=CATALOG, product_category_id=product, name=name,
                   description="", parent_id=None, status="confirmed", version=CATALOG)
        for task in (MAIN_TASK, OTHER_TASK):
            insert(db, "m06_task", registry_version=CATALOG, category_id=task.category_id, name=task.name,
                   definition=task.definition, inclusion_criteria=task.inclusion_criteria,
                   exclusion_criteria=task.exclusion_criteria, discovery="preset", lifecycle_status="confirmed",
                   version=CATALOG)
        for intent_id, name, status, primary in (
            (INTENT.intent_id, INTENT.name, "confirmed", PRIMARY),
            (CANDIDATE, "合成待审意图", "pending_parent", None),
        ):
            insert(db, "m06_intent", registry_version=CATALOG, intent_id=intent_id, name=name,
                   definition="合成定义", inclusion_criteria="合成纳入", exclusion_criteria="合成排除",
                   lifecycle_status=status, primary_category_id=primary, survey_validation_status="unvalidated",
                   version=CATALOG)
        for task in (PRIMARY, SECONDARY):
            insert(db, "m06_intent_task", registry_version=CATALOG, intent_id=INTENT.intent_id,
                   category_id=task, is_primary=int(task == PRIMARY))
        for member in supports:
            insert(db, "m06_representative", registry_version=CATALOG, intent_id=INTENT.intent_id,
                   study_id=study, segment_revision=1, mention_id=member["mention_id"],
                   evidence_id=member["evidence_ids"][0])
        seal_registry(db, CATALOG)
        command(db, "c4-browser-mapping", study)
        for product in PRODUCTS:
            insert(db, "m06_scope_product", study_id=study, scope_id=scope, mapping_revision=1,
                   registry_version=CATALOG, product_category_id=product)
        insert(db, "m06_scope_binding", study_id=study, scope_id=scope, mapping_revision=1,
               previous_revision=None, registry_version=CATALOG, mapping_status="mapped_product",
               scope_reviewer_ref="synthetic-scope-review", catalog_reviewer_ref="synthetic-catalog-review",
               basis_ref=BASIS, command_id="c4-browser-mapping")


def seed(page, base, headers, directory, fixture):
    study = fixture["study_id"]
    scope = fixture["scope"]["scope_id"]
    store = Store(Path(directory))
    (Path(directory) / GRANT_FILE).write_text(study, encoding="ascii")
    quotes = {}
    for product, (filename, text) in FIXTURES.items():
        batch = add_batch(page, base, fixture, filename, f"https://synthetic.invalid/{product}", text=text)
        page.goto(f"{base}/#corpus/{study}")
        expect(page.get_by_role("heading", name="原始语料库", exact=True)).to_be_visible()
        wizard = page.get_by_role("dialog")
        if wizard.is_visible():
            wizard.get_by_role("button", name="稍后配置").click()
        open_record(page, filename)
        verify_quote(page, text)
        record = unquote(urlsplit(page.url).fragment.split("/")[-1])
        quotes[product] = (batch, EvidenceInterval(record, sha256(text.encode()).hexdigest(), 0, len(text)))
    granted = lambda candidate, _: "synthetic-reviewer" if candidate == study else None
    mentions = MentionStore(store, authorize=granted)
    representatives = tuple(MentionTests.member(product, quote, segment_no=index)
                            for index, (product, (_, quote)) in enumerate(quotes.items(), 1))
    # A third independent representative runs through the same M05 review path.
    extra_file = "关系锚点 合成.csv"
    extra_text = "合成代表：我想在离线时继续使用。"
    add_batch(page, base, fixture, extra_file, "https://synthetic.invalid/third", text=extra_text)
    page.goto(f"{base}/#corpus/{study}")
    open_record(page, extra_file)
    verify_quote(page, extra_text)
    record = unquote(urlsplit(page.url).fragment.split("/")[-1])
    interval = EvidenceInterval(record, sha256(extra_text.encode()).hexdigest(), 0, len(extra_text))
    representatives += (MentionTests.member("THIRD", interval, segment_no=3),)
    first = mentions.publish_revision(study, key="c4-browser-r1", expected_revision=0,
                                      rule_version="synthetic-browser-segments", members=representatives)
    definitions_and_mapping(store, study, scope, first["members"])
    refreshed = tuple(MentionTests.member(member.ref, member.supports[0].interval,
                                          segment_no=member.supports[0].segment_no,
                                          mention_id=saved["mention_id"])
                      for member, saved in zip(representatives, first["members"], strict=True))
    result = mentions.publish_revision(
        study, key="c4-browser-r2", expected_revision=1, rule_version="synthetic-browser-segments",
        members=refreshed, proposals=tuple(MentionTests.proposal(product, quote, product)
                                          for product, (_, quote) in quotes.items()),
    )
    by_product = dict(zip((*quotes, "THIRD"), result["members"], strict=True))
    mentions.review_products(study, key="c4-browser-review", expected_revision=2,
                             decisions=tuple(MentionTests.decision(member, product)
                                             for product, member in by_product.items() if product in quotes))
    relations = RelationStore(store, grants=lambda: relation_fixture_grants(directory))
    supports = tuple((member["mention_id"], member["evidence_ids"][0]) for member in by_product.values())
    relations.attribute(study, key="c4-browser-attribute", expected_registry_version=CATALOG,
                        expected_segment_revision=2, intent_id=INTENT.intent_id, supports=supports)
    return quotes, by_product


def check_http(page, base, headers, study, scope, other, quotes, members):
    api = f"{base}/api"

    def get(path, expected=200, **params):
        response = page.request.get(api + path + ("?" + urlencode(params, doseq=True) if params else ""))
        assert response.status == expected, (response.url, response.status, response.text())
        assert response.headers["cache-control"] == "no-store"
        return response.json()

    products = get("/product-categories", limit=1)
    assert get("/product-categories", registry_version=CATALOG, limit=1,
               cursor=products["next_cursor"])["items"][0] != products["items"][0]
    get("/product-categories", 409, status="confirmed", limit=1, cursor=products["next_cursor"])
    get("/product-categories", 400, cursor="invalid-cursor")
    get(f"/product-categories/{PRODUCT_A}", registry_version=CATALOG)
    get("/categories")
    get(f"/categories/{PRIMARY}", registry_version=CATALOG)
    assert get("/intents", lifecycle_status="pending_parent")["items"][0]["primary_category_id"] is None
    assert get(f"/intents/{CANDIDATE}", registry_version=CATALOG)["lifecycle_status"] == "pending_parent"
    primary = get(f"/categories/{PRIMARY}/intents", intent_id=INTENT.intent_id)["items"]
    tasks = get(f"/intents/{INTENT.intent_id}/categories")["items"]
    assert tasks[0:1] == primary and [item["role"] for item in tasks] == ["primary", "secondary"]
    assert get(f"/intents/{INTENT.intent_id}/categories", category_id=SECONDARY)["items"] == tasks[1:]
    assert {item["study_id"] for item in get("/studies/relations/projects")["items"]} == {study}
    path = f"/intents/{INTENT.intent_id}/product-categories"
    filters = {"study_id": study, "registry_version": CATALOG, "segment_revision": 2}
    reverse = get(path, **filters)["items"]
    assert {row["product_category_id"] for row in reverse} == set(PRODUCTS)
    for product in PRODUCTS:
        forward = get(f"/product-categories/{product}/intents", **filters)["items"]
        back = next(row for row in reverse if row["product_category_id"] == product)
        assert len(forward) == 1 and forward[0]["intent_id"] == INTENT.intent_id
        assert (forward[0]["distinct_mention_n"], back["distinct_mention_n"]) == (1, 1)
        assert forward[0]["evidence_refs"] == back["evidence_refs"]
    queried = get(path, **filters, scope_id=scope, scope_version="v1", mapping_revision=1,
                  catalog_version=CATALOG, batch_id=[quotes[PRODUCT_A][0]], source=["forum", "review"],
                  **{"from": "2026-11-01T08:00:00+08:00", "to": "2026-11-02"})
    assert [row["product_category_id"] for row in queried["items"]] == [PRODUCT_A]
    assert queried["filter_echo"]["from"] == "2026-11-01T00:00:00Z"
    assert queried["resolved_versions"]["scope_mappings"][0]["mapping_revision"] == 1
    excluded = get(path, **filters, to="2026-11-01")
    assert excluded["items"] == []
    get(path, 400, **filters, scope_id=scope)
    get(path, 422, segment_revision=2)
    get(path, 404, **(filters | {"study_id": other}))
    unavailable = get(path, **filters, mode="formal")
    assert unavailable["availability"] == "unavailable" and unavailable["counts"] is None
    assert "G1_BLOCKED" in unavailable["reasons"] and unavailable["items"] == []
    assert get(path, **filters, mode="synthetic")["items"] == reverse
    member = members[PRODUCT_A]
    mention, evidence = member["mention_id"], member["evidence_ids"][0]
    assert get(f"/studies/{study}/mentions", segment_revision=1)["items"]
    assert get(f"/studies/{study}/mentions/{mention}", segment_revision=2)["mention_id"] == mention
    drill = f"/studies/{study}/mentions/{mention}/evidence/{evidence}"
    item = get(drill, segment_revision=2)
    assert item["excerpt"] == FIXTURES[PRODUCT_A][1] and item["record_id"] == quotes[PRODUCT_A][1].record_id
    assert item["line_number"] == 2 and item["license_status"] == "authorized"
    assert item["research_eligible"] is False and item["outbound_allowed"] is False
    get(f"/studies/{other}/mentions/{mention}/evidence/{evidence}", 404, segment_revision=2)
    payload = {"operation": "confirm", "candidate_intent_id": CANDIDATE, "expected_registry_version": CATALOG,
               "expected_segment_revision": 2, "representative_refs": [{"mention_id": mention, "evidence_id": evidence}]}
    validate = f"{api}/studies/{study}/relations/validate"
    reply = page.request.post(validate, headers=headers, data=payload)
    expect(reply).to_be_ok()
    result = reply.json()
    assert not result["valid"] and result["candidate_allowed"]
    assert {"PRIMARY_REQUIRED", "REPRESENTATIVES_INSUFFICIENT"} <= set(result["violations"])
    assert page.request.post(validate, headers=headers, data=payload | {"expected_registry_version": None}).status == 409
    assert page.request.post(validate, data=payload).status == 403
    forged = page.request.get(f"{api}/studies/{other}/mentions", headers={"X-VOC-Role": "owner"})
    assert forged.status == 404
    reflected = page.request.get(f"{api}/studies/{study}/mentions", params={"unknown": "synthetic-no-reflection"})
    assert reflected.status == 422 and "synthetic-no-reflection" not in reflected.text()
    page_one = get(path, **filters, limit=1)
    cursor = page_one["next_cursor"]
    assert cursor
    print("C4 localhost HTTP E2E passed: exact versions, bidirectional witnesses, filters, cursors, preflight and access.")
    return drill, path, filters, cursor


def check_scope_availability(page, base, headers, output, directory):
    fixture = project(page, base, headers, "C4 冻结范围合成回归")
    study = fixture["study_id"]
    study_url = f"{base}/api/studies/{study}"
    first_scope = fixture["scope"]["scope_id"]
    response = page.request.put(study_url, headers=headers, data={
        "name": fixture["name"], "revision": fixture["revision"],
        "scope": {"mode": "open", "topic": "合成非产品范围"},
    })
    expect(response).to_be_ok()
    second = response.json()
    second_scope = second["scope"]["scope_id"]
    expect(page.request.post(f"{study_url}/scopes/{second_scope}/freeze", headers=headers)).to_be_ok()
    expect(page.request.post(f"{study_url}/select", headers=headers)).to_be_ok()
    with (Path(directory) / GRANT_FILE).open("a", encoding="ascii") as grants:
        grants.write("\n" + study)
    store = Store(Path(directory))
    mapping = "c4-browser-non-product"
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        command(db, mapping, study)
        insert(db, "m06_scope_binding", study_id=study, scope_id=second_scope, mapping_revision=1,
               previous_revision=None, registry_version=CATALOG, mapping_status="non_product",
               scope_reviewer_ref="synthetic-scope-review", catalog_reviewer_ref="synthetic-catalog-review",
               basis_ref=BASIS, command_id=mapping)

    members = []
    for scoped_fixture, filename, segments in (
        (fixture, "映射待定 合成.csv", [f"合成原话 {number:02d}。" for number in range(26)]),
        (second, "非产品范围 合成.csv", ["合成非产品原话。"]),
    ):
        text = "".join(segments)
        add_batch(page, base, scoped_fixture, filename,
                  f"https://synthetic.invalid/scope/{scoped_fixture['scope']['scope_id']}", text=text)
        page.goto(f"{base}/#corpus/{study}")
        open_record(page, filename)
        verify_quote(page, text)
        record = unquote(urlsplit(page.url).fragment.split("/")[-1])
        digest = sha256(text.encode()).hexdigest()
        start = 0
        for segment in segments:
            end = start + len(segment)
            number = len(members) + 1
            members.append(MentionTests.member(f"SCOPE-{number}", EvidenceInterval(record, digest, start, end),
                                               segment_no=number))
            start = end
    mentions = MentionStore(store, authorize=lambda candidate, _: "synthetic-reviewer" if candidate == study else None)
    mentions.publish_revision(study, key="c4-browser-scopes-r1", expected_revision=0,
                              rule_version="synthetic-browser-segments", members=members)
    response = page.request.get(f"{study_url}/mentions", params={"registry_version": CATALOG})
    expect(response).to_be_ok()
    result = response.json()
    assert result["availability"] == "available" and len(result["items"]) == 25 and result["next_cursor"]
    assert {row["scope_id"]: row["mapping_status"] for row in result["resolved_versions"]["scope_mappings"]} == {
        first_scope: "unresolved", second_scope: "non_product",
    }

    page.goto(base + "/#relations")
    unavailable = page.get_by_text("冻结范围的产品映射未解析", exact=True)
    empty = page.get_by_text("暂无符合条件的关系。", exact=True)
    next_button = page.locator('[data-relation-action="next"]')
    expect(unavailable).to_be_visible()
    expect(empty).to_have_count(0)
    expect(next_button).to_be_hidden()
    page.screenshot(path=str(output / "c4-unresolved-scope.png"), full_page=True)
    scope = page.get_by_label("冻结研究范围", exact=True)
    scope.select_option(label=f"v2 · 映射版 1 · 目录 {CATALOG} · {second_scope}")
    expect(empty).to_be_visible()
    expect(unavailable).to_have_count(0)
    expect(next_button).to_be_hidden()
    print("C4 Chromium scope E2E passed: unavailable, valid empty scope, and cursor suppression.")


def relations_browser_checks(browser, base, output, directory):
    base = base.rstrip("/")
    headers = {"Origin": base, "X-VOC-Action": "connectivity"}
    page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="zh-CN")
    errors, outbound = [], []

    def local_only(route):
        if urlsplit(route.request.url).netloc == urlsplit(base).netloc:
            route.continue_()
        else:
            outbound.append(route.request.url)
            route.abort()

    page.route("**/*", local_only)
    page.on("pageerror", lambda error: errors.append(str(error)))
    fixture = project(page, base, headers, "C4 合成关系回归")
    other = project(page, base, headers, "C4 未获授权合成项目")
    study, scope = fixture["study_id"], fixture["scope"]["scope_id"]
    quotes, members = seed(page, base, headers, directory, fixture)
    drill, path, filters, cursor = check_http(page, base, headers, study, scope, other["study_id"], quotes, members)
    grant_file = Path(directory) / GRANT_FILE
    grant_file.write_text("", encoding="ascii")
    try:
        restricted = page.request.get(f"{base}/api{path}", params={**filters, "limit": 1, "cursor": cursor})
        missing = page.request.get(f"{base}/api{path}", params={**filters, "study_id": str(uuid4()), "limit": 1})
        assert restricted.status == missing.status == 404 and restricted.json() == missing.json()
        denied = page.request.get(f"{base}/api{drill}", params={"segment_revision": 2})
        assert denied.status == 404 and FIXTURES[PRODUCT_A][1] not in denied.text()
    finally:
        grant_file.write_text(study, encoding="ascii")
    assert page.request.get(f"{base}/api{drill}", params={"segment_revision": 2}).ok
    page.goto(base + "/#relations")
    expect(page.get_by_role("heading", name="三层关系", exact=True)).to_be_visible()
    product = page.get_by_label("产品品类", exact=True)
    expect(page.get_by_role("heading", name="电子秤 → 离线使用", exact=True)).to_be_visible()
    product.select_option(PRODUCT_A)
    expect(page.get_by_role("heading", name=INTENT.name, exact=True)).to_be_visible()
    expect(page.get_by_text("主任务", exact=False).filter(has_text=MAIN_TASK.name)).to_be_visible()
    expect(page.get_by_text("次任务 " + OTHER_TASK.name, exact=True)).to_be_visible()
    page.screenshot(path=str(output / "c4-relations.png"), full_page=True)
    evidence = page.get_by_role("button", name="查看证据 1", exact=True)
    dialog = page.get_by_role("dialog", name="原话证据")
    evidence.press("Enter")
    expect(dialog.locator("blockquote")).to_have_text(FIXTURES[PRODUCT_A][1])
    expect(dialog.locator("blockquote b")).to_have_count(0)
    expect(dialog.get_by_role("link", name="查看第 2 行")).to_be_visible()
    page.screenshot(path=str(output / "c4-evidence.png"))
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(evidence).to_be_focused()
    assert FIXTURES[PRODUCT_A][1] not in page.content()
    direction = page.get_by_label("关系方向", exact=True)
    direction.select_option("intent-task")
    expect(page.get_by_text("候选缺主任务", exact=True)).to_be_visible()
    page.get_by_label("用户意图", exact=True).select_option(INTENT.intent_id)
    expect(page.get_by_role("heading", name=MAIN_TASK.name, exact=True)).to_be_visible()
    expect(page.get_by_text("主任务 · 已确认", exact=True)).to_be_visible()
    expect(page.get_by_text("次任务 · 已确认", exact=True)).to_be_visible()
    direction.select_option("intent-product")
    expect(page.get_by_role("heading", name=PRODUCTS[PRODUCT_A], exact=True)).to_be_visible()
    for width in (390, 320):
        page.set_viewport_size({"width": width, "height": 844})
        evidence.click()
        expect(dialog.locator("blockquote")).to_have_text(FIXTURES[PRODUCT_A][1])
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert dialog.evaluate("(element) => element.scrollWidth <= element.clientWidth")
        page.screenshot(path=str(output / f"c4-mobile-{width}.png"))
        dialog.get_by_role("button", name="返回关系").click()
        expect(evidence).to_be_focused()
    assert page.request.post(
        f"{base}/api/imports/{study}/batches/{quotes[PRODUCT_A][0]}/revoke", headers=headers,
    ).ok
    evidence.click()
    expect(dialog).to_be_hidden()
    expect(page.get_by_text("原话已失格或当前访问受限", exact=False)).to_be_visible()
    assert FIXTURES[PRODUCT_A][1] not in page.content()
    page.screenshot(path=str(output / "c4-revoked.png"), full_page=True)
    expired = page.request.get(f"{base}/api{drill}", params={"segment_revision": 2})
    assert expired.status == 409 and FIXTURES[PRODUCT_A][1] not in expired.text()
    stale = page.request.get(f"{base}/api{path}", params={**filters, "limit": 1, "cursor": cursor})
    assert stale.status == 409 and FIXTURES[PRODUCT_A][1] not in stale.text()
    page.get_by_label("查询模式", exact=True).select_option("formal")
    expect(page.get_by_text("G-1 尚未通过", exact=False)).to_be_visible()
    page.set_viewport_size({"width": 1440, "height": 960})
    check_scope_availability(page, base, headers, output, directory)
    assert not errors, errors
    assert not outbound, outbound
    page.close()
    print("C4 Chromium E2E passed: relationship browsing, candidate, keyboard, 320/390px and revocation.")
