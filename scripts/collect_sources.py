"""Step 1: collect Phase 1 source documents from NSE into data/ and update config/sources.yaml.

Usage: python scripts/collect_sources.py [--dry-run]

Documents are picked by rule, anchored on each quarter's consolidated XBRL broadcast date
(the results date). Anything not found is marked `missing` with a reason, never guessed.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "config" / "sources.yaml"
DATA = ROOT / "data"

NSE = "https://www.nseindia.com/api/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
SYMBOLS = {"TITAN": "TITAN","ASIANPAINT": "ASIANPAINT", "MM": "M&M", "INFY": "INFY", "RELIANCE": "RELIANCE"}
QUARTER_END = {"Q4FY25": "31-MAR-2025", "Q1FY26": "30-JUN-2025", "Q3FY26": "31-DEC-2025",
               "Q4FY26": "31-MAR-2026", "Q1FY27": "30-JUN-2026"}

NO_PRESENTATION = {"INFY": "not filed on NSE; operating KPIs are read from the fact sheet "
                           "in the results_release bundle (decided 13 Oct)"}
NOT_TRANSCRIPT =re.compile(r"annual general|\bAGM\b|AI day", re.I)


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Referer": "https://www.nseindia.com/"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def nse_json(path, **params):
    return json.loads(get(NSE + path + "?" + urllib.parse.urlencode(params)))


def d(s, fmt):
    return dt.datetime.strptime(s, fmt).date()


def size_kb(r):
    m = re.match(r"([\d.]+)\s*(KB|MB)", r.get("attFileSize") or "")
    return float(m[1]) * (1024 if m[2] == "MB" else 1) if m else 0


def pick(company):
    """Return {quarter: {type: candidate dict or missing-reason str}}."""
    sym = SYMBOLS[company]
    filings = nse_json("integrated-filing-results", index="equities", symbol=sym,
                       period_ended="all", type="Integrated Filing- Financials")["data"]
    anns = nse_json("corporate-announcements", index="equities", symbol=sym,
                    from_date="01-01-2025", to_date=dt.date.today().strftime("%d-%m-%Y"))
    for a in anns:
        a["_date"] = d(a["an_dt"], "%d-%b-%Y %H:%M:%S")
        a["_text"] = a.get("attchmntText") or ""

    out = {}
    for q, qe in QUARTER_END.items():
        res = {}
        cons = [f for f in filings if f["qe_Date"] == qe and f["consolidated"] == "Consolidated"]
        orig = [f for f in cons if f["type_Sub"] == "Original"]
        if not orig:
            out[q] = {t: "no consolidated XBRL filing on NSE" for t in
                      ("xbrl", "results_release", "presentation", "transcript", "press_release")}
            continue
        x = orig[0]
        rd = d(x["creation_Date"][:11], "%d-%b-%Y")  # results date anchors the other picks
        # A revised filing is the source of record; the original is kept beside it
        latest = max(cons, key=lambda f: d(f["creation_Date"][:11], "%d-%b-%Y"))
        res["xbrl"] = {"url": latest["xbrl"], "date": d(latest["creation_Date"][:11], "%d-%b-%Y"),
                       "ext": "xml", "note": None}
        if latest is not x:
            res["xbrl"].update(original_url=x["xbrl"],
                               note=f"revised filing; original of {rd.isoformat()} kept as xbrl_original.xml")

        def near(a, lo, hi):
            return rd + dt.timedelta(days=lo) <= a["_date"] <= rd + dt.timedelta(days=hi)

        rr = [a for a in anns if near(a, -1, 1) and a["desc"] == "Outcome of Board Meeting"
              and re.search(r"result|financ", a["_text"] + a["attchmntFile"], re.I)]
        if not rr:  # some companies file the results under the outcome title only
            rr = [a for a in anns if near(a, 0, 0) and a["desc"] == "Outcome of Board Meeting"]
        res["results_release"] = max(rr, key=size_kb) if rr else "no results outcome filed within 1 day of XBRL"
        # Some originals are scanned; prefer the company's later machine-readable re-filing
        mr = [a for a in anns if near(a, 0, 30) and re.search(r"machine readable", a["_text"], re.I)]
        if mr:
            res["results_release"] = dict(min(mr, key=lambda a: a["_date"]),
                                          _note="machine-readable re-filing (original was scanned)")

        pr = [a for a in anns if near(a, -1, 3) and a["desc"] == "Investor Presentation"]
        res["presentation"] = max(pr, key=size_kb) if pr else (
            NO_PRESENTATION.get(company, "no investor presentation filed on NSE"))

        # Results press release: a text-based second source for the cross-source check (added after Step 8)
        ps = [a for a in anns if near(a, 0, 1) and a["desc"] == "Press Release"
              and re.search(r"result|financial|performance", a["_text"], re.I)]
        res["press_release"] = max(ps, key=size_kb) if ps else "no results press release filed on NSE"

        tr = [a for a in anns if near(a, 0, 25) and re.search(r"transcript", a["_text"], re.I)
              and not NOT_TRANSCRIPT.search(a["_text"])]
        res["transcript"] = min(tr, key=lambda a: a["_date"]) if tr else "no earnings-call transcript filed on NSE"

        for t, v in res.items():
            if isinstance(v, dict) and "an_dt" in v:
                res[t] = {"url": v["attchmntFile"], "date": v["_date"], "ext": "pdf",
                          "note": v.get("_note")}
        out[q] = res
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reg = yaml.safe_load(SOURCES.read_text(encoding="utf8"))
    picks = {}
    for co in SYMBOLS:
        picks[co] = pick(co)
        time.sleep(1)

    for doc in reg["documents"]:
        p = picks[doc["company"]][doc["quarter"]][doc["type"]]
        old_url = doc.get("url")
        if isinstance(p, str):
            doc.update(status="missing", reason=p, path=None, url=None, sha256=None)
            continue
        rel = pathlib.Path(doc["company"], doc["quarter"], f"{doc['type']}.{p['ext']}")
        doc.update(url=p["url"], publication_date=p["date"].isoformat(), path=f"data/{rel.as_posix()}")
        doc.pop("note", None)
        if p["note"]:
            doc["note"] = p["note"]
        if args.dry_run:
            print(doc["company"], doc["quarter"], doc["type"], p["url"])
            continue
        dest = DATA / rel
        if dest.exists() and old_url and old_url != p["url"]:
            dest.unlink()  # pick changed since last run; refetch
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_bytes(get(p["url"], accept="*/*"))
            except Exception as e:  # keep going; record the failure
                doc.update(status="pending", reason=f"download failed: {e}", sha256=None)
                print("FAIL", rel, e, file=sys.stderr)
                continue
            time.sleep(0.5)
        if p.get("original_url"):
            orig = dest.with_name(f"{doc['type']}_original.{p['ext']}")
            if not orig.exists():
                orig.write_bytes(get(p["original_url"], accept="*/*"))
        doc.update(status="collected", sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        doc.pop("reason", None)
        print("ok  ", rel)

    if not args.dry_run:
        header = "".join(l + "\n" for l in SOURCES.read_text(encoding="utf8").splitlines()
                         if l.startswith("#"))
        SOURCES.write_text(header + yaml.safe_dump(reg, sort_keys=False, allow_unicode=True),
                           encoding="utf8")
    counts = {}
    for doc in reg["documents"]:
        counts[doc.get("status")] = counts.get(doc.get("status"), 0) + 1
    print(counts)


if __name__ == "__main__":
    main()
