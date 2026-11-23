from src.config import MODEL
from src.discovery.recall import test_cross_category_recall
from src.execution.jev import call_shards
from src.execution.transport import ENDPOINTS, Denied, Response, failure, network, outbound
from src.ingestion.public_source import discover
from src.raw_store.store import Store

CODES = [f"C0-{n}" for n in range(1,7)]


def test_isolation_drill():
    calls = []
    def witness(*args):
        calls.append(1)
        return Response(200,{})
    denied = 0
    label_sets = [{"cx_internal"},{"internal_confidential"},{"public_approved","cx_internal"},
                  {"public_approved","internal_confidential"},{"unreviewed"},set()]
    for labels in label_sets:
        for channel in ENDPOINTS:
            try:
                outbound(channel,labels=labels,body={"test":"synthetic"},transport=witness)
            except Denied:
                denied += 1
    denied_transport = len(calls)
    outbound("tavily",labels={"public_approved"},transport=witness)
    outcomes = {}
    expected = {None:"offline",401:"invalid_key",402:"insufficient_balance",422:"invalid_contract",429:"rate_limited",502:"upstream_error"}
    for code in expected:
        def inject(*args):
            return Response(code,{"fixture":"fault_drill"})
        outcome = outbound("jevmodel",labels={"public_approved"},transport=inject)
        outcomes[str(code or "offline")] = failure(outcome.status)
    passed = (denied==len(label_sets)*len(ENDPOINTS) and denied_transport==0 and len(calls)==1
              and list(outcomes.values())==list(expected.values()))
    return {"passed":passed,"synthetic_cases":len(label_sets)*len(ENDPOINTS),"blocked_before_transport":denied,
            "private_transport_calls":denied_transport,"public_control_calls":len(calls),"fault_outcomes":outcomes,
            "dataset":"synthetic_fault_drill","research_denominator":0}


def test_gate_requires_all_six(statuses, review):
    return len(statuses)==6 and set(statuses)==set(CODES) and all(statuses[k]=="PASS" for k in CODES) and review["approved"]


def run_checks(settings, store, request_key, resume_id=None, transport=network):
    with store.writer():
        run, attempt = store.begin(request_key,settings,resume_id)
        if attempt is None:
            return run
        status = {}
        def result(rid, state, text, refs, blocker=None):
            store.result(attempt,rid,state,text,refs,blocker)
            status[rid] = state

        passed = False
        try:
            quote, refs, external_hit, errors = discover(settings,store,attempt,transport)
            if quote and external_hit:
                result("C0-3","PASS","搜索引擎发现 URL，官方来源复核了原话及许可。",refs)
            elif quote:
                result("C0-3","BLOCKED","论坛检索与原话接口均已核验。专案指定的搜索引擎尚未取证。",refs,"；".join(errors))
            else:
                result("C0-3","BLOCKED","本批未取得同时包含许可、作者与原址的原话。",refs,"；".join(errors) or "原文或许可不可用")

            refs, versions, gaps, reason = call_shards(settings,store,run,attempt,quote,transport)
            version_ok = versions==[True,True]
            result("C0-1","PASS" if version_ok else "BLOCKED",
                   "实测 8 + 3 题，两片模型及问题键一致。" if version_ok else "固定模型尚缺完整的两片真实响应。",refs,
                   None if version_ok else (reason or "模型版本或问题键不匹配"))
            if gaps:
                refs = [*refs,store.record(attempt,"schema_gap","contract_check",{"model":MODEL},{"schema_gap":True,"fields":gaps})]
            contract_ok = version_ok and not gaps
            result("C0-2","PASS" if contract_ok else "BLOCKED",
                   "三种真实返回字段和概率分布均已核验。" if contract_ok else "三类返回字段尚未通过完整校验。",refs,
                   None if contract_ok else ("schema_gap · "+", ".join(gaps) if gaps else reason or "缺少固定版本完整响应"))

            reopened = Store(store.directory)
            ledger = reopened.ledger(run)
            evidenced = reopened.rows("SELECT id FROM evidence WHERE attempt_id=?",(attempt,))
            actual = (len(ledger)==2 and all(x["state"]=="received" and x["tokens"] is not None for x in ledger)
                      and len({x["request_key"] for x in ledger})==2 and bool(quote) and len(evidenced)>0)
            ref = store.record(attempt,"sqlite_readback","local_sqlite",{"run_id":run,"reopened_connection":True},
                               {"persisted_evidence":len(evidenced),"shards":ledger,"input_tokens":sum(x["tokens"] for x in ledger if x["tokens"] is not None) if actual else None,
                                "balance_synced":bool(ledger and ledger[-1]["remaining"] is not None)})
            result("C0-4","PASS" if actual else "BLOCKED","重新打开 SQLite 后，已核对证据、批次和分片账本。",
                   [ref]+[x["evidence_id"] for x in ledger if x["evidence_id"]],None if actual else "缺少两片真实 Jev 用量，余额未同步。")
            drill = test_isolation_drill()
            ref = store.record(attempt,"outbound_isolation","synthetic_fault_drill",{"channels":list(ENDPOINTS)},drill)
            result("C0-5","PASS" if drill["passed"] else "FAIL",f"执行 {drill['synthetic_cases']} 次外发拦截与六种故障注入。",[ref],None if drill["passed"] else "外发隔离与预期不符")
            recall = test_cross_category_recall()
            ref = store.record(attempt,"global_recall","synthetic_smoke",{"fixture":"2 products, 3 tasks, 30 intents"},recall)
            result("C0-6","PASS" if recall["passed"] else "FAIL","全库 30 个意图参与召回，已记录两个跨品类查询的候选与版本。",[ref],None if recall["passed"] else "关系完整性或跨品类召回未通过")
        except Exception as exc:
            # Never include raw transport errors, credentials, file paths or internal text in audit.
            ref = store.record(attempt,"probe_error","local_error",{},{"exception_type":type(exc).__name__})
            for rid in CODES:
                if rid not in status:
                    result(rid,"FAIL","检查执行中断。",[ref],f"本地执行异常 · {type(exc).__name__}")
        finally:
            review = settings.review_status()
            passed = test_gate_requires_all_six(status,review)
            ref = store.record(attempt,"stage_gate","local_gate",{"required":CODES},{"statuses":status.copy(),"provider_review":review})
            errors = [code for code in CODES if status.get(code)!="PASS"]
            gate_state = "PASS" if passed else ("FAIL" if "FAIL" in status.values() else "BLOCKED")
            result("G-1",gate_state,"同批六项检查及供应商审查均通过。" if passed else "P0 入口等待本批次完成验收。",[ref],
                   None if passed else "、".join(errors)+("；供应商留存审查待核验" if not review["approved"] else ""))
            store.finish(run,attempt,passed)
        return run
