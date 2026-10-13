"""Step 4: register source documents and store PDF page text.

Reads config/sources.yaml. Each collected document is checked against its recorded SHA-256
before it is registered; a mismatch stops ingestion of that file. Re-running is safe: a
document already registered with the same hash is skipped.
"""
import hashlib
import pathlib

import pymupdf

from copilot import config, db

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANNED_BELOW = 30   # a page with fewer extractable characters is treated as scanned


class IngestError(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def select(documents, company="all", quarter="all"):
    return [d for d in documents
            if company in ("all", d["company"]) and quarter in ("all", d["quarter"])]


def ingest(conn, documents, root=ROOT, user=None):
    """Register documents and store page text. Returns a summary dict."""
    summary = {"registered": 0, "already": 0, "missing": [], "failed": [], "scanned_pages": []}
    for d in documents:
        label = f"{d['company']}/{d['quarter']}/{d['type']}"
        if d.get("status") != "collected":
            summary["missing"].append((label, d.get("reason", d.get("status"))))
            continue
        path = root / d["path"]
        try:
            doc_id, new = _register(conn, d, path, user)
        except IngestError as e:
            summary["failed"].append((label, str(e)))
            db.audit(conn, "ingest_failed", label, {"error": str(e)}, user=user)
            conn.commit()
            continue
        if not new:
            summary["already"] += 1
            continue
        if path.suffix.lower() == ".pdf":
            scanned = _store_pages(conn, doc_id, path)
            for page in scanned:
                summary["scanned_pages"].append((label, page))
            if scanned:
                db.audit(conn, "scanned_pages_flagged", f"document:{doc_id}",
                         {"pages": scanned}, user=user)
        conn.commit()
        summary["registered"] += 1
    return summary


def _register(conn, d, path, user):
    if not path.exists():
        raise IngestError(f"file not found: {d['path']}")
    digest = sha256(path)
    if d.get("sha256") and digest != d["sha256"]:
        raise IngestError(f"hash mismatch for {d['path']}: file {digest[:12]}, register {d['sha256'][:12]}")
    row = conn.execute(
        "SELECT id FROM documents WHERE company = ? AND quarter = ? AND type = ? AND sha256 = ?",
        (d["company"], d["quarter"], d["type"], digest)).fetchone()
    if row:
        return row["id"], False
    cur = conn.execute(
        "INSERT INTO documents (company, quarter, type, file_path, sha256, source_url,"
        " publication_date, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (d["company"], d["quarter"], d["type"], d["path"], digest, d.get("url"),
         str(d["publication_date"]) if d.get("publication_date") else None, db.now()))
    db.audit(conn, "document_ingested", f"document:{cur.lastrowid}",
             {"path": d["path"], "sha256": digest}, user=user)
    return cur.lastrowid, True


def _store_pages(conn, doc_id, path):
    """Store each page's text; page numbers start at 1 as in a PDF viewer. Returns scanned pages."""
    scanned = []
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf, start=1):
            text = page.get_text()
            is_scanned = len(text.strip()) < SCANNED_BELOW
            if is_scanned:
                scanned.append(i)
            conn.execute("INSERT INTO pages (document_id, page, text, scanned) VALUES (?, ?, ?, ?)",
                         (doc_id, i, text, int(is_scanned)))
    return scanned


def run(conn, company="all", quarter="all", user=None):
    documents = config.load("sources.yaml").get("documents", [])
    return ingest(conn, select(documents, company, quarter), user=user)
