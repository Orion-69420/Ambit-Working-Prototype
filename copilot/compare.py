"""Step 8b: compare each reported figure with the prior quarter, the year-ago quarter and the
estimate, and grade the size of each move (procedure Section 2 and Step 8).

Which copy of a comparator is used (procedure: "comparators are read from the current filing
wherever available; otherwise from that quarter's own filing"):
  1. the copy read from the target quarter's own document
  2. the copy read from the comparator quarter's own document
  3. any other document's copy (for example M&M Q4 FY26 KPIs read from the Q1 FY27 deck)
XBRL figures exist only in their own filing, so they always come from (2).

Changes
  pct  change % = (current - comparator) / comparator x 100; a zero or negative base gives n.m.
  bps  change in basis points = (current - comparator) x 100 (margins and other % levels)
  pp   change in percentage points = current - comparator (growth rates)
Severity uses the value as stored (rounded to 2 decimals), so boundaries grade consistently.
"""
from decimal import ROUND_HALF_UP, Decimal

from copilot import config, db

D2 = Decimal("0.01")


def severity(size, group):
    """size: absolute change in the group's unit. low < low_below <= medium <= high_above < high."""
    if size is None:
        return None
    size = abs(size)
    if size < Decimal(str(group["low_below"])):
        return "low"
    if size > Decimal(str(group["high_above"])):
        return "high"
    return "medium"


def change(current, base, change_as):
    """Return dict(change, change_pct, change_bps, not_meaningful, size) for one comparison."""
    diff = (current - base).quantize(D2, ROUND_HALF_UP)
    out = dict(change=diff, change_pct=None, change_bps=None, not_meaningful=0, size=None)
    if change_as == "pct":
        if base <= 0:
            out["not_meaningful"] = 1                       # zero or negative base: absolute change only
        else:
            out["change_pct"] = ((current - base) / base * 100).quantize(D2, ROUND_HALF_UP)
            out["size"] = out["change_pct"]
    elif change_as == "bps":
        out["change_bps"] = ((current - base) * 100).quantize(D2, ROUND_HALF_UP)
        out["size"] = out["change_bps"]
    else:                                                   # pp
        out["size"] = diff
    return out


def pick(conn, company, metric, segment, period, target):
    """The figure to use for (metric, segment, period) in the report for target quarter."""
    rows = conn.execute(
        "SELECT * FROM figures WHERE company = ? AND metric = ? AND segment IS ? AND period = ?"
        " AND supersedes IS NULL ORDER BY id", (company, metric, segment, period)).fetchall()
    corrected = {r["supersedes"]: r for r in conn.execute(
        "SELECT * FROM figures WHERE company = ? AND metric = ? AND segment IS ? AND period = ?"
        " AND supersedes IS NOT NULL ORDER BY id", (company, metric, segment, period))}
    rows = [corrected.get(r["id"], r) for r in rows]          # an analyst correction replaces its original
    with_value = [r for r in rows if r["value"] is not None]
    for pref in (target, period):
        for r in with_value:
            if r["quarter"] == pref:
                return r
    if with_value:
        return max(with_value, key=lambda r: config.QUARTERS.index(r["quarter"]) if r["quarter"] in config.QUARTERS else -1)
    return rows[0] if rows else None


def ensure_gap_rows(conn, cfg, company, target):
    """Annual-only metrics have no quarterly figure: record them as missing so they reach Gaps."""
    for m in cfg.metrics_for(company):
        if m["period"] != "annual_only":
            continue
        if conn.execute("SELECT 1 FROM figures WHERE company = ? AND metric = ? AND period = ?",
                        (company, m["id"], target)).fetchone():
            continue
        conn.execute("INSERT INTO figures (company, quarter, metric, period, basis, value, unit, method,"
                     " status, note, created_at) VALUES (?, ?, ?, ?, ?, NULL, ?, 'xbrl', 'missing', ?, ?)",
                     (company, target, m["id"], target, m.get("basis", "consolidated"), m["unit"],
                      m["gap_reason"], db.now()))


def run(conn, cfg, company="all", quarter="all", user=None):
    """Compute comparisons for each target quarter. Returns {(company, target): summary dict}."""
    companies = list(cfg.companies) if company == "all" else [company]
    targets = config.TARGET_QUARTERS if quarter == "all" else [q for q in [quarter] if q in config.TARGET_QUARTERS]
    summary = {}
    for c in companies:
        for t in targets:
            ensure_gap_rows(conn, cfg, c, t)
            comps = config.COMPARATORS[t]
            s = {"comparisons": 0, "gaps": 0, "missing_current": 0, "low": 0, "medium": 0, "high": 0, "n.m.": 0}
            for m in cfg.metrics_for(c):
                segments = list(cfg.companies[c]["segments"]) if m.get("per_segment") else [None]
                group = cfg.thresholds.get(m.get("threshold_group"))
                for seg in segments:
                    cur = pick(conn, c, m["id"], seg, t, t)
                    if cur is None or cur["value"] is None:
                        s["missing_current"] += 1
                        continue
                    conn.execute("DELETE FROM comparisons WHERE figure_id = ?", (cur["id"],))
                    a = db.from_db(cur["value"])
                    targets_ = [(k, pick(conn, c, m["id"], seg, p, t), None) for k, p in comps.items()]
                    est = conn.execute("SELECT * FROM estimates WHERE company = ? AND quarter = ? AND metric = ?"
                                       " AND segment IS ?", (c, t, m["id"], seg)).fetchone()
                    targets_.append(("estimate", None, est))
                    for kind, fig, e in targets_:
                        base_row = fig if kind != "estimate" else e
                        gap = None
                        if base_row is None:
                            gap = "no estimate in the model" if kind == "estimate" else f"no {kind.replace('_', '-')} figure"
                        elif base_row["value"] is None:
                            gap = ("estimate cell has no value" if kind == "estimate"
                                   else f"{kind.replace('_', '-')} figure missing: {base_row['note'] or 'not disclosed'}")
                        if gap:
                            conn.execute("INSERT INTO comparisons (figure_id, comparator, comparator_figure_id,"
                                         " comparator_estimate_id, gap_reason) VALUES (?, ?, ?, ?, ?)",
                                         (cur["id"], kind, fig["id"] if fig else None, e["id"] if e else None, gap))
                            s["gaps"] += 1
                            continue
                        ch = change(a, db.from_db(base_row["value"]), m["change_as"])
                        sev = severity(ch["size"], group) if not ch["not_meaningful"] else None
                        conn.execute("INSERT INTO comparisons (figure_id, comparator, comparator_figure_id,"
                                     " comparator_estimate_id, change, change_pct, change_bps, not_meaningful,"
                                     " severity) VALUES (?,?,?,?,?,?,?,?,?)",
                                     (cur["id"], kind, fig["id"] if fig else None, e["id"] if e else None,
                                      db.to_db(ch["change"]), db.to_db(ch["change_pct"]), db.to_db(ch["change_bps"]),
                                      ch["not_meaningful"], sev))
                        s["comparisons"] += 1
                        s[sev or "n.m."] += 1
            db.audit(conn, "comparisons_computed", f"{c}/{t}", s, user=user)
            summary[(c, t)] = s
    conn.commit()
    return summary
