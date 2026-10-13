"""Step 10: write a Change Report to Excel and PDF from one snapshot.

An approved report is exported from its saved snapshot; anything else is built fresh and
labelled DRAFT on every sheet and page. Both files are written from the same display rows
(sections()), so they always match. Exporting never approves.
"""
import datetime as dt
import json
import pathlib

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from copilot import config, db, report

OUT = pathlib.Path(__file__).resolve().parent.parent / "output"
SEV = {"high": "High", "medium": "Medium", "low": "Low", None: ""}
STATUS = {"verified": "Verified", "manually_verified": "Manually verified", "low_confidence": "Low confidence",
          "missing": "Missing", "extracted": "Not checked"}


def sections(snap, currency="₹"):
    """Display rows for every section, shared by both exports."""
    c = snap["content"]
    sample = " (SAMPLE)" if c["sample_estimates"] else ""
    comps = c["comparators"]
    head = [("Company", f"{c['company_name']} ({c['company']})"), ("Quarter", c["quarter"]),
            ("Period", f"{c['period'][0]} to {c['period'][1]}"), ("Basis", c["basis"].capitalize()),
            ("Status", snap["status"].upper()),
            ("Approved by", f"{snap.get('approved_by') or '—'}" + (f" on {snap['approved_at']}" if snap.get("approved_at") else "")),
            ("Documents used", str(len(c["sources"]))), ("Exported", dt.datetime.now().isoformat(timespec="seconds"))]
    metric_head = ["Metric", "Reported", f"Prior quarter ({comps['prior']}) / change",
                   f"Year-ago ({comps['year_ago']}) / change", f"Estimate{sample} / variance", "Severity (vs estimate)",
                   "Management explanation", "Source", "Verification"]
    metrics = []
    for r in c["rows"]:
        cur = r["current"] or {}
        name = r["name"] + (f" – {r['segment']}" if r["segment"] else "")
        cells = [name, report.fmt_value(cur.get("value"), r["unit"], currency)]
        for k in ("prior", "year_ago", "estimate"):
            cmp_ = r["comparisons"].get(k)
            if cmp_ is None:
                cells.append("—")
            elif cmp_.get("gap"):
                cells.append(f"gap: {cmp_['gap']}")
            else:
                sev = f" [{SEV[cmp_['severity']]}]" if k != "estimate" and cmp_["severity"] else ""
                cells.append(f"{report.fmt_value(cmp_['value'], r['unit'], currency)} / {report.fmt_change(cmp_)}{sev}")
        est = r["comparisons"].get("estimate") or {}
        cells.append(SEV[est.get("severity")] if not est.get("gap") else "")
        e = r["explanation"]
        cells.append(f"“{e['quote']}” ({e['speaker']}, p. {e['page']})" if e else "")
        cells.append((cur.get("source") or {}).get("text", "—"))
        cells.append(STATUS.get(cur.get("status"), cur.get("status") or "Missing"))
        metrics.append(cells)
    guidance = []
    for g in c["guidance"]:
        now = "\n".join(f"“{s['quote']}” ({s['speaker']}, p. {s['page']})" for s in g["current"]) or "—"
        before = "\n".join(f"“{s['quote']}” ({s['speaker']}, p. {s['page']})" for s in g["prior"]) or "—"
        if g["more_current"]:
            now += f"\n(+{g['more_current']} more on the review screen)"
        if g["more_prior"]:
            before += f"\n(+{g['more_prior']} more)"
        guidance.append([g["topic"].replace("_", " "), g["status"], before, now])
    flags = [[f["category"].replace("_", " "), f"“{f['quote']}”", f["speaker"], str(f["page"]), f["label"]]
             for f in c["flags"]] or [["—", "No governance or accounting flags found in the transcript", "", "", ""]]
    gaps = [[g["item"], g["reason"]] for g in c["gaps"]] or [["—", "No gaps"]]
    sources = [[s["type"].replace("_", " "), s["quarter"], s["published"] or "—", s["sha256"], s["path"]]
               for s in c["sources"]]
    return {"head": head, "notes": c["notes"], "sample": report.SAMPLE_BANNER if c["sample_estimates"] else None,
            "headline": [h["text"] for h in c["headline"]] or ["No verified moves against estimate to report."],
            "metric_head": metric_head, "metrics": metrics,
            "guidance_head": ["Topic", "Status", f"Prior quarter ({comps['prior']})", f"This quarter ({c['quarter']})"],
            "guidance": guidance,
            "flags_head": ["Category", "Quote", "Speaker", "Page", "Status"], "flags": flags,
            "gaps_head": ["Item", "Reason"], "gaps": gaps,
            "sources_head": ["Type", "Quarter", "Published", "SHA-256", "File"], "sources": sources}


def audit_rows(conn, snap):
    c = snap["content"]
    rid = snap["id"]
    rows = conn.execute("SELECT time, user, action, item, details FROM audit_log WHERE item LIKE ? OR item LIKE ?"
                        " OR item LIKE ? ORDER BY id", (f"{rid}%", f"{c['company']}/%", f"check:{c['company']}:%")).fetchall()
    return [list(r) for r in rows]


# ---------------------------------------------------------------- Excel

def to_excel(snap, path, audit):
    s = sections(snap)
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    bold, red = Font(bold=True), Font(bold=True, color="C00000")
    fill = PatternFill("solid", fgColor="DDEBF7")
    wrap = Alignment(wrap_text=True, vertical="top")
    r = 1
    ws.cell(r, 1, f"Change Report – {snap['content']['company_name']} – {snap['content']['quarter']}").font = Font(bold=True, size=14)
    if snap["status"] != "approved":
        ws.cell(r, 4, "DRAFT").font = Font(bold=True, size=14, color="C00000")
    r += 1
    if s["sample"]:
        ws.cell(r, 1, s["sample"]).font = red
        r += 1
    r += 1
    for k, v in s["head"]:
        ws.cell(r, 1, k).font = bold
        ws.cell(r, 2, v)
        r += 1
    for n in s["notes"]:
        ws.cell(r, 1, "Note").font = bold
        ws.cell(r, 2, n).alignment = wrap
        r += 1
    r += 1
    ws.cell(r, 1, "Headline summary").font = Font(bold=True, size=12)
    r += 1
    for h in s["headline"]:
        ws.cell(r, 1, f"• {h}")
        r += 1
    r += 1
    ws.cell(r, 1, "Metric table").font = Font(bold=True, size=12)
    r += 1
    for i, h in enumerate(s["metric_head"], 1):
        cell = ws.cell(r, i, h)
        cell.font, cell.fill, cell.alignment = bold, fill, wrap
    for row in s["metrics"]:
        r += 1
        for i, v in enumerate(row, 1):
            ws.cell(r, i, v).alignment = wrap
    for col, w in zip("ABCDEFGHI", (34, 18, 26, 26, 30, 12, 60, 40, 16)):
        ws.column_dimensions[col].width = w

    for title, head_key, key, widths in (("Guidance", "guidance_head", "guidance", (16, 18, 70, 70)),
                                         ("Flags", "flags_head", "flags", (18, 80, 20, 8, 20)),
                                         ("Gaps", "gaps_head", "gaps", (50, 80)),
                                         ("Sources", "sources_head", "sources", (16, 10, 12, 66, 40))):
        sh = wb.create_sheet(title)
        if snap["status"] != "approved":
            sh.cell(1, 1, "DRAFT").font = Font(bold=True, color="C00000")
        for i, h in enumerate(s[head_key], 1):
            cell = sh.cell(2, i, h)
            cell.font, cell.fill = bold, fill
        for j, row in enumerate(s[key], 3):
            for i, v in enumerate(row, 1):
                sh.cell(j, i, v).alignment = wrap
        for i, w in enumerate(widths):
            sh.column_dimensions[chr(65 + i)].width = w
    sh = wb.create_sheet("Audit log")
    for i, h in enumerate(["Time", "User", "Action", "Item", "Details"], 1):
        sh.cell(1, i, h).font = bold
    for j, row in enumerate(audit, 2):
        for i, v in enumerate(row, 1):
            sh.cell(j, i, v)
    for col, w in zip("ABCDE", (24, 16, 26, 40, 80)):
        sh.column_dimensions[col].width = w
    wb.save(path)


# ---------------------------------------------------------------- PDF

def to_pdf(snap, path):
    s = sections(snap, currency="Rs ")        # the standard PDF fonts have no ₹ glyph
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=7, leading=8.5)
    draft = snap["status"] != "approved"

    def p(text, style=small):
        text = str(text).replace("₹", "Rs ")       # also in pre-written sentences (headline, notes)
        return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>"), style)

    def table(head, rows, widths):
        t = Table([[p(h) for h in head]] + [[p(c) for c in row] for row in rows], colWidths=[w * mm for w in widths],
                  repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7")),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(10 * mm, 7 * mm, f"{snap['content']['company_name']} {snap['content']['quarter']} – "
                                           f"{'DRAFT' if draft else 'APPROVED'} – page {doc.page}")
        if s["sample"]:
            canvas.setFillColor(colors.HexColor("#C00000"))
            canvas.drawRightString(287 * mm, 7 * mm, s["sample"])
        if draft:
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
            canvas.drawCentredString(148 * mm, 100 * mm, "DRAFT")
        canvas.restoreState()

    story = [Paragraph(f"Change Report – {snap['content']['company_name']} – {snap['content']['quarter']}"
                       + (" (DRAFT)" if draft else ""), styles["Title"])]
    if s["sample"]:
        story.append(Paragraph(f"<font color='#C00000'>{s['sample']}</font>", styles["BodyText"]))
    story.append(table(["Item", "Value"], s["head"], (40, 120)))
    for n in s["notes"]:
        story.append(p(f"Note: {n}"))
    story += [Spacer(1, 4 * mm), Paragraph("Headline summary", styles["Heading3"])]
    story += [p(f"• {h}", styles["BodyText"]) for h in s["headline"]]
    story += [Spacer(1, 4 * mm), Paragraph("Metric table", styles["Heading3"]),
              table(s["metric_head"], s["metrics"], (34, 20, 28, 28, 30, 15, 60, 38, 18)), PageBreak(),
              Paragraph("Guidance changes", styles["Heading3"]), table(s["guidance_head"], s["guidance"], (25, 25, 110, 110)),
              Spacer(1, 4 * mm), Paragraph("Governance / accounting flags", styles["Heading3"]),
              table(s["flags_head"], s["flags"], (30, 150, 35, 15, 30)),
              Spacer(1, 4 * mm), Paragraph("Gaps", styles["Heading3"]), table(s["gaps_head"], s["gaps"], (90, 170)),
              Spacer(1, 4 * mm), Paragraph("Sources", styles["Heading3"]),
              table(s["sources_head"], s["sources"], (25, 18, 20, 110, 90))]
    SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                      topMargin=10 * mm, bottomMargin=12 * mm).build(story, onFirstPage=decorate, onLaterPages=decorate)


# ---------------------------------------------------------------- export

def snapshot(conn, cfg, company, quarter):
    """The approved snapshot if the report is approved and unchanged, else a fresh draft."""
    st = report.status(conn, cfg, company, quarter)
    if st["status"] == "approved":
        row = conn.execute("SELECT snapshot FROM reports WHERE id = ?", (report.report_id(company, quarter),)).fetchone()
        return json.loads(row["snapshot"])
    return report.build(conn, cfg, company, quarter) | {"status": "draft", "approved_by": None, "approved_at": None}


def export(conn, cfg, company, quarter, out_dir=OUT, user=None):
    snap = snapshot(conn, cfg, company, quarter)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = "APPROVED" if snap["status"] == "approved" else "DRAFT"
    base = out_dir / f"{company}_{quarter}_{label}"
    for stale in out_dir.glob(f"{company}_{quarter}_*.*"):
        stale.unlink()
    to_excel(snap, base.with_suffix(".xlsx"), audit_rows(conn, snap))
    to_pdf(snap, base.with_suffix(".pdf"))
    db.audit(conn, "report_exported", snap["id"], {"status": snap["status"], "fingerprint": snap["fingerprint"],
                                                  "files": [base.with_suffix(".xlsx").name, base.with_suffix(".pdf").name]},
             user=user)
    conn.commit()
    return snap, [base.with_suffix(".xlsx"), base.with_suffix(".pdf")]
