"""Step 10: assemble the Change Report and apply the approval rule (procedure Sections 6-7).

A report is built fresh from the database whenever it is viewed. Approval saves a snapshot of
it together with a fingerprint (SHA-256) of its content. If anything in that content changes
later (a corrected value, a new transcript, a re-run), the fingerprint no longer matches and
the report returns to Draft. Exporting never approves.

Review items are keyed by what they are, not by database ids, so reviews survive re-runs:
  metric:<metric>:<segment>                  one metric-table row
  statement:<type>:<page>:<hash of quote>    one guidance statement or flag
  check:<company>:<metric>:<segment>:<period>:<value>   a low-confidence figure checked by hand
"""
import hashlib
import json
from decimal import Decimal

from copilot import commentary, compare, config, db

SEV_RANK = {"high": 3, "medium": 2, "low": 1}
DONE_ACTIONS = {"approve", "reject", "correct"}
SAMPLE_BANNER = "Estimates are synthetic SAMPLE values, not an analyst view."
GUIDANCE_PER_SIDE = 2


class ApprovalError(Exception):
    pass


# ---------------------------------------------------------------- keys and formatting

def report_id(company, quarter):
    return f"{company}_{quarter}"


def metric_key(metric, segment):
    return f"metric:{metric}:{segment or ''}"


def statement_key(s):
    return f"statement:{s['type']}:{s['page']}:{hashlib.sha1(s['quote'].encode()).hexdigest()[:10]}"


def check_key(company, metric, segment, period, value):
    return f"check:{company}:{metric}:{segment or ''}:{period}:{value}"


def indian(n, places=0):
    """1240.5 -> '1,240.5' with Indian grouping (12,34,567)."""
    q = Decimal(n).quantize(Decimal(1).scaleb(-places)) if places else Decimal(n).quantize(Decimal(1))
    sign = "-" if q < 0 else ""
    ip, _, fp = str(abs(q)).partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        out = ""
        while len(head) > 2:
            out = "," + head[-2:] + out
            head = head[:-2]
        ip = head + out + "," + tail
    return sign + ip + ("." + fp if fp else "")


PLACES = {"inr_crore": 0, "inr_per_share": 2, "percent": 1, "pct_growth": 1, "thousand_units": 1,
          "million": 1, "inr_per_month": 1, "gb_per_month": 1}


def fmt_value(value, unit, currency="₹"):
    if value is None:
        return "—"
    v = Decimal(value)
    p = PLACES.get(unit, 2)
    if unit == "inr_crore":
        return f"{currency}{indian(v, p)} crore"
    if unit == "inr_per_share":
        return f"{currency}{indian(v, p)}"
    if unit in ("percent", "pct_growth"):
        return f"{v:.{p}f}%"
    if unit == "inr_per_month":
        return f"{currency}{v:.{p}f}/month"
    if unit == "thousand_units":
        return f"{v:.{p}f}k units"
    if unit == "million":
        return f"{v:.{p}f} Mn"
    if unit == "gb_per_month":
        return f"{v:.{p}f} GB/month"
    return f"{v:.{p}f}"


def fmt_change(c):
    """Change text for one comparison dict."""
    if c is None or c.get("gap"):
        return "gap"
    if c["not_meaningful"]:
        return f"{Decimal(c['change']):+,.2f} (n.m.)"
    if c["change_bps"] is not None:
        return f"{Decimal(c['change_bps']):+,.0f} bps"
    if c["change_pct"] is not None:
        return f"{Decimal(c['change_pct']):+.1f}%"
    return f"{Decimal(c['change']):+.1f} pp"


# ---------------------------------------------------------------- building the report

def _source(conn, f, cfg):
    if f is None:
        return None
    if f["method"] == "derived":
        return {"kind": "derived", "text": f"Derived: {json.loads(f['derivation'] or '{}').get('formula', '')}"}
    if f["document_id"] is None or (f["method"] == "pdf" and f["source_ref"] is None):
        return {"kind": "none", "text": f["note"] or "no source"}
    d = conn.execute("SELECT * FROM documents WHERE id = ?", (f["document_id"],)).fetchone()
    kind = d["type"].replace("_", " ")
    if f["method"] == "xbrl":
        return {"kind": "xbrl", "document_id": d["id"], "doc_quarter": d["quarter"], "element": f["source_detail"],
                "context": f["source_ref"], "text": f"XBRL {f['source_detail']} [{f['source_ref']}], {d['quarter']} filing"}
    text = f"{kind.capitalize()} {d['quarter']}, p. {f['source_ref']}"
    if d["quarter"] != f["period"] and d["quarter"] != f["quarter"]:
        text += f" (published {d['publication_date']})"
    return {"kind": "pdf", "document_id": d["id"], "doc_quarter": d["quarter"], "page": int(f["source_ref"]),
            "detail": f["source_detail"], "text": text, "published": d["publication_date"]}


def _figure_info(conn, cfg, f):
    if f is None:
        return None
    return {"period": f["period"], "value": f["value"], "status": f["status"], "note": f["note"],
            "source": _source(conn, f, cfg), "document_quarter": f["quarter"], "method": f["method"],
            "metric": f["metric"], "segment": f["segment"]}


def _rows(conn, cfg, company, quarter):
    topics = cfg.commentary.get("metric_topics", {})
    expl = conn.execute("SELECT * FROM statements WHERE company = ? AND quarter = ? AND type = 'explanation'"
                        " ORDER BY page, id", (company, quarter)).fetchall()
    rows = []
    for m in cfg.metrics_for(company):
        segments = list(cfg.companies[company]["segments"]) if m.get("per_segment") else [None]
        for seg in segments:
            cur = compare.pick(conn, company, m["id"], seg, quarter, quarter)
            row = {"key": metric_key(m["id"], seg), "metric": m["id"], "name": m["name"], "segment": seg,
                   "unit": m["unit"], "change_as": m["change_as"],
                   "current": _figure_info(conn, cfg, cur), "comparisons": {}, "explanation": None}
            if cur is not None and cur["value"] is not None:
                for k in conn.execute(
                        "SELECT k.*, g.value AS g_value, g.period AS g_period, g.quarter AS g_quarter,"
                        " g.status AS g_status, g.id AS g_id, e.value AS e_value, e.is_sample, e.sheet, e.cell"
                        " FROM comparisons k LEFT JOIN figures g ON g.id = k.comparator_figure_id"
                        " LEFT JOIN estimates e ON e.id = k.comparator_estimate_id WHERE k.figure_id = ?",
                        (cur["id"],)):
                    g = conn.execute("SELECT * FROM figures WHERE id = ?", (k["g_id"],)).fetchone() if k["g_id"] else None
                    row["comparisons"][k["comparator"]] = {
                        "value": k["e_value"] if k["comparator"] == "estimate" else k["g_value"],
                        "change": k["change"], "change_pct": k["change_pct"], "change_bps": k["change_bps"],
                        "not_meaningful": k["not_meaningful"], "severity": k["severity"], "gap": k["gap_reason"],
                        "figure": _figure_info(conn, cfg, g),
                        "estimate": {"sheet": k["sheet"], "cell": k["cell"], "sample": bool(k["is_sample"])}
                        if k["comparator"] == "estimate" and k["sheet"] else None}
            match = _explanation(expl, m["id"], seg, topics,
                                 cfg.commentary.get("segment_keywords", {}).get(company, {}))
            if match:
                row["explanation"] = {"quote": match["quote"], "page": match["page"], "speaker": match["speaker"]}
            rows.append(row)
    return rows


METRIC_WORDS = {"revenue": r"revenue|top ?line|\bsales\b", "ebitda": r"EBITDA", "ebitda_margin": r"margin",
                "pat_owners": r"\bPAT\b|profit", "basic_eps": r"\bEPS\b|earnings per share",
                "segment_revenue": r"revenue|growth|volume|sales", "segment_result": r"margin|EBIT|profit"}


def _explanation(expl, metric, segment, topics, seg_words):
    """The first explanation that fits the row: a segment row needs its segment named in the
    quote; a company-level row prefers a quote that names its metric, then one on its topic."""
    import re
    topic = topics.get(metric)
    words = METRIC_WORDS.get(metric)
    if segment:
        pats = seg_words.get(segment)
        if not pats:
            return None
        hits = [e for e in expl if any(re.search(p, e["quote"], re.I) for p in pats)]
        return next((e for e in hits if words and re.search(words, e["quote"], re.I)), hits[0] if hits else None)
    if words:
        named = next((e for e in expl if re.search(words, e["quote"], re.I)), None)
        if named:
            return named
    return next((e for e in expl if topic and e["topic"] == topic), None)


def low_confidence(row, company):
    """Low-confidence figures shown in a row: (label, figure info, check key)."""
    out = []
    figs = [("reported", row["current"])] + [(k, c["figure"]) for k, c in row["comparisons"].items() if c.get("figure")]
    for label, f in figs:
        if f and f["status"] == "low_confidence":
            out.append((label, f, check_key(company, f["metric"], f["segment"], f["period"], f["value"])))
    return out


def _headline(rows):
    cands = []
    for r in rows:
        cur, est = r["current"], r["comparisons"].get("estimate")
        if not cur or cur["value"] is None or cur["status"] not in ("verified", "manually_verified"):
            continue
        if not est or not est.get("severity") or any(f["status"] == "low_confidence" for _, f, _ in low_confidence(r, "")):
            continue
        size = abs(Decimal(est["change_bps"] or est["change_pct"] or est["change"]))
        cands.append((SEV_RANK[est["severity"]], size, r))
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    pick = [c for c in cands if c[0] >= 2][:5]
    if len(pick) < 3:
        pick += [c for c in cands if c[0] < 2][:3 - len(pick)]
    return [_sentence(r) for _, _, r in pick]


def _sentence(r):
    est = r["comparisons"]["estimate"]
    name = f"{r['segment']} {r['name'][0].lower() + r['name'][1:]}" if r["segment"] else r["name"]
    cur, e = fmt_value(r["current"]["value"], r["unit"]), fmt_value(est["value"], r["unit"])
    if est["change_bps"] is not None:
        size, direction = f"{abs(Decimal(est['change_bps'])):,.0f} bps", Decimal(est["change_bps"])
    elif est["change_pct"] is not None:
        size, direction = f"{abs(Decimal(est['change_pct'])):.1f}%", Decimal(est["change_pct"])
    else:
        size, direction = f"{abs(Decimal(est['change'])):.1f} pp", Decimal(est["change"])
    side = "above" if direction > 0 else "below" if direction < 0 else "in line with"
    tail = f"{size} {side} the estimate of {e}" if direction else f"in line with the estimate of {e}"
    return {"text": f"{name} of {cur} was {tail} ({est['severity'].capitalize()}).", "key": r["key"],
            "severity": est["severity"]}


def _statements(conn, company, quarter, typ):
    return [dict(r) | {"key": statement_key(r)} for r in conn.execute(
        "SELECT * FROM statements WHERE company = ? AND quarter = ? AND type = ? ORDER BY page, id",
        (company, quarter, typ))]


def _guidance(conn, company, quarter, latest):
    out = []
    for topic, status, cur, prior in commentary.guidance_table(conn, company, quarter):
        cur = [dict(s) | {"key": statement_key(s)} for s in cur]
        cur = [s for s in cur if latest.get(s["key"], {}).get("action") != "reject"]
        cur.sort(key=lambda s: latest.get(s["key"], {}).get("action") != "approve")
        prior = [dict(s) for s in prior]
        out.append({"topic": topic, "status": status,
                    "current": [_q(s) for s in cur[:GUIDANCE_PER_SIDE]], "more_current": max(0, len(cur) - GUIDANCE_PER_SIDE),
                    "prior": [_q(s) for s in prior[:GUIDANCE_PER_SIDE]], "more_prior": max(0, len(prior) - GUIDANCE_PER_SIDE)})
    return out


def _q(s):
    return {"quote": s["quote"], "page": s["page"], "speaker": s["speaker"], "key": s.get("key")}


def _gaps(rows, company, cfg):
    gaps = []
    for r in rows:
        label = f"{r['name']}" + (f" – {r['segment']}" if r["segment"] else "")
        cur = r["current"]
        if cur is None or cur["value"] is None:
            gaps.append({"item": label, "reason": (cur or {}).get("note") or "not disclosed this quarter"})
            continue
        for k, c in r["comparisons"].items():
            if c.get("gap"):
                gaps.append({"item": f"{label} vs {k.replace('_', '-')}", "reason": c["gap"]})
        for lbl, f, _ in low_confidence(r, company):
            gaps.append({"item": f"{label} ({lbl}, {f['period']})",
                         "reason": "not verified: " + (f["note"] or "").split("checks failed: ")[-1]})
    return gaps


def _sources(conn, rows, company, quarter):
    ids = set()
    for r in rows:
        for f in [r["current"]] + [c.get("figure") for c in r["comparisons"].values()]:
            if f and f["source"] and f["source"].get("document_id"):
                ids.add(f["source"]["document_id"])
    for (i,) in conn.execute("SELECT DISTINCT document_id FROM statements WHERE company = ? AND quarter IN (?, ?)",
                             (company, quarter, config.COMPARATORS[quarter]["prior"])):
        ids.add(i)
    for (i,) in conn.execute("SELECT DISTINCT document_id FROM estimates WHERE company = ? AND quarter = ?",
                             (company, quarter)):
        ids.add(i)
    quarters = (quarter, *config.COMPARATORS[quarter].values())       # releases used by the cross-check
    for (i,) in conn.execute(f"SELECT id FROM documents WHERE company = ? AND type IN ('results_release', 'press_release')"
                             f" AND quarter IN ({','.join('?' * len(quarters))})", (company, *quarters)):
        ids.add(i)
    docs = conn.execute(f"SELECT * FROM documents WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)).fetchall() if ids else []
    return [{"type": d["type"], "quarter": d["quarter"], "path": d["file_path"], "sha256": d["sha256"],
             "published": d["publication_date"], "url": d["source_url"]}
            for d in sorted(docs, key=lambda d: (d["type"], d["quarter"]))]


def latest_reviews(conn, rid):
    out = {}
    for r in conn.execute("SELECT * FROM reviews WHERE report = ? ORDER BY id", (rid,)):
        if r["action"] == "comment":
            out.setdefault(r["item"], {}).setdefault("comments", []).append(dict(r))
            continue
        prev = out.get(r["item"], {})
        out[r["item"]] = dict(r) | {"comments": prev.get("comments", [])}
    return out


def build(conn, cfg, company, quarter):
    """The report as a JSON-serialisable dict. 'content' is what the fingerprint covers."""
    rid = report_id(company, quarter)
    rows = _rows(conn, cfg, company, quarter)
    latest = latest_reviews(conn, rid)
    comp = cfg.companies[company]
    sample = any(((r["comparisons"].get("estimate") or {}).get("estimate") or {}).get("sample") for r in rows)
    content = {
        "company": company, "company_name": comp["name"], "quarter": quarter, "basis": comp["basis"],
        "period": config.QUARTER_DATES[quarter], "comparators": config.COMPARATORS[quarter],
        "notes": comp.get("report_notes", []), "sample_estimates": sample,
        "headline": _headline(rows), "rows": rows, "guidance": _guidance(conn, company, quarter, latest),
        "flags": [_q(s) | {"category": s["topic"], "label": "for analyst review"}
                  for s in _statements(conn, company, quarter, "flag")],
        "gaps": _gaps(rows, company, cfg), "sources": _sources(conn, rows, company, quarter)}
    return {"id": rid, "content": content, "fingerprint": fingerprint(content), "reviews": latest,
            "items": review_items(conn, content)}


def fingerprint(content):
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


def review_items(conn, content):
    """Every item the analyst must review: metric rows, current guidance statements, flags."""
    items = [r["key"] for r in content["rows"]]
    items += [statement_key(s) for s in _statements(conn, content["company"], content["quarter"], "guidance")]
    items += [f["key"] for f in content["flags"]]
    return items


# ---------------------------------------------------------------- status and approval

def blockers(conn, report):
    """Why the report cannot be approved yet ([] means it can)."""
    out = []
    latest = report["reviews"]
    unreviewed = [i for i in report["items"] if latest.get(i, {}).get("action") not in DONE_ACTIONS]
    if unreviewed:
        out.append(f"{len(unreviewed)} item(s) not yet reviewed")
    company = report["content"]["company"]
    unresolved = [(r["name"], lbl, f["period"]) for r in report["content"]["rows"]
                  for lbl, f, _ in low_confidence(r, company)]
    if unresolved:
        out.append(f"{len(unresolved)} low-confidence figure(s) unresolved: "
                   + "; ".join(f"{n} {lbl} {p}" for n, lbl, p in unresolved[:5]))
    return out


def status(conn, cfg, company, quarter, report=None, user=None):
    """Current status; an approved report whose content changed is returned to draft."""
    rid = report_id(company, quarter)
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
    if row is None or row["status"] == "draft":
        return {"status": "draft", "approved_by": None, "approved_at": None}
    report = report or build(conn, cfg, company, quarter)
    if report["fingerprint"] != row["input_hash"]:
        conn.execute("UPDATE reports SET status = 'draft', updated_at = ? WHERE id = ?", (db.now(), rid))
        db.audit(conn, "report_returned_to_draft", rid, {"approved_hash": row["input_hash"],
                                                         "current_hash": report["fingerprint"]}, user=user)
        conn.commit()
        return {"status": "draft", "approved_by": None, "approved_at": None, "returned": True}
    return {"status": "approved", "approved_by": row["approved_by"], "approved_at": row["approved_at"]}


def approve(conn, cfg, company, quarter, reviewer):
    if not reviewer or not reviewer.strip():
        raise ApprovalError("a reviewer name is required")
    report = build(conn, cfg, company, quarter)
    why = blockers(conn, report)
    if why:
        raise ApprovalError("cannot approve: " + "; ".join(why))
    rid, now = report["id"], db.now()
    snapshot = json.dumps(report | {"status": "approved", "approved_by": reviewer, "approved_at": now}, default=str)
    conn.execute("INSERT INTO reports (id, company, quarter, status, snapshot, input_hash, approved_by, approved_at,"
                 " updated_at) VALUES (?, ?, ?, 'approved', ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET"
                 " status = 'approved', snapshot = excluded.snapshot, input_hash = excluded.input_hash,"
                 " approved_by = excluded.approved_by, approved_at = excluded.approved_at, updated_at = excluded.updated_at",
                 (rid, company, quarter, snapshot, report["fingerprint"], reviewer, now, now))
    conn.execute("INSERT INTO reviews (report, item, reviewer, action, time) VALUES (?, 'report', ?, 'approve', ?)",
                 (rid, reviewer, now))
    db.audit(conn, "report_approved", rid, {"fingerprint": report["fingerprint"]}, user=reviewer)
    conn.commit()
    return report
