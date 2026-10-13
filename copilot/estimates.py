"""Step 7: read estimates from the analyst model, read-only.

The workbook is opened with openpyxl in read-only mode with data_only=True, so only cached
values are read (a formula with no cached value is reported as missing, never computed), and it
is never saved. Its SHA-256 is taken before and after; a change stops the run.
"""
import datetime as dt
import pathlib
from decimal import Decimal

from openpyxl import load_workbook

from copilot import config, db, ingest

MODEL_DOC = ("ALL", "ALL")   # the model covers every company; registered once as a document


class ModelError(Exception):
    pass


def load_map(cfg, base=config.CONFIG):
    m = config.load("model_map.yaml", base)
    problems = []
    for company, entry in (m.get("companies") or {}).items():
        if company not in cfg.companies:
            problems.append(f"model_map: unknown company {company}")
            continue
        for c in entry.get("cells", []):
            metric = cfg.metrics.get(c.get("metric"))
            if metric is None:
                problems.append(f"model_map {company}: unknown metric {c.get('metric')!r}")
            elif c.get("segment") and c["segment"] not in cfg.companies[company]["segments"]:
                problems.append(f"model_map {company}: unknown segment {c['segment']!r}")
            elif c.get("unit") != metric["unit"]:
                problems.append(f"model_map {company} {c['metric']}: unit {c.get('unit')} != {metric['unit']}")
    if problems:
        raise config.ConfigError(problems)
    return m


def to_decimal(v):
    """Excel stores numbers as floats; repr gives the shortest exact decimal string."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return Decimal(repr(v))
    try:
        return Decimal(str(v).replace(",", "").strip())
    except Exception:
        return None


def read(path, model_map, company="all", quarters=None):
    """Return ([estimate dicts], sha_before, sha_after). Raises ModelError if the file changed."""
    before = ingest.sha256(path)
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        out = []
        for c, entry in model_map["companies"].items():
            if company not in ("all", c):
                continue
            ws = wb[entry["sheet"]]
            dates = {q: ws[cell].value for q, cell in entry.get("estimate_date", {}).items()}
            for item in entry["cells"]:
                for q in config.TARGET_QUARTERS:
                    if q not in item or (quarters and q not in quarters):
                        continue
                    raw = ws[item[q]].value
                    d = dates.get(q)
                    out.append(dict(company=c, quarter=q, metric=item["metric"], segment=item.get("segment"),
                                    value=to_decimal(raw), unit=item["unit"], sheet=entry["sheet"], cell=item[q],
                                    estimate_date=d.date().isoformat() if isinstance(d, dt.datetime) else d,
                                    is_sample=bool(model_map.get("sample"))))
    finally:
        wb.close()
    after = ingest.sha256(path)
    if after != before:
        raise ModelError(f"analyst model changed while being read: {before[:12]} -> {after[:12]}")
    return out, before, after


def _model_document(conn, path, rel, sha, user):
    row = conn.execute("SELECT id FROM documents WHERE company = ? AND quarter = ? AND type = 'analyst_model'"
                       " AND sha256 = ?", (*MODEL_DOC, sha)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO documents (company, quarter, type, file_path, sha256, ingested_at)"
                       " VALUES (?, ?, 'analyst_model', ?, ?, ?)", (*MODEL_DOC, rel, sha, db.now()))
    db.audit(conn, "document_ingested", f"document:{cur.lastrowid}", {"path": rel, "sha256": sha}, user=user)
    return cur.lastrowid


def run(conn, cfg, company="all", quarter="all", user=None):
    model_map = load_map(cfg)
    rel = model_map["workbook"]
    path = config.CONFIG.parent / rel
    if not path.exists():
        raise ModelError(f"analyst model not found: {rel}")
    quarters = None if quarter == "all" else [q for q in config.quarters_needed(quarter) if q in config.TARGET_QUARTERS]
    ests, before, after = read(path, model_map, company, quarters)
    doc_id = _model_document(conn, path, rel, before, user)
    for c in {e["company"] for e in ests}:
        for q in {e["quarter"] for e in ests if e["company"] == c}:
            conn.execute("DELETE FROM estimates WHERE company = ? AND quarter = ?", (c, q))
    for e in ests:
        conn.execute("INSERT INTO estimates (company, quarter, metric, segment, value, unit, sheet, cell,"
                     " estimate_date, is_sample, document_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (e["company"], e["quarter"], e["metric"], e["segment"], db.to_db(e["value"]), e["unit"],
                      e["sheet"], e["cell"], e["estimate_date"], int(e["is_sample"]), doc_id))
    db.audit(conn, "estimates_read", rel, {"count": len(ests), "missing": sum(e["value"] is None for e in ests),
                                           "sha256_before": before, "sha256_after": after,
                                           "unchanged": before == after, "sample": model_map.get("sample")},
             user=user)
    conn.commit()
    return ests, before, after
