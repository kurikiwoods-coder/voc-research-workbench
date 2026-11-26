"""C0-6 runs an actual global nearest-neighbour query against a disposable synthetic database."""

from contextlib import closing
from hashlib import sha256
import sqlite3

import sklearn
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from src.execution.jev import intent_question
from src.raw_store.store import dump

TASKS = {
    "set-up": (
        "初次配对设备",
        "跳过初始绑定",
        "切换界面语言",
        "放大显示字体",
        "启用高对比显示",
        "调整提示音量",
        "恢复出厂设置",
        "读取使用说明",
        "共享家庭访问",
        "关闭消息通知",
    ),
    "use": (
        "断网离线继续使用",
        "中途暂停并继续",
        "比较历史记录",
        "定时自动结束",
        "查看剩余时间",
        "拆分连续任务",
        "切换使用模式",
        "保存常用设置",
        "导出个人数据",
        "查找上次操作",
    ),
    "care": (
        "清除顽固污渍",
        "更换磨损部件",
        "定位异常噪声",
        "诊断连接故障",
        "检查电池状态",
        "避免潮湿损坏",
        "清理残留气味",
        "重置保养提醒",
        "核对保修期限",
        "安排售后维修",
    ),
}
SCHEMA = """
CREATE TABLE products(id TEXT PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE scopes(id TEXT PRIMARY KEY,topic TEXT NOT NULL,version INTEGER NOT NULL);
CREATE TABLE scope_product(scope TEXT REFERENCES scopes,product TEXT REFERENCES products,PRIMARY KEY(scope,product));
CREATE TABLE tasks(id TEXT PRIMARY KEY);
CREATE TABLE intents(id TEXT PRIMARY KEY,definition TEXT NOT NULL,primary_task TEXT NOT NULL REFERENCES tasks);
CREATE TABLE intent_task(intent TEXT REFERENCES intents,task TEXT REFERENCES tasks,PRIMARY KEY(intent,task));
CREATE TABLE evidence(id TEXT PRIMARY KEY,body TEXT NOT NULL);
CREATE TABLE mentions(id TEXT PRIMARY KEY,scope TEXT REFERENCES scopes,evidence TEXT REFERENCES evidence,intent TEXT REFERENCES intents);
CREATE TABLE mention_product(mention TEXT REFERENCES mentions,product TEXT REFERENCES products,evidence TEXT REFERENCES evidence,
                             PRIMARY KEY(mention,product));
"""


def test_cross_category_recall():
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO products VALUES (?,?)", [("P-A", "智能手表"), ("P-B", "空气净化器")])
        db.executemany(
            "INSERT INTO scopes VALUES (?,?,1)",
            [("S1", "跨品类使用研究"), ("S2", "无产品限制的需求研究")],
        )
        db.executemany("INSERT INTO scope_product VALUES ('S1',?)", [("P-A",), ("P-B",)])
        for task, labels in TASKS.items():
            db.execute("INSERT INTO tasks VALUES (?)", (task,))
            for n, label in enumerate(labels):
                uid = f"{task}-{n:02d}"
                product = "P-A" if n % 2 == 0 else "P-B"
                db.execute("INSERT INTO intents VALUES (?,?,?)", (uid, label, task))
                db.execute("INSERT INTO intent_task VALUES (?,?)", (uid, task))
                db.execute("INSERT INTO evidence VALUES (?,?)", (uid, "合成夹具 · " + label))
                db.execute("INSERT INTO mentions VALUES (?,'S1',?,?)", (uid, uid, uid))
                db.execute("INSERT INTO mention_product VALUES (?,?,?)", (uid, product, uid))
        db.execute("INSERT INTO intent_task VALUES ('use-00','set-up')")
        registry = list(db.execute("SELECT id,definition FROM intents ORDER BY id"))
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3), sublinear_tf=True)
        matrix = vectorizer.fit_transform([label for _, label in registry])
        svd = TruncatedSVD(n_components=20, random_state=47)
        index = normalize(svd.fit_transform(matrix))
        probes = []
        for product, query, target in [
            ("P-B", "我出门时没联网，希望能断网离线继续使用", "use-00"),
            ("P-A", "家人不想一直听到提示，想调整提示音量", "set-up-05"),
        ]:
            vec = normalize(svd.transform(vectorizer.transform([query])))
            scores = (index @ vec.T).ravel()
            ranking = sorted(range(len(registry)), key=lambda i: (-scores[i], registry[i][0]))[:12]
            candidates = [
                {"intent_id": registry[i][0], "cosine": round(float(scores[i]), 6)} for i in ranking
            ]
            choice = intent_question({registry[i][0]: registry[i][1] for i in ranking})
            origin = db.execute(
                "SELECT product FROM mention_product JOIN mentions ON mention=mentions.id WHERE intent=?",
                (target,),
            ).fetchone()[0]
            probes.append(
                {
                    "query": query,
                    "query_product": product,
                    "expected": target,
                    "evidence_product": origin,
                    "cross_product_hit": origin != product and target in choice["criteria"],
                    "candidates": candidates,
                    "choice_options": list(choice["criteria"]),
                    "noul_guard": "in_registry",
                }
            )
        fk = db.execute("PRAGMA foreign_key_check").fetchall()
        broken = db.execute(
            """SELECT COUNT(*) FROM intents i WHERE NOT EXISTS
                            (SELECT 1 FROM intent_task WHERE intent=i.id AND task=i.primary_task)"""
        ).fetchone()[0]
        empty = db.execute("SELECT COUNT(*) FROM scope_product WHERE scope='S2'").fetchone()[0]
        counts = {
            table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
            for table in ("products", "tasks", "intents", "mentions")
        }
    registry_hash = sha256(dump(registry).encode()).hexdigest()[:16]
    embedding = "char-tfidf(1,3)+lsa(20)+cosine; sklearn-" + sklearn.__version__
    return {
        "passed": not fk
        and broken == 0
        and empty == 0
        and counts["intents"] >= 30
        and all(p["cross_product_hit"] for p in probes),
        "counts": counts,
        "orphan_links": len(fk) + broken,
        "unrestricted_scope_products": empty,
        "embedding_model": embedding,
        "index_version": sha256((registry_hash + embedding + ":seed47").encode()).hexdigest()[:16],
        "registry_version": registry_hash,
        "k": 12,
        "queries": probes,
        "dataset": "synthetic_smoke",
        "research_denominator": 0,
    }
