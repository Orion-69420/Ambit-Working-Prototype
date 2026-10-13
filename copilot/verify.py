"""Step 8a: automated checks on extracted figures (procedure Section 7).

Each figure ends as 'verified' (every check passed), 'low_confidence' (a check failed; reasons in
the note) or 'missing'. 'manually_verified' figures are left alone. Re-running recomputes.

Checks
  source     figure has a document and page, or an XBRL element and context   -> missing (Gaps)
  on_page    PDF figure: the printed value is on the cited page                -> low confidence
  period     figure's period is a known quarter; XBRL context is three months  -> low confidence
  basis      figure basis matches the metric's configured basis                -> low confidence
  unit       XBRL unit is INR (money) or INR per share (EPS)                   -> low confidence
  cross      XBRL revenue / PAT appears in that quarter's results release or press release, or
             in a later release's comparator columns (decided 13 Oct)         -> low confidence
  segments   segment revenues - inter-segment = segment total = revenue (or total income; for
             Reliance, whose segment revenue includes GST, only the first equality)
                                                                               -> low confidence
  inputs     derived figure: every input verified                              -> low confidence
The margin-recompute check does not apply: no company-reported EBITDA margin is extracted, and
companies' own EBITDA definitions differ from the dictionary's.
"""
import json
import re
from decimal import Decimal

from copilot import config, db

MARK = "checks failed: "
XBRL_UNITS = {"inr_crore": "INR", "inr_per_share": "INRPerShare"}
CROSS_METRICS = ("revenue", "pat_owners")
TOLERANCE = Decimal("1")          # ₹ crore: XBRL and PDF figures are rounded to the crore or lakh


# ---------------------------------------------------------------- number matching in PDF text

def formats(value):
    """Ways a figure in ₹ crore may be printed: 0 or 2 decimals, western or Indian grouping."""
    out = set()
    v = abs(Decimal(value))
    for q in ("1", "0.01"):
        x = v.quantize(Decimal(q))
        ip, _, fp = str(x).partition(".")
        west = f"{int(ip):,}"
        ind = (re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", ip[:-3]) + "," + ip[-3:]) if len(ip) > 3 else ip
        for g in {west, ind, ip}:
            out.add(g + ("." + fp if fp else ""))
    return out


def number_regex(printed):
    """Match a printed number allowing one stray space between characters ('8,35 8.9 1')."""
    body = r"\s?".join(re.escape(ch) for ch in printed)
    return re.compile(r"(?<![\d,.])" + body + r"(?![\d]|[.,]\d)")


def on_text(value, texts):
    pats = [number_regex(f) for f in formats(value)]
    return [i for i, t in texts if any(p.search(t) for p in pats)]


# ---------------------------------------------------------------- checks

def check_figure(conn, cfg, f, pages_cache):
    """Return a list of failure reasons for one figure (empty list = passed)."""
    fails = []
    m = cfg.metrics.get(f["metric"])
    if f["method"] == "xbrl":
        if not (f["document_id"] and f["source_ref"] and f["source_detail"]):
            return ["source not recorded"]
        if XBRL_UNITS.get(f["unit"]) and f["original_unit"] != XBRL_UNITS[f["unit"]]:
            fails.append(f"unit {f['original_unit']} is not {XBRL_UNITS[f['unit']]}")
    elif f["method"] == "pdf":
        if not (f["document_id"] and f["source_ref"]):
            return ["source not recorded"]
        text = _page(conn, f["document_id"], int(f["source_ref"]), pages_cache)
        printed = re.sub(r"[%₹~]|^c\.", "", f["original_value"] or "").strip()
        if not printed or not number_regex(printed).search(text):
            fails.append(f"value {f['original_value']!r} not found on page {f['source_ref']}")
    if f["period"] not in config.QUARTERS:
        fails.append(f"period {f['period']} is not a tracked quarter")
    expected_basis = m.get("basis", cfg.companies[f["company"]]["basis"]) if m else None
    if expected_basis and f["basis"] != expected_basis:
        fails.append(f"basis {f['basis']} is not {expected_basis}")
    return fails


def _page(conn, doc_id, page, cache):
    key = (doc_id, page)
    if key not in cache:
        row = conn.execute("SELECT text FROM pages WHERE document_id = ? AND page = ?", key).fetchone()
        cache[key] = row[0] if row else ""
    return cache[key]


def cross_source(conn, company, period, value):
    """(quarter, document type, page) of a results release or press release showing the value.

    Searched in order: the quarter's own results release, its own press release, then later
    quarters' releases (their comparator columns). Returns None if no document shows it.
    """
    order = {q: i for i, q in enumerate(config.QUARTERS)}
    docs = conn.execute("SELECT id, quarter, type FROM documents WHERE company = ?"
                        " AND type IN ('results_release', 'press_release')", (company,)).fetchall()
    docs = [d for d in docs if d["quarter"] == period or order.get(d["quarter"], -1) > order[period]]
    for d in sorted(docs, key=lambda d: (d["quarter"] != period, order.get(d["quarter"], 99),
                                         d["type"] != "results_release")):
        texts = conn.execute("SELECT page, text FROM pages WHERE document_id = ?", (d["id"],)).fetchall()
        hits = on_text(value, texts)
        if hits:
            return d["quarter"], d["type"], hits[0]
    return None


def segment_sum(rows, company_cfg):
    """rows: figures of one company-period. Returns a failure reason or None."""
    seg = [r for r in rows if r["metric"] == "segment_revenue" and r["value"] is not None]
    if not seg:
        return None
    by = {r["metric"]: r for r in rows if r["segment"] is None}
    total = by.get("segment_revenue_total")
    sum_to = company_cfg.get("segment_sum_to", "revenue")
    target_metric = "total_income" if sum_to == "total_income" else "revenue"
    target = None if sum_to == "segment_total" else by.get(target_metric)   # segment_total: internal check only
    s = sum(Decimal(r["value"]) for r in seg)
    inter = by.get("inter_segment_revenue")
    inter_v = Decimal(inter["value"]) if inter and inter["value"] is not None else None
    reasons = []
    if total and total["value"] is not None:
        net = s - (inter_v or 0)
        if abs(net - Decimal(total["value"])) > TOLERANCE * len(seg):
            reasons.append(f"segments {net} {'(inter-segment not tagged) ' if inter_v is None else ''}"
                           f"!= segment total {total['value']}")
        if target and target["value"] is not None and abs(Decimal(total["value"]) - Decimal(target["value"])) > TOLERANCE:
            reasons.append(f"segment total {total['value']} != {target_metric} {target['value']}")
    return "; ".join(reasons) or None


def run(conn, cfg, company="all", quarter="all", user=None):
    """Check every figure of the needed periods. Returns {(company, period): Counter-like dict}."""
    companies = list(cfg.companies) if company == "all" else [company]
    periods = config.quarters_needed(quarter)
    pages_cache, summary = {}, {}
    for c in companies:
        for p in periods:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM figures WHERE company = ? AND period = ? AND status != 'manually_verified'", (c, p))]
            results = {}
            for f in rows:
                base_note = extraction_note(f["note"])
                f["note"] = base_note
                if f["value"] is None and f["status"] == "missing" and f["method"] != "derived":
                    results[f["id"]] = ("missing", base_note, [])
                    continue
                if f["method"] == "derived":
                    continue
                fails = check_figure(conn, cfg, f, pages_cache)
                if fails == ["source not recorded"]:
                    results[f["id"]] = ("missing", "source not recorded", fails)
                    continue
                if f["method"] == "xbrl" and f["metric"] in CROSS_METRICS and f["segment"] is None:
                    hit = cross_source(conn, c, p, f["value"])
                    if hit is None:
                        fails.append("not found in the results release or press release (cross-source)")
                    elif hit[0] != p or hit[1] != "results_release":
                        kind = "results release" if hit[1] == "results_release" else "press release"
                        base_note = _join(base_note, f"cross-checked in the {hit[0]} {kind}, p{hit[2]}")
                results[f["id"]] = ("low_confidence" if fails else "verified", base_note, fails)
            reason = segment_sum(rows, cfg.companies[c])
            if reason:
                for f in rows:
                    if f["metric"] == "segment_revenue" and f["id"] in results and results[f["id"]][0] == "verified":
                        results[f["id"]] = ("low_confidence", results[f["id"]][1], [f"segment sum: {reason}"])
            # an analyst's check against the source (Step 10) holds while the value is unchanged
            for f in rows:
                if f["id"] in results and results[f["id"]][0] == "low_confidence" and f["method"] != "derived":
                    chk = manual_check(conn, c, f)
                    if chk:
                        results[f["id"]] = ("manually_verified",
                                            f"manually checked by {chk['reviewer']}: {chk['comment']}", [])
            # derived figures inherit their inputs' status
            for f in rows:
                if f["method"] != "derived":
                    continue
                if f["value"] is None:
                    results[f["id"]] = ("missing", f["note"], [])
                    continue
                ids = json.loads(f["derivation"] or "{}").get("input_figures", {})
                weak = [name for name, fid in ids.items()
                        if fid is None or results.get(fid, ("verified",))[0] not in ("verified", "manually_verified")]
                results[f["id"]] = ("low_confidence" if weak else "verified", f["note"],
                                    [f"input not verified: {', '.join(weak)}"] if weak else [])
            counts = {}
            for fid, (status, note, fails) in results.items():
                note = _join(note, MARK + "; ".join(fails)) if fails else note
                conn.execute("UPDATE figures SET status = ?, note = ? WHERE id = ?", (status, note, fid))
                counts[status] = counts.get(status, 0) + 1
                if fails:
                    db.audit(conn, "check_failed", f"figure:{fid}", {"reasons": fails}, user=user)
            db.audit(conn, "figures_checked", f"{c}/{p}", counts, user=user)
            summary[(c, p)] = counts
    conn.commit()
    return summary


def extraction_note(note):
    """The note as extraction left it: drops what earlier check runs added, so re-runs don't stack."""
    keep = [part for part in (note or "").split(MARK)[0].split("; ")
            if part.strip() and not part.startswith(("cross-checked in the ", "manually checked by "))]
    return "; ".join(keep) or None


def manual_check(conn, company, f):
    """The latest analyst approval of this exact figure value, if any (see report.check_key)."""
    key = f"check:{company}:{f['metric']}:{f['segment'] or ''}:{f['period']}:{f['value']}"
    row = conn.execute("SELECT reviewer, comment FROM reviews WHERE item = ? AND action = 'approve'"
                       " ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    return dict(row) if row else None


def _join(a, b):
    return f"{a}; {b}" if a else b
