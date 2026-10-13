# Step 6: Extract operating KPIs from PDFs

Status: **Done (13 Oct).** To rerun:

```
python run.py run --company all --quarter all
```

That runs Step 5 (XBRL) and then Step 6 (KPIs).

Done when: the agreed KPIs are extracted for every company-quarter with a page reference.

Segment revenue and segment results come from XBRL (Step 3 decision), so this step covers the 12 operating KPIs.

## Result

Running the rules on every relevant document gives **79 KPI figures**. Each records:
- page number
- row label and column header, chart series, or caption
- the value as printed
- the source document

Coverage for each report quarter:

| KPI | Q4 FY26: current / prior / year-ago | Q1 FY27: current / prior / year-ago |
|---|---|---|
| Titan secondary growth, overall and like-to-like | 54 / 36 / 20 · 50 / 32 / 15 | 38 / 54 / **gap** · 33 / 50 / **gap** |
| Asian Paints decorative volume growth | 12.4 / 7.9 / 1.8 | 9.0 / 12.4 / 3.9 |
| Asian Paints gross margin (standalone) | 45.6 / 44.9 / 44.9 | 43.8 / 45.6 / 43.2 |
| M&M SUV volumes ('000) | 183.8 / 178.9 / 149.1 * | 174.7 / 183.8 / 152.1 |
| M&M SUV revenue market share | 24.5 / 24.1 / 23.5 * | 25.0 / 24.5 / 27.3 |
| Infosys CC growth (YoY) | 4.1 / 1.7 / 4.8 | 2.4 / 4.1 / 3.8 |
| Infosys utilisation excl. trainees | 83.0 / 84.1 / 84.9 | 84.9 / 83.0 / 85.2 |
| Infosys voluntary attrition (LTM) | 12.6 / 12.3 / 14.1 | 13.0 / 12.6 / 14.4 |
| Jio ARPU (₹/month) | 214.0 / 213.7 / 206.2 | 215.6 / 214.0 / 208.8 |
| Jio customers (Mn) | 524.4 / 515.3 / 488.2 | 533.3 / 524.4 / 498.1 |
| Jio data per capita (GB/month) | 42.3 / 40.7 / 33.6 | 43.7 / 42.3 / 37.0 |

\* Read from the Q1 FY27 deck (published 30 Jul 2026), because the Q4 FY26 deck is annual-only.

- **Gap:** Titan's Q1 FY26 deck is a scanned image (61 of 66 pages have no text), so the year-ago values for the Q1 FY27 report go to Gaps. Decided 13 Oct.
- **Consistency:** where the same KPI and quarter appears in more than one document (for example, Infosys utilisation for Q4 FY25 appears in three fact sheets), every copy agrees.

## Rules (`config/pdf_rules/<company>.yaml`, engine in `copilot/pdf_extract.py`)

Each value is located by word position (PyMuPDF), never as "a number somewhere on the page":

| Kind | Finds | Used for |
|---|---|---|
| `grid` | Value where a row label meets a column header (quarter labels or dates such as "Jun 30, 2026") | Infosys utilisation and attrition, Jio table |
| `chart` | Value directly above each quarter label on the chart axis, optionally within part of the page | Asian Paints, M&M |
| `labelled` | Value directly above a caption | Titan "Overall" and "Like to like" |
| `text` | A sentence pattern; applies to the document's own quarter | Infosys CC growth |

Safeguards found necessary on the real documents:
- **Row labels must start their line.** Otherwise Reliance's commentary bullet "₹7 YoY increase in ARPU…" was taken as the ARPU row.
- **Value patterns screen out annotations.** For example, "~1.8%" material-inflation notes sit above Asian Paints' gross-margin bars.
- **Chart regions keep side-by-side charts apart.** M&M has volumes on the left and market share on the right.
- **Split quarter labels are joined.** Examples: "Q4" next to or above "FY26", "Q1F27", "Q4 F26".
- **The first caption block wins.** Titan's Tanishq block comes before CaratLane's identical captions.
- **Scanned documents are reported as such.** They are never silently missed.
- **Number parsing:** handles Indian and western digit grouping, (35.2) as negative, "–" or nil as missing (never zero), and "c." or "~" as approximate.

## Change to the metric dictionary

Titan's KPIs are now **secondary growth (overall)** and **like-to-like secondary growth**, both from the "Secondary YoY Growth" table (decided 13 Oct). The earlier prose-based figures mixed two measures: Q4's "54%" was overall growth, while Q1's "c.33%" was like-to-like. The table also gives exact numbers, so no "approximate" values remain in Phase 1.

## Departures from the procedure

- **Tool:** PyMuPDF word positions are used instead of pdfplumber tables. Most KPIs are charts, which have no table structure. PyMuPDF is on the procedure's stack for "text with positions".
- **Extra documents:** three Titan comparator decks (Q3 FY26, Q4 FY25, Q1 FY26) were added to the register. Titan states each quarter's growth only in that quarter's deck.
- **Selection deferred:** figures are stored for every quarter each document shows. Step 8 picks which copy a comparison uses, following the procedure's rule: the current document first, then that quarter's own document.
