"""Step 5: extract core financials and segment figures from XBRL filings.

Each SEBI integrated filing covers only its own quarter, so every quarter's figures come from
that quarter's own filing. A fact is used only if its context has the exact three-month period
(or the quarter-end instant for balance-sheet items) and no dimensions, except segment facts,
which are matched to a segment by the label the company gives that segment in the same filing.
"""
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from lxml import etree

from copilot import config, db, derive

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
SEGMENT_LABEL = "DescriptionOfReportableSegment"
BASIS = "NatureOfReportStandaloneConsolidated"


class ExtractError(Exception):
    """A problem that must stop extraction for a filing, e.g. wrong basis or unknown segment."""


@dataclass(frozen=True)
class Context:
    id: str
    start: str | None
    end: str | None
    instant: str | None
    dims: tuple          # ((axis, member), ...) with namespace prefixes removed


@dataclass(frozen=True)
class Fact:
    name: str
    context: Context
    unit: str | None
    text: str | None     # None when the fact is nil


def local(qname):
    """'in-capmkt:ReportableSegmentsAxis' -> 'ReportableSegmentsAxis' (prefixes vary by filer)."""
    return qname.rsplit(":", 1)[-1] if qname else qname


def parse(path):
    root = etree.parse(str(path)).getroot()
    contexts = {}
    for c in root.iter(XBRLI + "context"):
        p = c.find(XBRLI + "period")
        dims = tuple(sorted(
            (local(m.get("dimension")), local((m.text or "".join(m.itertext())).strip()))
            for m in c.iter(XBRLDI + "explicitMember", XBRLDI + "typedMember")))
        contexts[c.get("id")] = Context(c.get("id"), p.findtext(XBRLI + "startDate"),
                                        p.findtext(XBRLI + "endDate"), p.findtext(XBRLI + "instant"), dims)
    facts = []
    for el in root:
        if not isinstance(el.tag, str) or el.get("contextRef") not in contexts:
            continue
        text = None if el.get(XSI_NIL) == "true" else (el.text or "").strip()
        facts.append(Fact(etree.QName(el).localname, contexts[el.get("contextRef")], el.get("unitRef"), text))
    return facts


def in_period(ctx, quarter, period_type):
    start, end = config.QUARTER_DATES[quarter]
    if period_type == "point_in_time":
        return ctx.instant == end
    return ctx.start == start and ctx.end == end


def figure(metric, unit, **kw):
    return dict(metric=metric["id"], unit=metric["unit"], basis=metric.get("basis", "consolidated"),
                segment=None, value=None, original_value=None, original_unit=None, source_ref=None,
                source_detail=None, method="xbrl", derivation=None, status="extracted", note=None) | kw


def to_value(text, metric, units):
    scale = Decimal(units[metric["unit"]].get("scale_from_xbrl", 1))
    try:
        return Decimal(text) / scale
    except (InvalidOperation, TypeError):
        return None


def extract(cfg, company, quarter, path):
    """Return figure dicts for one company-quarter filing. Raises ExtractError on fatal problems."""
    facts = parse(path)
    comp = cfg.companies[company]

    basis = {f.text.lower() for f in facts if f.name == BASIS and f.text}
    if basis != {comp["basis"]}:
        raise ExtractError(f"{company} {quarter}: filing basis {basis or 'not stated'}, configured {comp['basis']}")

    out = []
    metrics = cfg.metrics_for(company, include_inputs=True)
    for m in metrics:
        elements = m["sources"].get("xbrl")
        if not elements or m["type"] == "derived" or m["period"] == "annual_only":
            continue
        if m.get("per_segment"):
            out += _segment_figures(m, facts, comp, quarter, cfg.units)
        else:
            out.append(_company_figure(m, facts, quarter, cfg.units))

    out += _derived(cfg, company, metrics, out)
    return out


def _company_figure(m, facts, quarter, units):
    elements = m["sources"]["xbrl"]
    found = [f for f in facts if f.name in elements and not f.context.dims
             and in_period(f.context, quarter, m["period"])]
    detail = " | ".join(elements)
    if not found:
        return figure(m, None, status="missing", source_detail=detail,
                      note=f"no {m['period']} fact for {quarter} in the filing")
    values = {f.text for f in found}
    if len(values) > 1:
        return figure(m, None, status="missing", source_detail=detail,
                      note=f"conflicting facts: {sorted(map(str, values))}")
    f = found[0]
    if f.text is None:
        return figure(m, None, status="missing", source_detail=f.name, source_ref=f.context.id,
                      note="fact is nil in the filing")
    value = to_value(f.text, m, units)
    return figure(m, None, value=value, original_value=f.text, original_unit=f.unit,
                  source_ref=f.context.id, source_detail=f.name,
                  status="extracted" if value is not None else "missing",
                  note=None if value is not None else f"not a number: {f.text!r}")


def _segment_figures(m, facts, comp, quarter, units):
    axis = m["sources"]["xbrl_axis"]
    aliases = {label: canon for canon, labels in comp["segments"].items() for label in labels}
    # The company labels each segment position in this filing
    labels = {}
    for f in facts:
        if f.name == SEGMENT_LABEL and f.text:
            for ax, member in f.context.dims:
                if ax == axis:
                    labels[member] = f.text
    unknown = sorted(set(labels.values()) - set(aliases))
    if unknown:
        raise ExtractError(f"{comp['id']} {quarter}: unknown segment labels {unknown}; add them to companies.yaml")

    out = []
    for f in facts:
        if f.name not in m["sources"]["xbrl"] or len(f.context.dims) != 1:
            continue
        ax, member = f.context.dims[0]
        if ax != axis or not in_period(f.context, quarter, m["period"]):
            continue
        if member not in labels:
            raise ExtractError(f"{comp['id']} {quarter}: {f.name} for {member} has no segment label")
        value = to_value(f.text, m, units) if f.text is not None else None
        out.append(figure(m, None, segment=aliases[labels[member]], value=value, original_value=f.text,
                          original_unit=f.unit, source_ref=f.context.id,
                          source_detail=f"{f.name} [{labels[member]}]",
                          status="extracted" if value is not None else "missing",
                          note=None if value is not None else "fact is nil or not a number"))
    if not out:
        out.append(figure(m, None, status="missing", source_detail=" | ".join(m["sources"]["xbrl"]),
                          note=f"no segment facts for {quarter} in the filing"))
    return out


def _derived(cfg, company, metrics, extracted):
    by_id = {m["id"]: m for m in metrics}
    values = {f["metric"]: f for f in extracted if f["segment"] is None}
    out = []
    for mid in derive.order(by_id):
        m = by_id[mid]
        inputs = {i: values.get(i) for i in m["inputs"]}
        absent = [i for i, f in inputs.items() if f is None or f["value"] is None]
        if absent:
            f = figure(m, None, method="derived", status="missing",
                       note=f"input missing: {', '.join(absent)}",
                       derivation=json.dumps({"formula": m["formula"], "inputs": list(inputs)}))
        else:
            try:
                v = derive.evaluate(m["formula"], {i: f["value"] for i, f in inputs.items()})
                f = figure(m, None, method="derived", value=v,
                           derivation=json.dumps({"formula": m["formula"],
                                                  "inputs": {i: str(f["value"]) for i, f in inputs.items()}}))
            except derive.DeriveError as e:
                f = figure(m, None, method="derived", status="missing", note=str(e),
                           derivation=json.dumps({"formula": m["formula"], "inputs": list(inputs)}))
        values[mid] = f
        out.append(f)
    return out


def store(conn, company, quarter, document_id, figures, user=None):
    """Replace this filing's XBRL and derived figures. Refuses if an analyst correction exists."""
    old = [r["id"] for r in conn.execute(
        "SELECT id FROM figures WHERE company = ? AND period = ? AND method IN ('xbrl', 'derived')",
        (company, quarter))]
    if old:
        marks = ",".join("?" * len(old))
        if conn.execute(f"SELECT count(*) FROM figures WHERE supersedes IN ({marks})", old).fetchone()[0]:
            raise ExtractError(f"{company} {quarter}: analyst corrections exist; not re-extracting")
        conn.execute(f"DELETE FROM comparisons WHERE figure_id IN ({marks}) OR comparator_figure_id IN ({marks})", old + old)
        conn.execute(f"DELETE FROM figures WHERE id IN ({marks})", old)
    ids = {}
    for f in figures:
        doc = None if f["method"] == "derived" else document_id
        derivation = f["derivation"]
        if f["method"] == "derived" and f["value"] is not None:
            # record which stored figures fed the formula
            d = json.loads(derivation)
            d["input_figures"] = {i: ids.get(i) for i in d["inputs"]}
            derivation = json.dumps(d)
        cur = conn.execute(
            "INSERT INTO figures (company, quarter, metric, period, basis, segment, value, unit,"
            " original_value, original_unit, document_id, source_ref, source_detail, method,"
            " derivation, status, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (company, quarter, f["metric"], quarter, f["basis"], f["segment"], db.to_db(f["value"]),
             f["unit"], f["original_value"], f["original_unit"], doc, f["source_ref"],
             f["source_detail"], f["method"], derivation, f["status"], f["note"], db.now()))
        if f["segment"] is None:
            ids[f["metric"]] = cur.lastrowid
    db.audit(conn, "figures_extracted", f"{company}/{quarter}",
             {"document_id": document_id, "count": len(figures), "replaced": len(old),
              "missing": [f["metric"] for f in figures if f["status"] == "missing"]}, user=user)
    conn.commit()


def run(conn, cfg, company="all", quarter="all", user=None):
    """Extract every needed filing. Returns {(company, quarter): figures or error string}."""
    results = {}
    companies = list(cfg.companies) if company == "all" else [company]
    for c in companies:
        for q in config.quarters_needed(quarter):
            row = conn.execute("SELECT id, file_path FROM documents WHERE company = ? AND quarter = ?"
                               " AND type = 'xbrl' ORDER BY id DESC LIMIT 1", (c, q)).fetchone()
            if row is None:
                results[(c, q)] = "no XBRL document ingested"
                continue
            try:
                figs = extract(cfg, c, q, config.CONFIG.parent / row["file_path"])
                store(conn, c, q, row["id"], figs, user=user)
                results[(c, q)] = figs
            except ExtractError as e:
                db.audit(conn, "extraction_failed", f"{c}/{q}", {"error": str(e)}, user=user)
                conn.commit()
                results[(c, q)] = str(e)
    return results
