import pymupdf
import pytest

from copilot import db, ingest


@pytest.fixture
def conn(tmp_path):
    return db.init_db(tmp_path / "t.sqlite")


@pytest.fixture
def files(tmp_path):
    """A two-page PDF (text + blank page) and an XBRL stub, with register entries."""
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Revenue from operations 1,240.10 for the quarter ended 30 June 2026")
    pdf.new_page()   # no text: behaves like a scanned page
    pdf.save(root / "data" / "release.pdf")
    (root / "data" / "x.xml").write_text("<xbrl/>", encoding="utf8")
    docs = [
        dict(company="MM", quarter="Q1FY27", type="results_release", path="data/release.pdf",
             status="collected", publication_date="2026-07-30", url="https://example/r.pdf",
             sha256=ingest.sha256(root / "data" / "release.pdf")),
        dict(company="MM", quarter="Q1FY27", type="xbrl", path="data/x.xml", status="collected",
             sha256=ingest.sha256(root / "data" / "x.xml")),
        dict(company="INFY", quarter="Q1FY27", type="presentation", status="missing",
             reason="not filed on NSE"),
    ]
    return root, docs


def test_registers_documents_with_hash_and_pages(conn, files):
    root, docs = files
    s = ingest.ingest(conn, docs, root=root, user="t")
    assert s["registered"] == 2 and not s["failed"]
    rows = {r["type"]: r for r in conn.execute("SELECT * FROM documents")}
    assert rows["results_release"]["sha256"] == docs[0]["sha256"]
    assert rows["results_release"]["publication_date"] == "2026-07-30"
    pages = conn.execute("SELECT page, text, scanned FROM pages ORDER BY page").fetchall()
    assert [p["page"] for p in pages] == [1, 2]          # numbered from 1, as in a viewer
    assert "1,240.10" in pages[0]["text"] and pages[0]["scanned"] == 0
    assert pages[1]["scanned"] == 1
    assert s["scanned_pages"] == [("MM/Q1FY27/results_release", 2)]


def test_missing_documents_are_reported_not_registered(conn, files):
    root, docs = files
    s = ingest.ingest(conn, docs, root=root)
    assert s["missing"] == [("INFY/Q1FY27/presentation", "not filed on NSE")]
    assert conn.execute("SELECT count(*) FROM documents WHERE company = 'INFY'").fetchone()[0] == 0


def test_rerun_is_idempotent(conn, files):
    root, docs = files
    ingest.ingest(conn, docs, root=root)
    s = ingest.ingest(conn, docs, root=root)
    assert s["registered"] == 0 and s["already"] == 2
    assert conn.execute("SELECT count(*) FROM pages").fetchone()[0] == 2


def test_hash_mismatch_is_refused(conn, files):
    root, docs = files
    (root / "data" / "x.xml").write_text("<xbrl>changed</xbrl>", encoding="utf8")
    s = ingest.ingest(conn, docs, root=root)
    assert s["failed"] and "hash mismatch" in s["failed"][0][1]
    assert conn.execute("SELECT count(*) FROM documents WHERE type = 'xbrl'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM audit_log WHERE action = 'ingest_failed'").fetchone()[0] == 1


def test_every_ingest_is_audited(conn, files):
    root, docs = files
    ingest.ingest(conn, docs, root=root, user="t")
    actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log")]
    assert actions.count("document_ingested") == 2 and "scanned_pages_flagged" in actions


def test_select_filters_company_and_quarter(files):
    _, docs = files
    assert len(ingest.select(docs, "MM", "all")) == 2
    assert len(ingest.select(docs, "all", "Q1FY27")) == 3
    assert ingest.select(docs, "TITAN", "all") == []
