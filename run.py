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

from copilot import config, db, ingest

# Company/quarter subcommands and the procedure step that builds them
STEPS = {"ingest": "Step 4", "run": "Steps 5-9", "export": "Step 10"}
PENDING = {"run", "export"}


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
