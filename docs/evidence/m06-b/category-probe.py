"""Check the CAT-6 design with synthetic data in an in-memory SQLite database."""

import sqlite3
from contextlib import closing


def check():
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE product(id TEXT PRIMARY KEY NOT NULL);
            CREATE TABLE task(id TEXT PRIMARY KEY NOT NULL);
            CREATE TABLE intent(id TEXT PRIMARY KEY NOT NULL, main_task TEXT NOT NULL REFERENCES task);
            CREATE TABLE scope(id TEXT PRIMARY KEY NOT NULL);
            CREATE TABLE scope_product(scope TEXT REFERENCES scope, product TEXT REFERENCES product,
                                       PRIMARY KEY(scope, product)) WITHOUT ROWID;
            CREATE TABLE occurrence(id TEXT PRIMARY KEY NOT NULL, intent TEXT NOT NULL REFERENCES intent);
            CREATE TABLE evidence(id TEXT PRIMARY KEY NOT NULL, scope TEXT NOT NULL REFERENCES scope,
                                  occurrence TEXT NOT NULL REFERENCES occurrence, allowed INTEGER NOT NULL);
            CREATE TABLE product_proof(evidence TEXT REFERENCES evidence, product TEXT REFERENCES product,
                                       PRIMARY KEY(evidence, product)) WITHOUT ROWID;
            INSERT INTO task VALUES ('offline'), ('export');
            INSERT INTO intent VALUES ('continue', 'offline'), ('save', 'export');
            INSERT INTO scope VALUES ('scope1'), ('scope2'), ('open');
            INSERT INTO product VALUES ('p1');
            INSERT INTO scope_product VALUES ('scope1', 'p1');
            INSERT INTO occurrence VALUES ('m1', 'continue'), ('m2', 'save'), ('m5', 'save');
            INSERT INTO evidence VALUES ('e1', 'scope1', 'm1', 1), ('e2', 'scope1', 'm2', 1),
                                        ('e5', 'open', 'm5', 1);
            INSERT INTO product_proof VALUES ('e1', 'p1'), ('e2', 'p1');
        """)
        schema_sql = "SELECT type, name, sql FROM sqlite_schema ORDER BY type, name"
        prior_schema = db.execute(schema_sql).fetchall()
        db.executescript("""
            INSERT INTO product VALUES ('p2');
            INSERT INTO scope_product VALUES ('scope2', 'p2');
            INSERT INTO occurrence VALUES ('m3', 'continue'), ('m4', 'save');
            INSERT INTO evidence VALUES ('e3', 'scope2', 'm3', 1), ('e4', 'scope2', 'm4', 1);
            INSERT INTO product_proof VALUES ('e3', 'p2'), ('e4', 'p2');
        """)
        assert prior_schema == db.execute(schema_sql).fetchall()
        edges = """
            SELECT DISTINCT p.product, i.id, i.main_task FROM product_proof p
            JOIN evidence e ON e.id = p.evidence
            JOIN occurrence m ON e.occurrence = m.id
            JOIN intent i ON m.intent = i.id WHERE e.allowed = 1
        """
        for product in ("p1", "p2"):
            assert db.execute(edges + " AND p.product = ? ORDER BY i.id", (product,)).fetchall() == [
                (product, "continue", "offline"), (product, "save", "export")
            ]
        reverse = db.execute(edges + " AND i.id = 'save' ORDER BY p.product").fetchall()
        assert [edge[0] for edge in reverse] == ["p1", "p2"]
        db.execute("UPDATE evidence SET allowed = 0 WHERE id = 'e4'")
        assert db.execute(edges + " AND p.product = 'p2'").fetchall() == [("p2", "continue", "offline")]
        assert db.execute("SELECT COUNT(*) FROM evidence WHERE scope = 'open' AND allowed = 1").fetchone() == (1,)
        assert db.execute("SELECT COUNT(*) FROM product_proof WHERE evidence = 'e5'").fetchone() == (0,)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        print("CAT-6 prototype: two products, two shared intents, two tasks; schema unchanged")
        print("forward/reverse, withdrawn proof and non-product scope: PASS")


if __name__ == "__main__":
    check()
