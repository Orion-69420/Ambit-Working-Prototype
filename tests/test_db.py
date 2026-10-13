import sqlite3
from decimal import Decimal

import pytest

import run
from copilot import db


@pytest.fixture
def conn(tmp_path):
    return db.init_db(tmp_path / "t.sqlite")


def test_init_creates_all_tables(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(db.TABLES) <= names


def test_init_is_idempotent(tmp_path):
    db.init_db(tmp_path / "t.sqlite")
    db.init_db(tmp_path / "t.sqlite")


def test_audit_log_is_append_only(conn):
    db.audit(conn, "test", "item", {"a": 1}, user="tester")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET action = 'x'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")


def test_decimals_round_trip_exactly():
    assert db.from_db(db.to_db(Decimal("1240.10"))) == Decimal("1240.10")
    assert db.to_db("0.1") == "0.1"


def test_missing_stays_missing_and_floats_rejected():
    assert db.to_db(None) is None
    with pytest.raises(TypeError):
        db.to_db(0.1)


def test_correction_requires_reason(conn):
    base = dict(company="MM", quarter="Q1FY27", metric="revenue", period="Q1FY27",
                basis="consolidated", unit="INR crore", method="xbrl", status="verified",
                created_at=db.now())
    cols = ", ".join(base)
    conn.execute(f"INSERT INTO figures ({cols}) VALUES ({', '.join('?' * len(base))})", tuple(base.values()))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO figures ({cols}, supersedes) VALUES ({', '.join('?' * len(base))}, 1)",
                     tuple(base.values()))


def test_cli_init_db(tmp_path, capsys):
    assert run.main(["--db", str(tmp_path / "c.sqlite"), "init-db"]) == 0
    assert f"{len(db.TABLES)} tables" in capsys.readouterr().out


def test_cli_pending_commands_validate_and_exit(tmp_path):
    assert run.main(["--db", str(tmp_path / "c.sqlite"), "export", "--company", "MM", "--quarter", "Q1FY27"]) == 1  # no database
    with pytest.raises(SystemExit):
        run.main(["ingest", "--company", "TRENT", "--quarter", "Q1FY27"])
