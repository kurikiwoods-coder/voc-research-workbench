"""Export one connectivity run to a reviewable JSON + SQLite projection."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

from src.config import Settings
from src.dashboard.app import requirements
from src.execution.transport import ENDPOINTS, outbound
from src.ingestion.public_source import LICENSES, SITE, first_sentence, post_id
from src.raw_store.store import Store, dump, now


def fingerprint(value):
    return sha256(dump(value).encode()).hexdigest()


def public_evidence(row):
    name = row["name"]
    request, response = row["request"].copy(), row["response"].copy()
    if name == "forum_post":
        response = {key: response[key] for key in (
            "post_id","url","license","license_url","published_at","verified","method","search",
            "source_policy","terms_url","response_sha256","role","research_denominator"
        ) if key in response}
        if "text" in row["response"]:
            response["quote_utf8_sha256"] = sha256(row["response"]["text"].encode()).hexdigest()
            response["attributed_locally"] = bool(row["response"].get("author"))
    elif name in {"tavily","brave","forum_search"}:
        if "hits" in response:
            response = {"hits":[{"id":hit["id"],"url":hit["url"].split("?")[0].split("#")[0]} for hit in response["hits"]],
                        "response_sha256":response.get("response_sha256"),"quota_remaining":response.get("quota_remaining")}
    elif name == "jev_shard":
        body = request["body"]
        request["body"] = {"model":body["model"],"questions":body["questions"],
                           "state_utf8_sha256":sha256(body["state"].encode()).hexdigest()}
        obj = response.get("body")
        allowed = ("model","answers","usage")
        response = {"X-Tokens-Remaining":response.get("X-Tokens-Remaining"),"body_sha256":fingerprint(obj),
                    "body":{k:obj[k] for k in allowed if k in obj} if isinstance(obj,dict) else None}
    elif name not in {"jev_admission","sqlite_readback","outbound_isolation","global_recall","stage_gate","schema_gap","source_contract","probe_error"}:
        # New connector types must be explicitly reviewed before publishing free-text payloads.
        request, response = {"sha256":fingerprint(request)}, {"sha256":fingerprint(response)}
    return {k:row[k] for k in ("id","attempt_id","name","mode","checked_at","status_code")} | {
        "request":request,"response":response
    }


SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE checks(requirement_id TEXT PRIMARY KEY, description TEXT NOT NULL, implementation TEXT NOT NULL,
 test_case TEXT NOT NULL, status TEXT NOT NULL, detail TEXT, blocker TEXT, last_checked_at TEXT NOT NULL);
CREATE TABLE evidence(id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL, name TEXT NOT NULL,
 mode TEXT NOT NULL, checked_at TEXT NOT NULL, status_code INTEGER, request_json TEXT NOT NULL, response_json TEXT NOT NULL);
CREATE TABLE check_evidence(requirement_id TEXT REFERENCES checks,id INTEGER REFERENCES evidence,PRIMARY KEY(requirement_id,id));
CREATE TABLE usage_ledger(shard_no INTEGER PRIMARY KEY,state TEXT,tokens INTEGER,remaining INTEGER,evidence_id INTEGER REFERENCES evidence);
"""


def export(store, run_id, target):
    audit = store.audit(run_id)
    checks = [c for c in requirements(store,run_id) if c["stage"]=="P0-0" and c["last_checked_at"]]
    if len(checks)!=7 or store.fixture:
        raise ValueError("需要同一真实批次的六项记录与 G-1 判定")
    evidence = [public_evidence(item) for attempt in audit["attempts"] for item in attempt["evidence"]]
    ledger = [{k:shard[k] for k in ("shard_no","state","tokens","remaining","evidence_id")} for shard in store.ledger(run_id)]
    with store.db() as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        violations = len(db.execute("PRAGMA foreign_key_check").fetchall())
    receipt = {"format":1,"run":audit["run"],"attempts":[{k:a[k] for k in ("id","started_at","finished_at")} for a in audit["attempts"]],
               "operational_db_check":{"integrity_check":integrity,"foreign_key_violations":violations},
               "checks":checks,"evidence":evidence,"usage_ledger":ledger,"research_denominator":0}
    target = Path(target)
    target.mkdir(parents=True,exist_ok=True)
    # Refuse to overwrite an earlier receipt or the operational database.
    dbpath = target / "audit.sqlite3"
    output = target / "run.json"
    if dbpath.exists() or output.exists():
        raise FileExistsError("请为新批次选择空的输出目录")
    with closing(sqlite3.connect(dbpath)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        for key in ("format","run","attempts","operational_db_check","research_denominator"):
            db.execute("INSERT INTO metadata VALUES (?,?)",(key,dump(receipt[key])))
        for e in evidence:
            db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)",(
                e["id"],e["attempt_id"],e["name"],e["mode"],e["checked_at"],e["status_code"],dump(e["request"]),dump(e["response"])))
        for c in checks:
            db.execute("INSERT INTO checks VALUES (?,?,?,?,?,?,?,?)",tuple(c[k] for k in (
                "requirement_id","description","implementation","test_case","status","detail","blocker","last_checked_at")))
            db.executemany("INSERT INTO check_evidence VALUES (?,?)",[(c["requirement_id"],i) for i in set(c["evidence"])])
        for shard in ledger:
            db.execute("INSERT INTO usage_ledger VALUES (?,?,?,?,?)",tuple(shard.values()))
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return verify(target)


def verify(folder):
    folder = Path(folder)
    receipt = json.loads((folder/"run.json").read_text("utf-8"))
    with closing(sqlite3.connect((folder/"audit.sqlite3").resolve().as_uri()+"?mode=ro",uri=True)) as db:
        db.row_factory=sqlite3.Row
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite 完整性校验失败")
        meta = {r["key"]:json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}
        expected_metadata = {k:receipt[k] for k in ("format","run","attempts","operational_db_check","research_denominator")}
        checks = [dict(r) for r in db.execute("SELECT * FROM checks ORDER BY requirement_id")]
        expected_checks=[]
        for c in sorted(receipt["checks"],key=lambda row:row["requirement_id"]):
            expected_checks.append({k:c[k] for k in ("requirement_id","description","implementation","test_case","status","detail","blocker","last_checked_at")})
        links = {(r[0],r[1]) for r in db.execute("SELECT * FROM check_evidence")}
        expected_links={(c["requirement_id"],eid) for c in receipt["checks"] for eid in c["evidence"]}
        events=[]
        for r in db.execute("SELECT * FROM evidence ORDER BY id"):
            obj=dict(r)
            obj["request"]=json.loads(obj.pop("request_json"))
            obj["response"]=json.loads(obj.pop("response_json"))
            events.append(obj)
        ledger=[dict(r) for r in db.execute("SELECT * FROM usage_ledger ORDER BY shard_no")]
        if (meta!=expected_metadata or checks!=expected_checks or links!=expected_links or
                events!=sorted(receipt["evidence"],key=lambda r:r["id"]) or ledger!=receipt["usage_ledger"]):
            raise ValueError("数据库与 JSON 记录不同")
        status={c["requirement_id"]:c["status"] for c in checks}
        return {"run":receipt["run"]["id"],"checks":status,"evidence_records":len(events),"shards":len(ledger),
                "sqlite_integrity":"ok","receipt_sha256":fingerprint(receipt)}


def verify_public_source(folder):
    """Re-fetch the licensed excerpts identified in an independently checked audit."""
    folder = Path(folder)
    verify(folder)
    receipt = json.loads((folder / "run.json").read_text("utf-8"))
    references = {}
    for record in receipt["evidence"]:
        proof = record["response"]
        if record["name"] != "forum_post" or not proof.get("verified"):
            continue
        ident = post_id(proof.get("url"))
        if not ident or ident != proof.get("post_id"):
            raise ValueError("原帖域名或编号与存档不符")
        references.setdefault(ident, set()).add((proof["quote_utf8_sha256"], proof["license"]))

    observations = []
    for ident, expected in references.items():
        parameters = {"site": SITE, "filter": "withbody"}
        reply = outbound("stackexchange", labels={"public_approved"}, path=ident, query=parameters)
        items = reply.body.get("items") if isinstance(reply.body, dict) else []
        row = {}
        if isinstance(items, list) and items and isinstance(items[0], dict):
            row = items[0]
        body = row.get("body")
        digest = sha256(first_sentence(body).encode("utf-8")).hexdigest() if isinstance(body, str) else None
        license_name = row.get("content_license")
        if reply.status != 200 or not row:
            status = "BLOCKED"
        elif (
            post_id(row.get("link")) == ident
            and str(row.get("question_id")) == ident
            and license_name in LICENSES
            and expected == {(digest, license_name)}
        ):
            status = "PASS"
        else:
            status = "FAIL"
        observations.append({
            "checked_at": now(),
            "endpoint": ENDPOINTS["stackexchange"] + ident,
            "parameters": parameters,
            "post_id": ident,
            "http_status": reply.status,
            "license": license_name,
            "observed_quote_utf8_sha256": digest,
            "archived_sha256": sorted({checksum for checksum, _ in expected}),
            "status": status,
        })

    states = {row["status"] for row in observations}
    if "FAIL" in states:
        status = "FAIL"
    elif states == {"PASS"}:
        status = "PASS"
    else:
        status = "BLOCKED"
    return {
        "run": receipt["run"]["id"],
        "check": "public source recheck",
        "status": status,
        "observations": observations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--run", help="operational run UUID to export")
    command.add_argument("--verify", action="store_true")
    command.add_argument(
        "--verify-source", action="store_true", help="re-fetch the archived excerpt from its original API"
    )
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.verify_source:
        result = verify_public_source(args.directory)
    elif args.verify:
        result = verify(args.directory)
    else:
        result = export(Store(Settings.load().directory), args.run, args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.verify_source and result["status"] != "PASS":
        sys.exit(2 if result["status"] == "BLOCKED" else 1)
