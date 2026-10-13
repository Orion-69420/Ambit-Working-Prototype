"""Load and validate the YAML configuration (Step 3).

Every problem found is collected and reported together; any problem stops the run.
"""
import pathlib
import re
from dataclasses import dataclass

import yaml

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "config"

QUARTERS = ("Q4FY25", "Q1FY26", "Q3FY26", "Q4FY26", "Q1FY27")
TARGET_QUARTERS = ("Q4FY26", "Q1FY27")
QUARTER_DATES = {   # (start, end) of each three-month quarter, April-March financial year
    "Q4FY25": ("2025-01-01", "2025-03-31"),
    "Q1FY26": ("2025-04-01", "2025-06-30"),
    "Q3FY26": ("2025-10-01", "2025-12-31"),
    "Q4FY26": ("2026-01-01", "2026-03-31"),
    "Q1FY27": ("2026-04-01", "2026-06-30"),
}
COMPARATORS = {     # target quarter -> comparator quarters (procedure Section 2)
    "Q4FY26": {"prior": "Q3FY26", "year_ago": "Q4FY25"},
    "Q1FY27": {"prior": "Q4FY26", "year_ago": "Q1FY26"},
}


def quarters_needed(quarter):
    """A target quarter needs its own figures plus its comparators'; 'all' means every quarter."""
    if quarter == "all":
        return list(QUARTERS)
    return [quarter, *COMPARATORS.get(quarter, {}).values()]

METRIC_TYPES = {"reported", "derived", "input"}
PERIODS = {"quarter", "point_in_time", "annual_only"}
CHANGE_AS = {"pct", "bps", "pp"}
BASES = {"consolidated", "standalone"}
DOC_TYPES = {"xbrl", "results_release", "presentation", "transcript", "press_release"}
FORMULA = re.compile(r"^[a-z0-9_+\-*/(). ]+$")
NAME = re.compile(r"[a-z_][a-z0-9_]*")


class ConfigError(Exception):
    def __init__(self, problems):
        self.problems = problems
        super().__init__("invalid configuration:\n  - " + "\n  - ".join(problems))


@dataclass
class Config:
    companies: dict      # id -> company dict
    units: dict          # id -> unit dict
    metrics: dict        # id -> metric dict
    thresholds: dict     # group -> band dict
    commentary: dict

    def metrics_for(self, company, include_inputs=False):
        return [m for m in self.metrics.values()
                if (include_inputs or m["type"] != "input")
                and (m["applies_to"] == "all" or company in m["applies_to"])]


def load(name, base=CONFIG):
    path = pathlib.Path(base) / name
    if not path.exists():
        raise ConfigError([f"missing config file: {path}"])
    try:
        return yaml.safe_load(path.read_text(encoding="utf8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError([f"{name}: not valid YAML: {e}"])


def companies():
    """Company ids only; usable before the full config is valid."""
    rows = load("companies.yaml").get("companies", [])
    return {c["id"]: c for c in rows}


def load_all(base=CONFIG):
    problems = []
    raw_companies = load("companies.yaml", base).get("companies", [])
    raw_metrics = load("metrics.yaml", base)
    raw_thresholds = load("thresholds.yaml", base).get("groups", {})
    commentary = load("commentary_rules.yaml", base)

    comps = _unique(raw_companies, "companies.yaml company", problems)
    _check_companies(comps, problems)
    units = raw_metrics.get("units", {})
    metrics = _unique(raw_metrics.get("metrics", []), "metrics.yaml metric", problems)
    _check_thresholds(raw_thresholds, problems)
    for m in metrics.values():
        _check_metric(m, metrics, units, raw_thresholds, comps, problems)
    _check_cycles(metrics, problems)
    _check_commentary(commentary, comps, problems)

    if problems:
        raise ConfigError(problems)
    return Config(comps, units, metrics, raw_thresholds, commentary)


def _unique(rows, what, problems):
    out = {}
    for r in rows:
        rid = r.get("id")
        if not rid:
            problems.append(f"{what} without an id: {r}")
        elif rid in out:
            problems.append(f"duplicate {what} id: {rid}")
        else:
            out[rid] = r
    return out


def _check_companies(comps, problems):
    for cid, c in comps.items():
        for field in ("name", "nse", "bse", "financial_year", "basis"):
            if not c.get(field):
                problems.append(f"company {cid}: missing {field}")
        if c.get("basis") and c["basis"] not in BASES:
            problems.append(f"company {cid}: unknown basis {c['basis']!r}")
        notes = c.get("report_notes", [])
        if not isinstance(notes, list) or not all(isinstance(n, str) and n.strip() for n in notes):
            problems.append(f"company {cid}: report_notes must be a list of non-empty strings")
        segs = c.get("segments")
        if segs is None:
            problems.append(f"company {cid}: missing segments (use {{}} for a single-segment company)")
            continue
        seen = {}
        for canon, labels in segs.items():
            for label in labels or []:
                if label in seen:
                    problems.append(f"company {cid}: segment label {label!r} maps to both {seen[label]!r} and {canon!r}")
                seen[label] = canon
        if segs and c.get("segment_sum_to") not in ("revenue", "total_income", "segment_total"):
            problems.append(f"company {cid}: segment_sum_to must be revenue, total_income or segment_total")


def _check_thresholds(groups, problems):
    if not groups:
        problems.append("thresholds.yaml: no groups")
    for g, b in groups.items():
        if b.get("unit") not in CHANGE_AS:
            problems.append(f"threshold group {g}: unknown unit {b.get('unit')!r}")
        for label, bands in (("", b), (" period", b.get("period") or {})):
            lo, hi = bands.get("low_below"), bands.get("high_above")
            if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)) or not 0 < lo <= hi:
                problems.append(f"threshold group {g}{label}: need 0 < low_below <= high_above, got {lo}, {hi}")


def _check_metric(m, metrics, units, thresholds, comps, problems):
    mid = m["id"]
    p = lambda msg: problems.append(f"metric {mid}: {msg}")
    for field in ("name", "definition", "type", "unit", "period", "applies_to"):
        if not m.get(field):
            p(f"missing {field}")
    if m.get("type") not in METRIC_TYPES:
        p(f"unknown type {m.get('type')!r}")
    if m.get("unit") and m["unit"] not in units:
        p(f"unknown unit {m['unit']!r}")
    if m.get("period") and m["period"] not in PERIODS:
        p(f"unknown period {m['period']!r}")
    if m.get("basis", "consolidated") not in BASES:
        p(f"unknown basis {m['basis']!r}")

    applies = m.get("applies_to")
    if applies != "all":
        if not isinstance(applies, list):
            p("applies_to must be 'all' or a list of company ids")
        else:
            for c in applies:
                if c not in comps:
                    p(f"applies_to unknown company {c!r}")
                elif m.get("per_segment") and not comps[c].get("segments"):
                    p(f"per-segment metric applies to single-segment company {c}")

    if m.get("type") != "input":   # shown in the report: needs a comparison rule
        if m.get("change_as") not in CHANGE_AS:
            p(f"unknown change_as {m.get('change_as')!r}")
        group = thresholds.get(m.get("threshold_group"))
        if group is None:
            p(f"unknown threshold_group {m.get('threshold_group')!r}")
        elif group.get("unit") != m.get("change_as"):
            p(f"threshold_group {m['threshold_group']} is in {group.get('unit')}, metric changes in {m.get('change_as')}")

    sources = m.get("sources")
    if sources is None:
        p("missing sources")
        sources = {}
    if m.get("type") == "derived":
        inputs, formula = m.get("inputs") or [], m.get("formula") or ""
        if not formula or not FORMULA.match(formula):
            p(f"formula missing or has characters other than names, numbers and + - * / ( ): {formula!r}")
        used = set(NAME.findall(formula))
        for name in inputs:
            if name not in metrics:
                p(f"input {name!r} is not a defined metric")
        if used - set(inputs):
            p(f"formula uses names not listed in inputs: {sorted(used - set(inputs))}")
        if set(inputs) - used:
            p(f"inputs not used in formula: {sorted(set(inputs) - used)}")
    elif m.get("period") != "annual_only" and not (sources.get("xbrl") or sources.get("pdf_labels")):
        p("needs an XBRL element or PDF labels")
    if sources.get("document") and sources["document"] not in DOC_TYPES:
        p(f"unknown source document {sources['document']!r}")
    for pat in sources.get("text_patterns", []):
        try:
            if "value" not in re.compile(pat).groupindex:
                p(f"text pattern lacks a (?P<value>...) group: {pat!r}")
        except re.error as e:
            p(f"bad text pattern {pat!r}: {e}")
    if m.get("period") == "annual_only" and not m.get("gap_reason"):
        p("annual_only metric needs a gap_reason")


def _check_cycles(metrics, problems):
    def visit(mid, stack):
        if mid in stack:
            problems.append(f"metric {mid}: circular inputs {' -> '.join(stack + [mid])}")
            return
        for i in metrics.get(mid, {}).get("inputs") or []:
            visit(i, stack + [mid])
    for mid in metrics:
        visit(mid, [])


def _check_commentary(rules, comps, problems):
    for key in ("guidance", "explanation", "flags", "negations", "topics"):
        if key not in rules:
            problems.append(f"commentary_rules.yaml: missing {key}")
    pats = []
    for key in ("guidance", "explanation"):
        pats += (rules.get(key) or {}).get("phrases", [])
    for v in (rules.get("flags") or {}).values():
        pats += v
    for group in (rules.get("topics") or {}).values():
        for v in group.values():
            pats += v
    for pat in pats:
        try:
            re.compile(pat)
        except re.error as e:
            problems.append(f"commentary_rules.yaml: bad pattern {pat!r}: {e}")
    for c in (rules.get("topics") or {}):
        if c != "common" and c not in comps:
            problems.append(f"commentary_rules.yaml: topics for unknown company {c!r}")
