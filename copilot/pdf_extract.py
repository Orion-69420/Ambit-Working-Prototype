"""Step 6: extract operating KPIs from PDFs with per-company rules (config/pdf_rules/<company>.yaml).

Values are located by word position (PyMuPDF), never by "a number somewhere on the page":

  grid      value at the intersection of a row label and a column header (fact sheets, tables)
  chart     value directly above a quarter label on a chart's x-axis
  labelled  value directly above a caption such as "Like to like"
  text      a sentence pattern with a (?P<value>...) group; describes the document's own quarter

Each document yields values for every quarter it shows (a fact sheet's prior and year-ago columns,
a chart's quarterly series). Which document a comparison uses is decided in Step 8.
"""
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import pymupdf
import yaml

from copilot import config, db

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
QUARTER_LABEL = re.compile(r"^Q([1-4])\s*(?:F|FY)?\s*'?(\d{2})$", re.I)
QUARTER_HEAD = re.compile(r"^Q([1-4])$", re.I)
YEAR_TAIL = re.compile(r"^(?:F|FY)\s*'?(\d{2})$", re.I)
DATE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+(\d{1,2}),?\s+(\d{4})", re.I)
MISSING_MARKS = {"-", "–", "—", "nil", "na", "n.a.", ""}


class RuleError(Exception):
    """The rule could not locate its value; the figure is recorded as missing with this reason."""


# ---------------------------------------------------------------- numbers and periods

def parse_number(text):
    """Parse a printed number. Returns (Decimal or None, approximate flag).

    Handles Indian and western digit grouping, (35.2) as negative, %, ₹, a leading 'c.' or '~'
    (approximate), and '–'/'-'/nil as missing (never zero).
    """
    t = text.strip().replace("−", "-")
    approx = bool(re.match(r"^(c\.|~|approx\.?)\s*", t, re.I))
    t = re.sub(r"^(c\.|~|approx\.?)\s*", "", t, flags=re.I)
    t = t.replace("₹", "").replace("%", "").replace(" ", "").strip()
    if t.lower() in MISSING_MARKS:
        return None, approx
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None, approx
    return (-v if neg else v), approx


def quarter_from_label(q, yy):
    """'Q4', '26' -> 'Q4FY26'"""
    return f"Q{q}FY{yy}"


def quarter_from_date(month, year):
    """Quarter-end date -> quarter id (April-March financial year)."""
    m, y = MONTHS[month[:3].lower()], int(year)
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(m)
    if q is None:
        return None
    fy = y + 1 if m >= 4 else y
    return f"Q{q}FY{fy % 100:02d}"


# ---------------------------------------------------------------- page geometry

@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int
    line: int

    @property
    def xc(self):
        return (self.x0 + self.x1) / 2

    @property
    def yc(self):
        return (self.y0 + self.y1) / 2


def page_words(page):
    return [Word(*w[:5], w[5], w[6]) for w in page.get_text("words")]


def lines(words):
    """Group words into visual lines: [(text, [words])] in reading order."""
    groups = {}
    for w in words:
        groups.setdefault((w.block, w.line), []).append(w)
    out = [(" ".join(w.text for w in ws), ws) for ws in groups.values()]
    return sorted(out, key=lambda l: (round(min(w.y0 for w in l[1])), min(w.x0 for w in l[1])))


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def find_page(pdf, anchors):
    """First page (1-based) whose text contains every anchor (whitespace-insensitive)."""
    for i, page in enumerate(pdf, start=1):
        text = norm(page.get_text())
        if all(norm(a) in text for a in anchors):
            return i, page
    raise RuleError(f"no page contains all of {anchors}")


def numbers(words, pattern=None):
    out = []
    for w in words:
        if pattern and not re.match(pattern, w.text):
            continue
        v, approx = parse_number(w.text)
        if v is not None and re.search(r"\d", w.text):
            out.append((w, v, approx))
    return out


def quarter_labels(words):
    """Quarter axis/column labels, joining split labels like 'Q4' + 'FY26' (side by side or stacked)."""
    out, used = [], set()
    for i, w in enumerate(words):
        m = QUARTER_LABEL.match(w.text)
        if m:
            out.append((quarter_from_label(*m.groups()), w.x0, w.y0, w.x1, w.y1))
            continue
        if QUARTER_HEAD.match(w.text) and i not in used:
            for j, t in enumerate(words):
                if j == i or j in used:
                    continue
                m2 = YEAR_TAIL.match(t.text)
                beside = abs(t.yc - w.yc) < 4 and 0 <= t.x0 - w.x1 < 12
                below = abs(t.xc - w.xc) < 25 and -4 <= t.y0 - w.y1 < 12   # boxes may touch or overlap
                if m2 and (beside or below):
                    used.add(j)
                    out.append((quarter_from_label(QUARTER_HEAD.match(w.text).group(1), m2.group(1)),
                                min(w.x0, t.x0), min(w.y0, t.y0), max(w.x1, t.x1), max(w.y1, t.y1)))
                    break
    return out


# ---------------------------------------------------------------- rule kinds

def rule_grid(page, rule, doc_quarter):
    words = page_words(page)
    ls = lines(words)
    # follow the row path: each label must be found below the previous one
    y_from, row = -1, None
    for label in rule["row"]:
        # a row label starts its line; this skips commentary that merely mentions the metric
        match = next(((t, ws) for t, ws in ls if min(w.y0 for w in ws) > y_from and norm(t).startswith(norm(label))), None)
        if match is None:
            raise RuleError(f"row label {label!r} not found")
        row = match
        y_from = min(w.y0 for w in match[1])
    row_words = _label_words(row[1], rule["row"][-1])
    band = (min(w.y0 for w in row_words) - 2, max(w.y1 for w in row_words) + 2)
    label_right = max(w.x1 for w in row_words)

    heads = _column_heads(words, rule["columns"], band[0])
    if not heads:
        raise RuleError("no column headers found above the row")
    out = {}
    cand = [(w, v, a) for w, v, a in numbers(words, rule.get("value_pattern"))
            if band[0] <= w.yc <= band[1] and w.x0 > label_right]
    for q, hx0, hx1 in heads:
        hc, half = (hx0 + hx1) / 2, max((hx1 - hx0) / 2, 20)
        hits = [(abs(w.xc - hc), w, v, a) for w, v, a in cand if abs(w.xc - hc) <= half + 15]
        if not hits:
            continue
        _, w, v, a = min(hits, key=lambda h: h[0])
        out[q] = dict(value=v, approx=a, printed=w.text, detail=f"{row[0]} | {_head_text(rule['columns'], q)}")
    return out


def _label_words(ws, label):
    """The words of a line that spell the label (a line can also hold the unit and the values)."""
    ws = sorted(ws, key=lambda w: w.x0)
    target = norm(label)
    for i in range(len(ws)):
        for j in range(i, len(ws)):
            joined = norm(" ".join(w.text for w in ws[i:j + 1]))
            if target in joined:
                return ws[i:j + 1]
            if not target.startswith(joined[: len(target)]):
                break
    return ws


def _column_heads(words, kind, row_top):
    """Column headers nearest above the row: [(quarter, x0, x1)]."""
    heads = []
    if kind == "date":
        for t, ws in lines(words):
            for m in DATE.finditer(t):
                q = quarter_from_date(m.group(1), m.group(3))
                # locate the words making up this date to get its x-span
                parts = [w for w in ws if w.text.rstrip(",.").lower().startswith(m.group(1)[:3].lower())
                         or w.text.rstrip(",") in (m.group(2), m.group(3))]
                if q and parts and max(w.y1 for w in parts) < row_top:
                    heads.append((q, min(w.x0 for w in parts), max(w.x1 for w in parts), min(w.y0 for w in parts)))
    elif kind == "quarter":
        heads = [(q, x0, x1, y0) for q, x0, y0, x1, y1 in quarter_labels(words) if y1 < row_top]
    if not heads:
        return []
    nearest = max(h[3] for h in heads)                     # the header row closest above
    return [(q, x0, x1) for q, x0, x1, y0 in heads if nearest - y0 < 15]


def _head_text(kind, q):
    if kind == "quarter":
        return q
    n, fy = int(q[1]), 2000 + int(q[-2:])
    month, day, year = {1: (6, 30, fy - 1), 2: (9, 30, fy - 1), 3: (12, 31, fy - 1), 4: (3, 31, fy)}[n]
    return f"quarter ended {year}-{month:02d}-{day}"


def rule_chart(page, rule, doc_quarter):
    words = page_words(page)
    W = page.rect.width
    x0, x1 = (f * W for f in rule.get("region", [0, 1]))
    inside = [w for w in words if x0 <= w.xc <= x1]
    labels = quarter_labels(inside)
    if not labels:
        raise RuleError("no quarter labels on the chart axis")
    axis_y = max(l[2] for l in labels)
    labels = [l for l in labels if axis_y - l[2] < 15]       # the axis row only
    labels.sort(key=lambda l: l[1])
    spacing = min((b[1] - a[1] for a, b in zip(labels, labels[1:])), default=60)
    vals = [(w, v, a) for w, v, a in numbers(inside, rule.get("value_pattern")) if w.y1 <= axis_y + 1]
    out = {}
    for q, lx0, ly0, lx1, ly1 in labels:
        lc = (lx0 + lx1) / 2
        hits = [(abs(w.xc - lc), w, v, a) for w, v, a in vals if abs(w.xc - lc) < spacing * 0.5]
        if not hits:
            continue
        hits.sort(key=lambda h: h[0])
        if len(hits) > 1 and abs(hits[0][0] - hits[1][0]) < 2:
            raise RuleError(f"two values above {q}: {hits[0][1].text}, {hits[1][1].text}")
        _, w, v, a = hits[0]
        out[q] = dict(value=v, approx=a, printed=w.text, detail=f"{rule.get('series', 'chart')} | {q}")
    return out


def rule_labelled(page, rule, doc_quarter):
    words = page_words(page)
    ls = [(t, ws) for t, ws in lines(words) if norm(rule["label"]) == norm(t) or norm(t).startswith(norm(rule["label"]))]
    if len(ls) < rule.get("occurrence", 1):
        raise RuleError(f"caption {rule['label']!r} not found")
    _, lab = ls[rule.get("occurrence", 1) - 1]
    lx0, lx1, ly0 = min(w.x0 for w in lab), max(w.x1 for w in lab), min(w.y0 for w in lab)
    above = [(ly0 - w.y1, w, v, a) for w, v, a in numbers(words, rule.get("value_pattern"))
             if w.y1 <= ly0 + 2 and ly0 - w.y1 < 40 and w.x1 > lx0 - 5 and w.x0 < lx1 + 5]
    if not above:
        raise RuleError(f"no value above caption {rule['label']!r}")
    _, w, v, a = min(above, key=lambda h: h[0])
    return {doc_quarter: dict(value=v, approx=a, printed=w.text, detail=f"{rule['label']} (above caption)")}


def rule_text(page, rule, doc_quarter):
    text = re.sub(r"\s+", " ", page.get_text())
    m = re.search(rule["pattern"], text, re.I)
    if not m:
        raise RuleError(f"pattern not found: {rule['pattern']}")
    v, approx = parse_number(m.group("value"))
    approx = approx or bool(re.search(r"c\.\s*$", text[:m.start("value")]))
    if v is None:
        raise RuleError(f"not a number: {m.group('value')!r}")
    return {doc_quarter: dict(value=v, approx=approx, printed=m.group("value"), detail=m.group(0)[:120])}


KINDS = {"grid": rule_grid, "chart": rule_chart, "labelled": rule_labelled, "text": rule_text}


# ---------------------------------------------------------------- running rules

def load_rules(company):
    path = config.CONFIG / "pdf_rules" / f"{company}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf8"))


def apply(rule, pdf_path, doc_quarter):
    """Run one rule on one document. Returns (page, {period: result})."""
    with pymupdf.open(pdf_path) as pdf:
        try:
            page_no, page = find_page(pdf, rule["page_anchors"])
        except RuleError:
            blank = sum(1 for p in pdf if len(p.get_text().strip()) < 30)
            if blank > pdf.page_count / 2:
                raise RuleError(f"document is a scanned image ({blank} of {pdf.page_count} pages have no text)")
            raise
        if len(page.get_text().strip()) < 30:
            raise RuleError(f"page {page_no} is a scanned image")
        found = KINDS[rule["kind"]](page, rule, doc_quarter)
    if not found:
        raise RuleError(f"page {page_no}: no values located")
    return page_no, found


def run(conn, cfg, company="all", quarter="all", user=None):
    """Apply every KPI rule to every matching document. Returns {(company, doc_quarter, metric): result}."""
    results = {}
    companies = list(cfg.companies) if company == "all" else [company]
    for c in companies:
        rules = load_rules(c)
        if not rules:
            continue
        for metric, rule in rules["kpis"].items():
            m = cfg.metrics[metric]
            doc_type = m["sources"]["document"]
            docs = conn.execute("SELECT id, quarter, file_path FROM documents WHERE company = ? AND type = ?"
                                " ORDER BY quarter", (c, doc_type)).fetchall()
            for d in docs:
                if quarter != "all" and d["quarter"] not in config.quarters_needed(quarter):
                    continue
                if d["quarter"] in (rule.get("skip") or {}):
                    continue
                try:
                    page, found = apply(rule, config.CONFIG.parent / d["file_path"], d["quarter"])
                    figs = [_figure(m, d, page, period, r) for period, r in sorted(found.items())
                            if period in config.QUARTERS]
                    note = None
                except RuleError as e:
                    figs, note = [_missing(m, d, str(e))], str(e)
                _store(conn, c, d, metric, figs, user)
                results[(c, d["quarter"], metric)] = figs if note is None else note
    conn.commit()
    return results


def _figure(m, d, page, period, r):
    note = "approximate (stated as 'c.')" if r["approx"] else None
    return dict(metric=m["id"], quarter=d["quarter"], period=period, basis=m.get("basis", "consolidated"),
                value=r["value"], unit=m["unit"], original_value=r["printed"], original_unit=None,
                document_id=d["id"], source_ref=str(page), source_detail=r["detail"], status="extracted", note=note)


def _missing(m, d, reason):
    return dict(metric=m["id"], quarter=d["quarter"], period=d["quarter"], basis=m.get("basis", "consolidated"),
                value=None, unit=m["unit"], original_value=None, original_unit=None, document_id=d["id"],
                source_ref=None, source_detail=None, status="missing", note=reason)


def _store(conn, company, d, metric, figs, user):
    old = [r["id"] for r in conn.execute(
        "SELECT id FROM figures WHERE company = ? AND document_id = ? AND metric = ? AND method = 'pdf'",
        (company, d["id"], metric))]
    if old:
        marks = ",".join("?" * len(old))
        if conn.execute(f"SELECT count(*) FROM figures WHERE supersedes IN ({marks})", old).fetchone()[0]:
            raise RuleError(f"{company} {metric}: analyst corrections exist; not re-extracting")
        conn.execute(f"DELETE FROM comparisons WHERE figure_id IN ({marks}) OR comparator_figure_id IN ({marks})", old + old)
        conn.execute(f"DELETE FROM figures WHERE id IN ({marks})", old)
    for f in figs:
        conn.execute(
            "INSERT INTO figures (company, quarter, metric, period, basis, segment, value, unit, original_value,"
            " original_unit, document_id, source_ref, source_detail, method, status, note, created_at)"
            " VALUES (?,?,?,?,?,NULL,?,?,?,?,?,?,?,'pdf',?,?,?)",
            (company, f["quarter"], f["metric"], f["period"], f["basis"], db.to_db(f["value"]), f["unit"],
             f["original_value"], f["original_unit"], f["document_id"], f["source_ref"], f["source_detail"],
             f["status"], f["note"], db.now()))
    db.audit(conn, "kpi_extracted", f"{company}/{d['quarter']}/{metric}",
             {"document_id": d["id"], "values": {f["period"]: str(f["value"]) for f in figs},
              "missing": [f["note"] for f in figs if f["status"] == "missing"]}, user=user)
