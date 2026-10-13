"""Command line for the Results-to-Thesis Copilot.

    python run.py init-db
    python run.py check-config
    python run.py ingest --company MM --quarter Q1FY27
    python run.py run    --company MM --quarter Q1FY27
    python run.py export --company MM --quarter Q1FY27

--company and --quarter accept "all".
"""
import argparse
import pathlib
import sys

from copilot import commentary, compare, config, db, estimates, ingest, pdf_extract, verify, xbrl_extract

# Company/quarter subcommands and the procedure step that builds them
STEPS = {"ingest": "Step 4", "run": "Steps 5-9", "export": "Step 10"}
PENDING = {"export"}


def parse(argv):
    companies = list(config.companies())
    ap = argparse.ArgumentParser(prog="run.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(db.DEFAULT_DB), help="SQLite file (default: %(default)s)")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="create an empty database")
    sub.add_parser("check-config", help="validate config/*.yaml and summarise the metric dictionary")
    for name, step in STEPS.items():
        p = sub.add_parser(name, help=f"procedure {step}" + (" (not built yet)" if name in PENDING else ""))
        p.add_argument("--company", required=True, choices=companies + ["all"])
        p.add_argument("--quarter", required=True, choices=list(config.QUARTERS) + ["all"])
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    if args.command == "init-db":
        conn = db.init_db(args.db)
        n = conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
        print(f"database ready: {args.db} ({n} tables)")
        return 0
    try:
        cfg = config.load_all()
    except config.ConfigError as e:
        print(e, file=sys.stderr)
        return 1
    if args.command == "check-config":
        for cid in cfg.companies:
            shown = [m["id"] for m in cfg.metrics_for(cid)]
            print(f"{cid:<11} {len(shown):>2} metrics: {', '.join(shown)}")
        print(f"config OK: {len(cfg.metrics)} metrics, {len(cfg.thresholds)} threshold groups")
        return 0
    if args.command in PENDING:
        print(f"'{args.command}' is not built yet ({STEPS[args.command]} of the procedure).",
              file=sys.stderr)
        return 2
    if not pathlib.Path(args.db).exists():
        print(f"no database at {args.db}; run 'python run.py init-db' first", file=sys.stderr)
        return 1
    conn = db.connect(args.db)
    if args.command == "ingest":
        return report_ingest(ingest.run(conn, args.company, args.quarter))
    if args.command == "run":
        code = report_run(xbrl_extract.run(conn, cfg, args.company, args.quarter))
        code = max(code, report_kpis(pdf_extract.run(conn, cfg, args.company, args.quarter)))
        code = max(code, report_estimates(conn, cfg, args))
        code = max(code, report_checks(conn, verify.run(conn, cfg, args.company, args.quarter),
                                       compare.run(conn, cfg, args.company, args.quarter)))
        return max(code, report_commentary(conn, commentary.run(conn, cfg, args.company, args.quarter), args))


def report_commentary(conn, results, args):
    print()
    print(f"{'company':<11}{'transcript':<11}{'guidance':>9}{'explain':>8}{'flags':>6}  management speakers")
    for (c, q), r in results.items():
        if isinstance(r, str):
            print(f"{c:<11}{q:<11}  {r}")
            continue
        n = {t: sum(s['type'] == t for s in r['statements']) for t in ('guidance', 'explanation', 'flag')}
        mgmt = sorted({s for s, role in r['speakers'] if role == 'management'})
        print(f"{c:<11}{q:<11}{n['guidance']:>9}{n['explanation']:>8}{n['flag']:>6}  {', '.join(mgmt)[:70]}")
    print()
    print("guidance vs prior quarter (topic: status)")
    companies = list(config.companies()) if args.company == "all" else [args.company]
    targets = config.TARGET_QUARTERS if args.quarter == "all" else [q for q in [args.quarter] if q in config.TARGET_QUARTERS]
    for c in companies:
        for t in targets:
            rows = commentary.guidance_table(conn, c, t)
            print(f"  {c:<11}{t:<8}" + "; ".join(f"{topic}: {st}" for topic, st, _, _ in rows))
    return 0


def report_checks(conn, checks, comps):
    print()
    print(f"{'company':<11}{'period':<8}{'verified':>9}{'low conf':>9}{'missing':>8}")
    for (c, p), n in checks.items():
        print(f"{c:<11}{p:<8}{n.get('verified', 0):>9}{n.get('low_confidence', 0):>9}{n.get('missing', 0):>8}")
    low = conn.execute("SELECT company, period, metric, segment, note FROM figures"
                       " WHERE status = 'low_confidence' AND method != 'derived' ORDER BY company, period").fetchall()
    for r in low:
        print(f"  low confidence  {r['company']} {r['period']} {r['metric']} {r['segment'] or ''}: "
              f"{(r['note'] or '').split(verify.MARK)[-1]}")
    print()
    print(f"{'company':<11}{'report':<8}{'compared':>9}{'gaps':>6}{'low':>6}{'medium':>7}{'high':>6}{'n.m.':>6}"
          f"{'no current':>11}")
    for (c, t), s in comps.items():
        print(f"{c:<11}{t:<8}{s['comparisons']:>9}{s['gaps']:>6}{s['low']:>6}{s['medium']:>7}{s['high']:>6}"
              f"{s['n.m.']:>6}{s['missing_current']:>11}")
    return 0


def report_estimates(conn, cfg, args):
    try:
        ests, before, after = estimates.run(conn, cfg, args.company, args.quarter)
    except (estimates.ModelError, config.ConfigError) as e:
        print(f"ESTIMATES FAILED: {e}", file=sys.stderr)
        return 1
    missing = [e for e in ests if e["value"] is None]
    sample = " (SAMPLE)" if ests and ests[0]["is_sample"] else ""
    print()
    print(f"estimates{sample}: {len(ests)} read, {len(missing)} without a cached value; "
          f"model hash {before[:12]} unchanged: {before == after}")
    for e in missing:
        print(f"  missing  {e['company']} {e['quarter']} {e['metric']} {e['segment'] or ''} ({e['sheet']}!{e['cell']})")
    return 0


def report_kpis(results):
    """One line per KPI and document: the quarters it yielded, or why it is missing."""
    print()
    print(f"{'company':<11}{'document':<10}{'kpi':<26}page  values by quarter")
    for (c, q, m), figs in results.items():
        if isinstance(figs, str):
            print(f"{c:<11}{q:<10}{m:<26}   -  MISSING: {figs}")
            continue
        vals = ", ".join(f"{f['period']} {f['value']}" + ("~" if f["note"] else "") for f in figs)
        print(f"{c:<11}{q:<10}{m:<26}{figs[0]['source_ref']:>4}  {vals}")
    return 0


def report_run(results):
    """One line per company-quarter with the headline XBRL figures."""
    show = ["revenue", "ebitda", "ebitda_margin", "pat_owners", "basic_eps"]
    print(f"{'company':<11}{'quarter':<8}" + "".join(f"{m:>15}" for m in show) + "  segments  missing")
    failed = 0
    for (c, q), figs in results.items():
        if isinstance(figs, str):
            print(f"{c:<11}{q:<8}  FAILED: {figs}", file=sys.stderr)
            failed += 1
            continue
        top = {f["metric"]: f["value"] for f in figs if f["segment"] is None}
        cells = "".join(f"{'-' if top.get(m) is None else f'{top[m]:,.2f}':>15}" for m in show)
        segs = len({f["segment"] for f in figs if f["segment"]})
        missing = sorted({f["metric"] for f in figs if f["status"] == "missing"})
        print(f"{c:<11}{q:<8}{cells}  {segs:>8}  {', '.join(missing) or '-'}")
    return 1 if failed else 0


def report_ingest(s):
    print(f"registered {s['registered']} documents, {s['already']} already registered")
    for label, reason in s["missing"]:
        print(f"  missing   {label}: {reason}")
    pages = {}
    for label, page in s["scanned_pages"]:
        pages.setdefault(label, []).append(page)
    for label, p in pages.items():
        print(f"  scanned   {label}: pages {p} (manual handling)")
    for label, err in s["failed"]:
        print(f"  FAILED    {label}: {err}", file=sys.stderr)
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
