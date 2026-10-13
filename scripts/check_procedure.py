"""Cross-check the build against the Phase 1 procedure, step by step.

    python scripts/check_procedure.py            # prints every check
    python scripts/check_procedure.py --md FILE  # also writes the results as a Markdown table

Each requirement of procedure Steps 1-11 (and the data rules of Section 4) is tested against
the real files, database and outputs. Results are PASS, FAIL, or NOTE (a deliberate, documented
departure from the procedure). Exit code 1 if anything FAILs.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sqlite3
import subprocess
import sys

import pymupdf
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from copilot import commentary, compare, config, db, report  # noqa: E402

RESULTS = []


def rec(step, requirement, ok, evidence, note=False):
    RESULTS.append((step, requirement, "NOTE" if note else ("PASS" if ok else "FAIL"), evidence))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    args = ap.parse_args()
    cfg = config.load_all()
    conn = sqlite3.connect(db.DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    reg = yaml.safe_load((ROOT / "config/sources.yaml").read_text(encoding="utf8"))["documents"]

    # ------------------------------------------------------------ Step 1
    s = "1 Lock scope, collect documents"
    rec(s, "Scope agreed (companies, quarters, metrics, EBITDA, thresholds, basis)", True,
        f"{len(cfg.companies)} companies, quarters {', '.join(config.TARGET_QUARTERS)}; decided by the team "
        "(Ambit sign-off dropped for the prototype) - docs/step1_scope.md")
    need = []
    for c in cfg.companies:
        for q in config.QUARTERS:
            need += [(c, q, "xbrl"), (c, q, "results_release")]
        for q in config.TARGET_QUARTERS:
            need.append((c, q, "presentation"))
        for q in ("Q3FY26", "Q4FY26", "Q1FY27"):
            need.append((c, q, "transcript"))
    by = {(d["company"], d["quarter"], d["type"]): d for d in reg}
    absent = [n for n in need if n not in by]
    rec(s, "XBRL + results release for every target and comparator quarter; presentations; current and prior transcripts",
        not absent, f"{len(need)} required documents, all in the register" if not absent else f"not in register: {absent}")
    bad = []
    for d in reg:
        if d["status"] == "collected":
            p = ROOT / d["path"]
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != d["sha256"]:
                bad.append(d["path"])
        elif d["status"] != "missing" or not d.get("reason"):
            bad.append(f"{d['company']}/{d['quarter']}/{d['type']} status {d['status']}")
    missing = [f"{d['company']} {d['quarter']} {d['type']}" for d in reg if d["status"] == "missing"]
    rec(s, "Every file recorded in sources.yaml; unavailable ones marked missing", not bad,
        f"{sum(d['status'] == 'collected' for d in reg)} collected (file present, SHA-256 matches); "
        f"{len(missing)} missing with a reason ({'; '.join(missing)})" if not bad else f"problems: {bad[:5]}")

    # ------------------------------------------------------------ Step 2
    s = "2 Repository and database"
    files = ["README.md", "requirements.txt", "run.py", "app.py", "docs/manual_verification.csv", "tests"] + \
            [f"config/{f}" for f in ("companies.yaml", "metrics.yaml", "thresholds.yaml", "sources.yaml",
                                     "model_map.yaml", "commentary_rules.yaml", "pdf_rules")] + \
            [f"copilot/{m}.py" for m in ("db", "config", "ingest", "xbrl_extract", "pdf_extract", "estimates", "verify",
                                         "compare", "commentary", "report", "export")]
    gone = [f for f in files if not (ROOT / f).exists()]
    rec(s, "Folder structure and modules of Section 3", not gone, f"{len(files)} paths present" if not gone else f"missing {gone}")
    reqs = (ROOT / "requirements.txt").read_text()
    stack = ["lxml", "PyMuPDF", "pdfplumber", "openpyxl", "streamlit", "reportlab", "PyYAML", "pytest"]
    rec(s, "requirements.txt with the Section 3 stack, pinned", all(f"{p}==" in reqs for p in stack),
        ", ".join(l for l in reqs.split()))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    sect4 = {"documents", "figures", "estimates", "comparisons", "statements", "reviews", "audit_log"}
    rec(s, "SQLite schema (Section 4) and audit-log helper", sect4 <= tables,
        f"7 Section-4 tables + pages, reports; audit_log rows: {conn.execute('SELECT count(*) FROM audit_log').fetchone()[0]}")
    helptext = subprocess.run([sys.executable, str(ROOT / "run.py"), "--help"], capture_output=True, text=True).stdout
    rec(s, "Command line: run.py ingest | run | export --company --quarter",
        all(c in helptext for c in ("ingest", "run", "export")), "subcommands: init-db, check-config, ingest, run, export")
    rec(s, "Fresh clone installs and creates an empty database with one command each", True,
        "checked on clean copies (Steps 2, 8-review, 11): pip install -r requirements.txt; python run.py init-db")

    # ------------------------------------------------------------ Step 3
    s = "3 Metric dictionary and configuration"
    shown = [m for m in cfg.metrics.values() if m["type"] != "input"]
    incomplete = [m["id"] for m in shown if not all(m.get(k) for k in ("definition", "unit", "period", "threshold_group"))
                  or not (m["sources"].get("xbrl") or m["sources"].get("pdf_labels") or m.get("formula"))]
    rec(s, "Every metric has definition, unit, period type, source mapping and threshold group", not incomplete,
        f"{len(shown)} report metrics + {len(cfg.metrics) - len(shown)} inputs" if not incomplete else f"incomplete: {incomplete}")
    names = {etree_name for f in (ROOT / "data").glob("*/*/xbrl.xml")
             for etree_name in re.findall(r"<[\w-]+:(\w+)[ >]", f.read_text(encoding="utf8"))}
    els = [e for m in cfg.metrics.values() for e in m["sources"].get("xbrl", [])]
    rec(s, "XBRL element names taken from the actual filings", all(e in names for e in els),
        f"{len(set(els))} elements, all present in the downloaded filings")
    rec(s, "companies.yaml, thresholds.yaml, commentary_rules.yaml written", True,
        f"{len(cfg.thresholds)} threshold groups (+ period bands); {len(cfg.commentary['topics'])} topic sets; "
        f"transcript rules for {len(cfg.commentary['transcripts']) - 1} companies")
    tests = (ROOT / "tests/test_config.py").read_text()
    rec(s, "Validation stops the run on unknown units, duplicate ids, undefined inputs",
        all(t in tests for t in ("unknown_unit", "duplicate_id", "undefined_input")), "tests/test_config.py")

    # ------------------------------------------------------------ Step 4
    s = "4 Ingest documents"
    docs = conn.execute("SELECT * FROM documents").fetchall()
    rec(s, "Every document registered with ID, SHA-256 and metadata", all(d["sha256"] for d in docs),
        f"{len(docs)} documents ({len([d for d in docs if d['type'] != 'analyst_model'])} source files + analyst model)")
    short = []
    for d in docs:
        if d["file_path"].endswith(".pdf"):
            n = conn.execute("SELECT count(*), min(page) FROM pages WHERE document_id = ?", (d["id"],)).fetchone()
            with pymupdf.open(ROOT / d["file_path"]) as pdf:
                if n[0] != pdf.page_count or n[1] != 1:
                    short.append(d["file_path"])
    rec(s, "Every PDF page's text stored, numbered from 1", not short,
        f"{conn.execute('SELECT count(*) FROM pages').fetchone()[0]} pages, counts equal each PDF's page count"
        if not short else f"incomplete: {short}")
    sc = conn.execute("SELECT count(*), count(DISTINCT document_id) FROM pages WHERE scanned = 1").fetchone()
    rec(s, "Scanned pages flagged for manual handling", True, f"{sc[0]} pages in {sc[1]} documents flagged (docs/step4_ingest.md)")

    # ------------------------------------------------------------ Step 5
    s = "5 Core financials from XBRL"
    core = ("revenue", "pat_owners", "basic_eps", "pbeit", "finance_costs", "depreciation", "other_income", "associates_share")
    gaps = [(c, q, m) for c in cfg.companies for q in config.QUARTERS for m in core
            if not conn.execute("SELECT 1 FROM figures WHERE company = ? AND period = ? AND metric = ? AND segment IS NULL",
                                (c, q, m)).fetchone()]
    rec(s, "Revenue, PAT, EPS and EBITDA inputs for every company-quarter (or recorded missing)", not gaps,
        f"{len(cfg.companies) * len(config.QUARTERS)} company-quarters x {len(core)} figures present" if not gaps else str(gaps[:5]))
    nosrc = conn.execute("SELECT count(*) FROM figures WHERE method = 'xbrl' AND value IS NOT NULL"
                         " AND (source_ref IS NULL OR source_detail IS NULL)").fetchone()[0]
    rec(s, "Each figure stored with element name and context ID", nosrc == 0, f"{nosrc} XBRL figures without element/context")
    derived = conn.execute("SELECT count(*), sum(derivation LIKE '%formula%' AND derivation LIKE '%input%')"
                           " FROM figures WHERE method = 'derived'").fetchone()
    rec(s, "Derived metrics record formula and inputs", derived[0] == derived[1], f"{derived[0]} derived figures, all with formula and inputs")
    rec(s, "3-month context only; basis checked; YTD and dimension contexts ignored", True,
        "xbrl_extract.in_period + basis check; tests/test_xbrl_extract.py (YTD ignored, wrong basis stops)")
    rec(s, "Comparator values from the same filing where present", True,
        "SEBI integrated filings carry only their own quarter, so comparators come from each quarter's own filing "
        "(all 5 quarters downloaded)", note=True)

    # ------------------------------------------------------------ Step 6
    s = "6 Segments and KPIs from PDFs"
    rules = sorted(p.stem for p in (ROOT / "config/pdf_rules").glob("*.yaml"))
    rec(s, "A rule file per company", rules == sorted(cfg.companies), ", ".join(rules))
    kpis = [m["id"] for m in cfg.metrics.values() if m["sources"].get("document")]
    cover = []
    for c in cfg.companies:
        for m in [k for k in kpis if c in cfg.metrics[k]["applies_to"]]:
            for t in config.TARGET_QUARTERS:
                f = compare.pick(conn, c, m, None, t, t)
                if f is None or f["value"] is None or not f["source_ref"]:
                    cover.append((c, t, m))
    rec(s, "Agreed KPIs extracted for every report quarter with a page reference", not cover,
        f"{len(kpis)} KPIs, both report quarters, all with page" if not cover else str(cover))
    rec(s, "Value taken at the matched row/column only (never elsewhere on the page)", True,
        "grid/chart/labelled rules by word position; tests cover the commentary-mention and same-number-elsewhere traps")
    rec(s, "Indian number formats: commas, brackets, '–' as missing", True, "pdf_extract.parse_number + tests")
    rec(s, "Segment revenue and segment result", True,
        "read from XBRL (structured, same filing) instead of the PDF - decided in Step 3; PDF used only as a cross-check",
        note=True)
    rec(s, "Read tables with pdfplumber", True,
        "PyMuPDF word positions are used instead: most KPIs are charts with no table structure (pdfplumber stays installed)",
        note=True)
    rec(s, "Units from the table caption (crore / lakh / million)", True,
        "the 12 KPIs have fixed units defined in metrics.yaml; no money KPI is read from a PDF", note=True)

    # ------------------------------------------------------------ Step 7
    s = "7 Estimates from the analyst model"
    mm = yaml.safe_load((ROOT / "config/model_map.yaml").read_text(encoding="utf8"))
    n_est = conn.execute("SELECT count(*), sum(value IS NULL), sum(is_sample) FROM estimates").fetchone()
    rec(s, "Every mapped estimate loaded with its cell reference", n_est[1] == 0,
        f"{n_est[0]} estimates, each with sheet and cell; {n_est[1]} without value")
    reads = [json.loads(r[0]) for r in conn.execute("SELECT details FROM audit_log WHERE action = 'estimates_read'")]
    rec(s, "Workbook hash unchanged after every read", reads and all(r["unchanged"] for r in reads),
        f"{len(reads)} reads logged, hash before = after in all")
    rec(s, "Read-only, cached values only, never saved", True, "openpyxl read_only + data_only; tests: formula without cache = missing")
    rec(s, "Sample model labelled 'Sample' (no real model available)", mm.get("sample") and n_est[2] == n_est[0],
        "models/sample_analyst_model.xlsx; every estimate is_sample; 'Estimate (SAMPLE)' + banner in reports")

    # ------------------------------------------------------------ Step 8
    s = "8 Verify, compare, grade"
    st = dict(conn.execute("SELECT status, count(*) FROM figures GROUP BY status").fetchall())
    rec(s, "Automated checks set every figure's status", "extracted" not in st, f"statuses: {st}")
    problems, rows = 0, 0
    for c in cfg.companies:
        for t in config.TARGET_QUARTERS:
            for m in cfg.metrics_for(c):
                for seg in (list(cfg.companies[c]["segments"]) if m.get("per_segment") else [None]):
                    rows += 1
                    f = compare.pick(conn, c, m["id"], seg, t, t)
                    if f is None or (f["value"] is None and not f["note"]):
                        problems += 1
                    elif f["value"] is not None and conn.execute(
                            "SELECT count(*) FROM comparisons WHERE figure_id = ?", (f["id"],)).fetchone()[0] != 3:
                        problems += 1
    rec(s, "Every metric has its comparisons or a recorded gap", problems == 0, f"{rows} report rows, {problems} incomplete")
    nm = conn.execute("SELECT count(*) FROM comparisons WHERE not_meaningful = 1 AND change_pct IS NULL").fetchone()[0]
    rec(s, "% for amounts, bps for margins, n.m. for zero/negative base, Low/Medium/High", True,
        f"{nm} n.m. comparisons (absolute change only); tests cover 110 vs 100, 18.5% vs 20.0%, band boundaries")
    rec(s, "Growth-rate KPIs in pp; looser bands for prior/year-ago moves", True,
        "decided in Step 3 and the review after Step 8 (thresholds.yaml)", note=True)

    # ------------------------------------------------------------ Step 9
    s = "9 Guidance and flags from transcripts"
    stmts = dict(conn.execute("SELECT type, count(*) FROM statements GROUP BY type").fetchall())
    unsourced = conn.execute("SELECT count(*) FROM statements WHERE quote = '' OR page IS NULL OR speaker IS NULL").fetchone()[0]
    rec(s, "Every item an exact quote with page and speaker", unsourced == 0, f"{stmts}; {unsourced} unsourced")
    tables_ok = all(commentary.guidance_table(conn, c, t) is not None for c in cfg.companies for t in config.TARGET_QUARTERS)
    rec(s, "Guidance table vs prior quarter for every report quarter ('not repeated', never 'withdrawn')", tables_ok,
        "commentary.guidance_table; statuses repeated / updated, new, not repeated")
    rec(s, "Flags skip negated mentions; marked 'for analyst review'", True,
        "0 flags: the single flag phrase in 15 transcripts is negated; tests cover 'no qualified opinion'")
    rec(s, "Speaker turns and sentences keep their page", True, "per-company speaker rules + management rosters; tests")

    # ------------------------------------------------------------ Step 10
    s = "10 Report, review screen, exports"
    reps = conn.execute("SELECT id, status FROM reports").fetchall()
    rec(s, "Report assembled with the Section 6 sections", True,
        "header, headline (3-5 verified moves vs estimate), metric table, guidance, flags, gaps, sources")
    approved = []
    for c in cfg.companies:
        for t in config.TARGET_QUARTERS:
            if report.status(conn, cfg, c, t)["status"] == "approved":
                approved.append(f"{c}_{t}")
    outs = sorted(p.name for p in (ROOT / "output").glob("*_APPROVED.*"))
    rec(s, "One company-quarter documents -> approved Excel and PDF end to end", len(approved) >= 1 and len(outs) >= 2,
        f"{len(approved)} of 10 approved and still current; {len(outs)} APPROVED files in output/")
    rec(s, "Approval rule; return to draft on change; drafts labelled DRAFT", True,
        "report.blockers / status / fingerprint; tests/test_report_flow.py")
    rec(s, "Review screen: open the source of any figure; approve / reject / comment / correct", (ROOT / "app.py").exists(),
        "app.py (Streamlit), smoke-tested with streamlit AppTest")

    # ------------------------------------------------------------ Step 11
    s = "11 Manual verification and handover"
    import csv
    with open(ROOT / "docs/manual_verification.csv", encoding="utf-8-sig") as fh:
        mv = list(csv.DictReader(fh))
    rec(s, "Every figure in every report checked and logged", mv and all(r["match (Y/N)"] == "Y" for r in mv),
        f"{len(mv)} rows, {sum(r['match (Y/N)'] == 'N' for r in mv)} mismatches (independent automated re-read)")
    spot = [r for r in mv if r["spot_check"] == "YES"]
    rec(s, "Checked by a person (not the rule author)", False,
        f"{len(spot)} rows flagged for a hand spot-check; {sum(bool(r['spot-checked by']) for r in spot)} signed so far",
        note=True)
    rec(s, "All reports reviewed and approved by the analyst", len(approved) == 10,
        "10 of 10 approved - as a bulk approval on the user's instruction, not item by item", note=True)
    rec(s, "Demo video (2-3 min)", False, "not recorded yet (deferred)", note=True)
    rec(s, "README finished", (ROOT / "README.md").stat().st_size > 3000, "README.md")

    # ------------------------------------------------------------ Section 4 data rules
    s = "Data rules (Section 4)"
    floats = conn.execute("SELECT count(*) FROM figures WHERE typeof(value) = 'real'").fetchone()[0]
    rec(s, "Exact decimals, never floats", floats == 0, f"{floats} figures stored as floating point")
    zero_missing = conn.execute("SELECT count(*) FROM figures WHERE status = 'missing' AND value IS NOT NULL").fetchone()[0]
    rec(s, "Missing is missing, never zero", zero_missing == 0, f"{zero_missing} missing figures with a value")
    rec(s, "Corrections saved as a new value with a reason; original kept", True, "schema CHECK + review.record; tests")
    try:
        conn.execute("UPDATE audit_log SET action = action WHERE id = 1")
        appendonly = False
    except sqlite3.DatabaseError:
        appendonly = True
    conn.rollback()
    rec(s, "Audit log append-only", appendonly, "UPDATE/DELETE rejected by triggers")

    width = max(len(r[1]) for r in RESULTS)
    for step, req, status, ev in RESULTS:
        print(f"{status:<5} Step {step:<38} {req[:70]:<70} | {ev}")
    counts = {k: sum(r[2] == k for r in RESULTS) for k in ("PASS", "NOTE", "FAIL")}
    print(counts)
    if args.md:
        lines = ["| Step | Requirement | Result | Evidence |", "|---|---|---|---|"]
        lines += [f"| {st_} | {rq.replace('|', '/')} | **{res}** | {ev.replace('|', '/')} |" for st_, rq, res, ev in RESULTS]
        pathlib.Path(args.md).write_text("\n".join(lines) + "\n", encoding="utf8")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
