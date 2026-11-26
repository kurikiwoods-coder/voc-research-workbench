"""Run a synthetic SQLite relationship probe without opening the workbench database."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import platform
import sqlite3
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter


SCHEMA = """
CREATE TABLE source (
    study INTEGER, record INTEGER, channel INTEGER, period INTEGER,
    permitted INTEGER, expires INTEGER,
    PRIMARY KEY (study, record)
) WITHOUT ROWID;
CREATE TABLE member (
    study INTEGER, revision INTEGER, mention INTEGER,
    PRIMARY KEY (study, revision, mention)
) WITHOUT ROWID;
CREATE TABLE support (
    study INTEGER, revision INTEGER, mention INTEGER, record INTEGER,
    PRIMARY KEY (study, revision, mention, record),
    FOREIGN KEY (study, revision, mention) REFERENCES member,
    FOREIGN KEY (study, record) REFERENCES source
) WITHOUT ROWID;
CREATE TABLE product_edge (
    study INTEGER, revision INTEGER, mention INTEGER, record INTEGER, product INTEGER,
    PRIMARY KEY (study, revision, mention, record, product),
    FOREIGN KEY (study, revision, mention, record) REFERENCES support
) WITHOUT ROWID;
CREATE INDEX product_lookup ON product_edge (study, revision, product, mention, record);
CREATE TABLE registry (
    version INTEGER, kind TEXT, entity INTEGER, definition TEXT,
    PRIMARY KEY (version, kind, entity)
) WITHOUT ROWID;
"""

FILTER = """
SELECT COUNT(DISTINCT edge.mention)
FROM product_edge AS edge JOIN source AS src
    ON (src.study, src.record) = (edge.study, edge.record)
WHERE edge.study = 1 AND edge.revision = 1 AND edge.product = 4
    AND src.channel = 1 AND src.period BETWEEN 2 AND 8
    AND src.permitted = 1 AND src.expires > 10
"""

PAGE = """
SELECT mention FROM member
WHERE study = 1 AND revision = 1 AND mention > ?
ORDER BY mention LIMIT 100
"""

PRODUCTS = """
SELECT record, product FROM product_edge
WHERE study = 1 AND revision = 1 AND mention = ?
ORDER BY record, product
"""


def fixture_row(record):
    return (1, record, record // 3 % 2, record % 12, int(record % 13 != 0),
            30 if record % 17 else 5)


def fixture_products(record):
    return (record % 5, (record + 1) % 5)


def populate(db, size):
    with db:
        db.executemany("INSERT INTO source VALUES (?, ?, ?, ?, ?, ?)",
                       (fixture_row(record) for record in range(size)))
        db.executemany("INSERT INTO member VALUES (1, 1, ?)",
                       ((mention,) for mention in range(size // 2)))
        db.executemany("INSERT INTO support VALUES (1, 1, ?, ?)",
                       ((record // 2, record) for record in range(size)))
        db.executemany("INSERT INTO product_edge VALUES (1, 1, ?, ?, ?)",
                       ((record // 2, record, product)
                        for record in range(size) for product in fixture_products(record)))
        db.executemany("INSERT INTO registry VALUES (1, ?, ?, ?)",
                       ((kind, entity, f"synthetic {kind} {entity}")
                        for kind, count in (("product", 100), ("task", 50), ("intent", 350))
                        for entity in range(count)))
        db.execute("ANALYZE")


def query_probe(db, query, args=()):
    db.execute(query, args).fetchall()
    samples = []
    for _ in range(7):
        start = perf_counter()
        output = db.execute(query, args).fetchall()
        samples.append((perf_counter() - start) * 1000)
    plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query, args)]
    return output, f"median {median(samples):.3f} ms, max {max(samples):.3f} ms", plan


def checkpoint(db):
    assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def byte_count(path):
    return path.stat().st_size


def timed_write(db, statements):
    db.execute("BEGIN IMMEDIATE")
    start = perf_counter()
    with db:
        for statement in statements:
            db.execute(statement)
    return (perf_counter() - start) * 1000


def counts(db):
    return tuple(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                 for name in ("source", "member", "support", "product_edge", "registry"))


def probe(size):
    with TemporaryDirectory(prefix="m06-scale-") as scratch:
        database = Path(scratch, "source.sqlite3")
        wal = database.with_name(database.name + "-wal")
        restored = Path(scratch, "restored.sqlite3")
        with closing(sqlite3.connect(database)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.executescript(SCHEMA)
            populate(db, size)
            checkpoint(db)
            across_rows = [record for record in range(size)
                           if 4 in fixture_products(record) and record // 3 % 2 == 1
                           and 2 <= record % 12 <= 8 and record % 13 != 0 and record % 17 != 0]
            expected = Counter(record // 2 for record in across_rows)
            assert len(across_rows) > len(expected)
            evidence_count_query = FILTER.replace("COUNT(DISTINCT edge.mention)", "COUNT(*)")
            assert db.execute(evidence_count_query).fetchone() == (len(across_rows),)
            revoked = next(record for record in across_rows if expected[record // 2] == 1)
            midpoint = size // 4
            print(f"\n{size:,} source records; initial main {byte_count(database):,} B")
            print(f"matching evidence rows before DISTINCT: {len(across_rows):,}")
            queries = (
                ("filter", FILTER, (), [(len(expected),)]),
                ("page", PAGE, (midpoint,), [(i,) for i in range(midpoint + 1, midpoint + 101)]),
                ("reverse product", PRODUCTS, (midpoint,),
                 [(record, product) for record in (midpoint * 2, midpoint * 2 + 1)
                  for product in sorted(fixture_products(record))]),
            )
            for label, query, args, expected_rows in queries:
                output, duration, plan = query_probe(db, query, args)
                assert output == expected_rows, (label, output, expected_rows)
                print(f"{label}: {output[0][0] if label == 'filter' else len(output)}; {duration}; {plan}")

            before = byte_count(database)
            snapshot_ms = timed_write(db, (
                "INSERT INTO member SELECT study, 2, mention FROM member WHERE revision = 1",
                "INSERT INTO support SELECT study, 2, mention, record FROM support WHERE revision = 1",
                "INSERT INTO product_edge SELECT study, 2, mention, record, product FROM product_edge WHERE revision = 1",
            ))
            snapshot_wal = byte_count(wal)
            checkpoint(db)
            print(f"snapshot: {snapshot_ms:.3f} ms; main +{byte_count(database)-before:,} B; WAL {snapshot_wal:,} B")

            before = byte_count(database)
            registry_ms = timed_write(db, (
                "INSERT INTO registry SELECT 2, kind, entity, definition FROM registry WHERE version = 1",
            ))
            registry_wal = byte_count(wal)
            checkpoint(db)
            print(f"registry: {registry_ms:.3f} ms; main +{byte_count(database)-before:,} B; WAL {registry_wal:,} B")

            # Keep a committed change in WAL to check that backup restores the live state.
            with db:
                db.execute("UPDATE source SET permitted = 0 WHERE study = 1 AND record = ?", (revoked,))
            assert db.execute(FILTER).fetchone() == (len(expected) - 1,)
            assert byte_count(wal) > 32
            start = perf_counter()
            with closing(sqlite3.connect(restored)) as target:
                db.backup(target)
            backup_ms = (perf_counter() - start) * 1000
        with closing(sqlite3.connect(restored)) as target:
            assert counts(target) == (size, size, size * 2, size * 4, 1000)
            assert target.execute(FILTER).fetchone() == (len(expected) - 1,)
            assert target.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert target.execute("PRAGMA foreign_key_check").fetchall() == []
        print(f"backup: {backup_ms:.3f} ms; {byte_count(restored):,} B; restore assertions passed")


if __name__ == "__main__":
    print(f"{platform.platform()}, Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}")
    for scale in (1_000, 10_000, 100_000):
        probe(scale)
