"""SQLite storage: schema, connection, exact-decimal helpers and the audit log."""
import datetime as dt
import getpass
import json
import pathlib
import sqlite3
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "copilot.sqlite"
SCHEMA = pathlib.Path(__file__).with_name("schema.sql")

TABLES = ("documents", "pages", "figures", "estimates", "comparisons",
          "statements", "reviews", "audit_log", "reports")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def connect(path=DEFAULT_DB):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=DEFAULT_DB):
    """Create the database and schema. Safe to run on an existing database."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    _migrate(conn)
    conn.executescript(SCHEMA.read_text(encoding="utf8"))
    audit(conn, "init_db", str(path))
    conn.commit()
    return conn


def _migrate(conn):
    """Bring an older database up to the current schema.

    Step 5 added figures.note and the 'extracted' status; Step 7 added estimates.segment.
    SQLite cannot change a CHECK constraint in place, so an empty table is dropped and
    recreated by the schema.
    """
    _migrate_document_types(conn)
    for table, column, step in (("figures", "note", "Step 5"), ("estimates", "segment", "Step 7")):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and column not in cols:
            if conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise RuntimeError(f"{table} table predates {step} and is not empty; rebuild the database")
            conn.execute(f"DROP TABLE {table}")
            audit(conn, "schema_migrated", table, {"added": column})


def _migrate_document_types(conn):
    """The review after Step 8 added the 'press_release' document type.

    The documents table holds rows other tables point to, so it is rebuilt in place: copy the
    rows into a table with the new constraint, then swap it in. References by id stay valid.
    """
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'documents'").fetchone()
    if row is None or "press_release" in row[0]:
        return
    new_sql = row[0].replace("'transcript', 'analyst_model'", "'transcript', 'press_release', 'analyst_model'")
    new_sql = new_sql.replace("CREATE TABLE documents", "CREATE TABLE documents_new", 1)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(new_sql)
        conn.execute("INSERT INTO documents_new SELECT * FROM documents")
        conn.execute("DROP TABLE documents")
        conn.execute("ALTER TABLE documents_new RENAME TO documents")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    audit(conn, "schema_migrated", "documents", {"added": "type 'press_release'", "rows_kept": True})


def to_db(value):
    """Store a value as exact decimal text. None stays None (missing, never zero)."""
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError("floats are not allowed for figures; pass Decimal or str")
    return str(Decimal(value))


def from_db(text):
    return None if text is None else Decimal(text)


def audit(conn, action, item=None, details=None, user=None):
    """Append one row to the audit log. Rows can never be updated or deleted."""
    conn.execute(
        "INSERT INTO audit_log (time, user, action, item, details) VALUES (?, ?, ?, ?, ?)",
        (now(), user or getpass.getuser(), action, item,
         json.dumps(details, default=str) if details is not None else None),
    )
