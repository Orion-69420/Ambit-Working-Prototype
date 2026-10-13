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
    conn.executescript(SCHEMA.read_text(encoding="utf8"))
    audit(conn, "init_db", str(path))
    conn.commit()
    return conn


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
