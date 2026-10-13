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
          "statements", "reviews", "audit_log")


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
    for table, column, step in (("figures", "note", "Step 5"), ("estimates", "segment", "Step 7")):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if cols and column not in cols:
            if conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise RuntimeError(f"{table} table predates {step} and is not empty; rebuild the database")
            conn.execute(f"DROP TABLE {table}")
            audit(conn, "schema_migrated", table, {"added": column})


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
