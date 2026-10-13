"""Step 11: fill docs/manual_verification.csv by re-reading every displayed figure from its source.

    python scripts/verify_register.py

For every figure shown in every approved report (reported value, prior quarter, year-ago and
estimate), the value is read again from the source document through a path that does NOT use
the extraction code, so an extraction bug would show up as a mismatch:

  XBRL      raw XML text, located by element name and context id with a plain pattern
  PDF       the cited page opened afresh with PyMuPDF; the printed number must be on it
  derived   recomputed from raw XBRL values with the dictionary formula
  estimate  the analyst-model cell read with openpyxl

Rows are marked 'automated re-read'. A stratified sample is flagged for the team to check by
hand ('spot_check' = YES); the team fills the spot-check columns and signs them.
"""
import csv
import datetime as dt
import json
import pathlib
import random
import re
import sqlite3
import sys
from decimal import Decimal

import pymupdf
from openpyxl import load_workbook

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from copilot import config, db, derive, report  # noqa: E402

OUT = ROOT / "docs" / "manual_verification.csv"
CHECKER = "automated re-read (scripts/verify_register.py)"
HEAD = ["report", "metric", "period", "displayed value", "source and page", "value found in source",
        "match (Y/N)", "checked by", "date", "notes", "spot_check", "spot-checked by", "spot-check date",
        "spot-check result"]
SAMPLE_PER_REPORT = 3


def raw_fact(xml_text, element, context):
    m = re.search(r"<[\w-]+:" + re.escape(element) + r'\b[^>]*contextRef="' + re.escape(context) + r'"[^>]*>([^<]*)<',
                  xml_text)
    return m.group(1).strip() if m else None


def raw_by_element(xml_text, element, start, end, instant=False):
    """Value of an undimensioned fact for a period, found from the raw contexts (for derived inputs)."""
    ctx = re.findall(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', xml_text, re.S)
    for cid, body in ctx:
        if "explicitMember" in body or "typedMember" in body:
            continue
        ok = (f"<xbrli:instant>{end}</xbrli:instant>" in body) if instant else (
            f"<xbrli:startDate>{start}</xbrli:startDate>" in body and f"<xbrli:endDate>{end}</xbrli:endDate>" in body)
        if ok:
            v = raw_fact(xml_text, element, cid)
            if v is not None:
                return v
    return None


class Reader:
    def __init__(self, conn, cfg):
        self.conn, self.cfg, self.xml, self.wb = conn, cfg, {}, None

    def xml_text(self, company, quarter):
        key = (company, quarter)
        if key not in self.xml:
            d = self.conn.execute("SELECT file_path FROM documents WHERE company = ? AND quarter = ? AND type = 'xbrl'"
                                  " ORDER BY id DESC LIMIT 1", key).fetchone()
            self.xml[key] = (ROOT / d["file_path"]).read_text(encoding="utf8")
        return self.xml[key]

    def scale(self, unit):
        return Decimal(self.cfg.units[unit].get("scale_from_xbrl", 1))

    def derived(self, company, metric, period):
        m = self.cfg.metrics[metric]
        start, end = config.QUARTER_DATES[period]
        text = self.xml_text(company, period)
        vals = {}
        for name in m["inputs"]:
            im = self.cfg.metrics[name]
            if im["type"] == "derived":
                vals[name] = self.derived(company, name, period)
                continue
            raw = raw_by_element(text, im["sources"]["xbrl"][0], start, end, im["period"] == "point_in_time")
            vals[name] = None if raw is None else Decimal(raw) / self.scale(im["unit"])
        return derive.evaluate(m["formula"], vals)

    def estimate(self, sheet, cell):
        if self.wb is None:
            mm = config.load("model_map.yaml")
            self.wb = load_workbook(ROOT / mm["workbook"], read_only=True, data_only=True)
        v = self.wb[sheet][cell].value
        return None if v is None else Decimal(repr(v))


def check(reader, company, row, f, kind, est=None):
    """(source text, value found, match, note) for one displayed value."""
    unit = row["unit"]
    shown = Decimal(str(f["value"])) if f and f.get("value") is not None else None
    if kind == "estimate":
        found = reader.estimate(est["sheet"], est["cell"])
        return f"Analyst model {est['sheet']}!{est['cell']} (SAMPLE)", found, found == shown, ""
    src = f["source"] or {}
    if f["method"] == "derived" or src.get("kind") == "derived":
        found = reader.derived(company, f["metric"], f["period"])
        return src.get("text", "derived"), found, found is not None and abs(found - shown) < Decimal("0.0001"), \
            "recomputed from raw XBRL"
    if src.get("kind") == "xbrl":
        element = src["element"].split(" [")[0]
        raw = raw_fact(reader.xml_text(company, src["doc_quarter"]), element, src["context"])
        found = None if raw is None else Decimal(raw) / reader.scale(unit)
        return src["text"], found, found == shown, f"raw XML value {raw}"
    if src.get("kind") == "pdf":
        d = reader.conn.execute("SELECT file_path FROM documents WHERE id = ?", (src["document_id"],)).fetchone()
        with pymupdf.open(ROOT / d["file_path"]) as pdf:
            text = pdf[src["page"] - 1].get_text()
        # the number as it would be printed: plain decimal, with or without a trailing %
        plain = format(shown.normalize(), "f")
        variants = {plain, f"{shown:.1f}", f"{shown:.2f}", f"{shown:,}"}
        hit = next((v for v in variants if re.search(r"(?<![\d.,])" + re.escape(v) + r"(?![\d])", text)), None)
        return src["text"], (shown if hit else None), hit is not None, f"printed as {hit!r} on the page" if hit else \
            "number not found on the cited page"
    return src.get("text", "no source"), None, False, f.get("note") or ""


def main():
    cfg = config.load_all()
    conn = sqlite3.connect(db.DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    reader = Reader(conn, cfg)
    today = dt.date.today().isoformat()
    rows, mismatches = [], []
    for company in cfg.companies:
        for quarter in config.TARGET_QUARTERS:
            rec = conn.execute("SELECT snapshot, status FROM reports WHERE id = ?",
                               (report.report_id(company, quarter),)).fetchone()
            snap = json.loads(rec["snapshot"])["content"] if rec and rec["status"] == "approved" else \
                report.build(conn, cfg, company, quarter)["content"]
            rid = report.report_id(company, quarter)
            for r in snap["rows"]:
                label = r["name"] + (f" – {r['segment']}" if r["segment"] else "")
                cur = r["current"]
                if not cur or cur.get("value") is None:
                    continue
                items = [("reported", cur, None)]
                for k, c in r["comparisons"].items():
                    if c.get("gap") or c.get("value") is None:
                        continue
                    items.append((k, c.get("figure") or {"value": c["value"]}, c.get("estimate")))
                for kind, f, est in items:
                    if kind == "estimate":
                        f = {"value": r["comparisons"]["estimate"]["value"]}
                    src, found, ok, note = check(reader, company, r, f, kind, est)
                    period = quarter if kind in ("reported", "estimate") else f["period"]
                    row = {"report": rid, "metric": label + ("" if kind == "reported" else f" ({kind.replace('_', '-')})"),
                           "period": period, "displayed value": report.fmt_value(f["value"], r["unit"]),
                           "source and page": src, "value found in source":
                               "—" if found is None else report.fmt_value(found, r["unit"]),
                           "match (Y/N)": "Y" if ok else "N", "checked by": CHECKER, "date": today, "notes": note,
                           "spot_check": "", "spot-checked by": "", "spot-check date": "", "spot-check result": ""}
                    rows.append(row)
                    if not ok:
                        mismatches.append(row)
    # stratified sample for the team: per report, one XBRL, one PDF (if any) and one other value
    rnd = random.Random(20261013)
    for rid in sorted({r["report"] for r in rows}):
        mine = [r for r in rows if r["report"] == rid]
        groups = [[r for r in mine if r["source and page"].startswith("XBRL")],
                  [r for r in mine if " p. " in r["source and page"]],
                  [r for r in mine if not r["source and page"].startswith("XBRL") and " p. " not in r["source and page"]]]
        picked = [rnd.choice(g) for g in groups if g][:SAMPLE_PER_REPORT]
        for r in picked:
            r["spot_check"] = "YES"
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} figures, {len(mismatches)} mismatches, "
          f"{sum(r['spot_check'] == 'YES' for r in rows)} flagged for a hand spot-check")
    for m in mismatches[:30]:
        print("  MISMATCH", m["report"], m["metric"], m["period"], m["displayed value"], "|", m["value found in source"],
              "|", m["source and page"], "|", m["notes"])
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
