"""Step 9: guidance statements, explanations and governance/accounting flags from transcripts.

Rules are keyword-based (config/commentary_rules.yaml); they find candidates and the analyst
judges meaning. Every item is stored as an exact quote with its page and speaker.

  guidance     management sentence with a forward-looking phrase and a tracked topic
  explanation  management sentence linking a tracked topic to a cause ("due to", "driven by")
  flag         any non-moderator sentence matching a flag phrase, unless negated just before it
               ("no qualification"); always "for analyst review"

guidance_table() places each topic's current guidance beside the prior quarter's. A topic with
prior guidance but none this quarter is "not repeated" (never "withdrawn").
"""
import re
from dataclasses import dataclass, field

from copilot import config, db

STOP_NAMES = {"date", "sub", "subject", "note", "disclaimer", "encl", "encl.", "ref", "tel", "fax", "scrip code",
              "symbol", "management", "isin", "cc", "fcs", "security code", "regd. office", "scrip symbol",
              "sensitivity", "corporate participants", "analysts", "journalists", "participants", "transcript"}
MODERATOR = re.compile(r"^(moderator|operator)$", re.I)
TITLE_WORDS = re.compile(r"speakers|participants|officer|director|president|\bhead\b|chairman|limited", re.I)
ALL_CAPS = re.compile(r"^[A-Z\s&.]+$")       # headings such as "TITAN MANAGEMENT SPEAKERS"


def not_a_name(name):
    return bool(TITLE_WORDS.search(name) or ALL_CAPS.match(name))
HONORIFIC = re.compile(r"^(mr|ms|mrs|dr|sh|smt|shri)\.?\s+", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])[\"”’)]?\s+(?=[A-Z\"“‘(₹0-9])")


def norm_name(name):
    n = HONORIFIC.sub("", name.strip())
    return frozenset(t for t in re.sub(r"[.,]", " ", n).lower().split() if t)


@dataclass
class Turn:
    speaker: str
    role: str                  # management / analyst / moderator
    parts: list = field(default_factory=list)   # [(page, text)]


@dataclass
class Sentence:
    text: str
    page: int
    speaker: str
    role: str


# ---------------------------------------------------------------- parsing

def _rules(cfg, company):
    t = cfg.commentary.get("transcripts", {})
    base, own = t.get("default", {}), t.get(company, {})
    return dict(speakers=[s if isinstance(s, dict) else {"pattern": s} for s in own.get("speakers", [])],
                management=[norm_name(n) for n in own.get("management", [])],
                ignore=[re.compile(p, re.I) for p in base.get("ignore_lines", []) + own.get("ignore_lines", [])])


def _role(name, rules, forced=None):
    if forced:
        return forced
    if MODERATOR.match(name.strip()):
        return "moderator"
    key = norm_name(name)
    if any(key and (key <= m or m <= key) for m in rules["management"]):
        return "management"
    return "analyst"


def turns(pages, cfg, company):
    """pages: [(page, text)] -> [Turn]. Text before the first speaker (cover letter, lists) is dropped."""
    rules = _rules(cfg, company)
    lines = [(p, l) for p, text in pages for l in text.splitlines()]
    lines = [(p, l) for p, l in lines if l.strip() and not any(r.search(l) for r in rules["ignore"])]
    whole = "\n".join(l for _, l in lines)
    intro = {norm_name(m.group(1)) for m in re.finditer(
        r"question[^.\n]{0,40}?from(?: the line of)?\s+((?:Mr\.|Ms\.)?\s*[A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,3})", whole)}
    counts = {}
    for spec in rules["speakers"]:
        rx = re.compile(spec["pattern"])
        for _, l in lines:
            m = rx.match(l)
            if m:
                counts[norm_name(m.group("name"))] = counts.get(norm_name(m.group("name")), 0) + 1

    out, cur = [], None
    for page, line in lines:
        hit = None
        for spec in rules["speakers"]:
            m = re.match(spec["pattern"], line)
            if not m:
                continue
            name = m.group("name").strip()
            key = norm_name(name)
            if name.lower().rstrip(":") in STOP_NAMES or not key or (
                    not_a_name(name) and not MODERATOR.match(name) and not spec.get("role")):
                continue
            if spec.get("known_only") and not (MODERATOR.match(name) or key in intro or counts.get(key, 0) >= 2
                                               or _role(name, rules) == "management"):
                continue
            hit = (name, _role(name, rules, spec.get("role")), (m.groupdict().get("rest") or "").strip())
            break
        if hit:
            cur = Turn(hit[0], hit[1])
            out.append(cur)
            if hit[2]:
                cur.parts.append((page, hit[2]))
        elif cur is not None:
            cur.parts.append((page, line.strip()))
    return out


def sentences(turn):
    """Split a turn into sentences, each with the page on which it starts."""
    text, starts = "", []
    for page, part in turn.parts:
        if text:
            text += " "
        starts.append((len(text), page))
        text += part
    text = re.sub(r"(\w)- (\w)", r"\1-\2", text)          # re-join words hyphenated across lines
    out, pos = [], 0
    for piece in SENTENCE_END.split(text):
        idx = text.find(piece, pos)
        pos = idx + len(piece)
        page = max((p for start, p in starts if start <= idx), default=starts[0][1] if starts else None)
        s = re.sub(r"\s+", " ", piece).strip()
        if len(s) > 15:
            out.append(Sentence(s, page, turn.speaker, turn.role))
    return out


# ---------------------------------------------------------------- rules

def _compile(cfg, company):
    c = cfg.commentary
    topics = {**c["topics"].get(company, {}), **{k: v for k, v in c["topics"]["common"].items()
                                                  if k not in c["topics"].get(company, {})}}
    return dict(
        guidance=[re.compile(p, re.I) for p in c["guidance"]["phrases"]],
        explanation=[re.compile(p, re.I) for p in c["explanation"]["phrases"]],
        exclude=[re.compile(p, re.I) for p in c.get("exclude", [])],
        flags={k: [re.compile(p, re.I) for p in v] for k, v in c["flags"].items()},
        negations=[re.compile(p, re.I) for p in c["negations"]],
        topics={k: [re.compile(p, re.I) for p in v] for k, v in topics.items()})


def _first(patterns, text):
    for p in patterns:
        m = p.search(text)
        if m:
            return m
    return None


def classify(s, rx):
    """Return [(type, topic, rule)] for one sentence."""
    out = []
    if s.role == "moderator" or any(p.search(s.text) for p in rx["exclude"]):
        return out
    topic = next((t for t, pats in rx["topics"].items() if _first(pats, s.text)), None)
    if s.role == "management" and topic:
        g = None if s.text.rstrip().endswith("?") else _first(rx["guidance"], s.text)   # questions are not guidance
        if g:
            out.append(("guidance", topic, g.group(0)))
        e = _first(rx["explanation"], s.text)
        if e:
            out.append(("explanation", topic, e.group(0)))
    for cat, pats in rx["flags"].items():
        m = _first(pats, s.text)
        if m and not any(n.search(s.text[max(0, m.start() - 40):m.start()]) for n in rx["negations"]):
            out.append(("flag", cat, m.group(0)))
    return out


# ---------------------------------------------------------------- running and storing

def extract(conn, cfg, company, quarter):
    """Statements for one company-quarter transcript, or None if there is no transcript."""
    doc = conn.execute("SELECT id FROM documents WHERE company = ? AND quarter = ? AND type = 'transcript'"
                       " ORDER BY id DESC LIMIT 1", (company, quarter)).fetchone()
    if doc is None:
        return None, None
    pages = conn.execute("SELECT page, text FROM pages WHERE document_id = ? ORDER BY page", (doc["id"],)).fetchall()
    rx = _compile(cfg, company)
    out, ts = [], turns(pages, cfg, company)
    for t in ts:
        for s in sentences(t):
            for typ, topic, rule in classify(s, rx):
                out.append(dict(type=typ, topic=topic, quote=s.text, page=s.page, speaker=s.speaker, rule=rule))
    return doc["id"], dict(statements=out, turns=len(ts),
                           speakers={(t.speaker, t.role) for t in ts})


def run(conn, cfg, company="all", quarter="all", user=None):
    companies = list(cfg.companies) if company == "all" else [company]
    quarters = [q for q in config.quarters_needed(quarter) if q in ("Q3FY26", "Q4FY26", "Q1FY27")]
    results = {}
    for c in companies:
        for q in quarters:
            doc_id, res = extract(conn, cfg, c, q)
            conn.execute("DELETE FROM statements WHERE company = ? AND quarter = ?", (c, q))
            if doc_id is None:
                results[(c, q)] = "no transcript"
                continue
            for s in res["statements"]:
                conn.execute("INSERT INTO statements (company, quarter, type, topic, quote, document_id, page,"
                             " speaker, rule_matched) VALUES (?,?,?,?,?,?,?,?,?)",
                             (c, q, s["type"], s["topic"], s["quote"], doc_id, s["page"], s["speaker"], s["rule"]))
            counts = {t: sum(s["type"] == t for s in res["statements"]) for t in ("guidance", "explanation", "flag")}
            db.audit(conn, "statements_extracted", f"{c}/{q}", counts | {"turns": res["turns"]}, user=user)
            for s in res["statements"]:
                if s["type"] == "flag":
                    db.audit(conn, "flag_raised", f"{c}/{q}", {"category": s["topic"], "page": s["page"],
                                                               "speaker": s["speaker"]}, user=user)
            results[(c, q)] = res
    conn.commit()
    return results


def guidance_table(conn, company, quarter):
    """[(topic, status, current statements, prior statements)] for the report quarter."""
    prior_q = config.COMPARATORS[quarter]["prior"]
    rows = conn.execute("SELECT * FROM statements WHERE company = ? AND quarter IN (?, ?) AND type = 'guidance'"
                        " ORDER BY page, id", (company, quarter, prior_q)).fetchall()
    cur = {}
    prior = {}
    for r in rows:
        (cur if r["quarter"] == quarter else prior).setdefault(r["topic"], []).append(r)
    has_prior = conn.execute("SELECT 1 FROM documents WHERE company = ? AND quarter = ? AND type = 'transcript'",
                             (company, prior_q)).fetchone() is not None
    out = []
    for topic in sorted(set(cur) | set(prior)):
        if topic in cur and topic in prior:
            status = "repeated / updated"
        elif topic in cur:
            status = "new" if has_prior else "no prior transcript"
        else:
            status = "not repeated"
        out.append((topic, status, cur.get(topic, []), prior.get(topic, [])))
    return out
