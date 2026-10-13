# Step 10: Change Report, review screen and exports

Status: **Done (13 Oct).** All 10 reports are approved and exported as APPROVED Excel and PDF.

**How they were approved:** on the user's instruction ("just approve everything"), as a bulk approval. The reviewer recorded on every item is "Bulk approval on user instruction (Claude Code)". Each item's comment says it was approved on that instruction and **not individually reviewed**. The analyst's item-by-item review is still to be done in Step 11.

**The 6 low-confidence figures were actually checked against their sources first:**
- **Titan revenue, 5 quarters:** sale of products + other operating revenue equals the XBRL figure in each release (for example Q1 FY27 p9: 20,787 + 569 = 21,356). Q4 FY25 was read from the Q1 FY26 release.
- **Reliance Q1 FY27 PAT attributable to owners:** 20,946, read on the scanned results page (p9).

Their notes record exactly what was checked.

```
python run.py export --company all --quarter all      # Excel + PDF for every report (DRAFT until approved)
streamlit run app.py                                  # review screen
```

Done when: one company-quarter goes from documents to an approved Excel and PDF report, end to end.
- **Shown on a copy of the database** by `tests/test_report_flow.py`: review every item → approve → export APPROVED Excel and PDF that match → a correction returns the report to Draft.
- **On the real database:** all 10 reports are approved, and they stay approved after a full pipeline re-run.

## The Change Report (`copilot/report.py`)

One report per company and quarter, built fresh from the database each time it is viewed:

| Section | Contents |
|---|---|
| Header | Company, quarter, period, basis, status (Draft / Approved), approver and time, number of documents used, company notes (Titan bullion and net debt; M&M net debt and Q4 KPI source) |
| Banner | "Estimates are synthetic SAMPLE values, not an analyst view." The estimate column is headed "Estimate (SAMPLE)" (decided 13 Oct) |
| Headline summary | The 3–5 largest moves against estimate (High, then Medium, then Low), from **verified figures only**, written with the procedure's template. Example: "PAT attributable to owners of ₹5,455 crore was 8.0% above the estimate of ₹5,051 crore (Medium)." |
| Metric table | One row per metric (and segment): reported value; prior quarter, year-ago and estimate, each with its change; severity vs estimate; management explanation; source; verification status |
| Guidance changes | Per topic: up to **2 current and 2 prior-quarter quotes**, analyst-approved ones first and rejected ones left out, with a count of the rest (decided 13 Oct). Status is repeated / updated, new, or not repeated |
| Flags | Each flag quote with speaker, page and "for analyst review" (none this round) |
| Gaps | Missing figures, comparisons with no comparator, and unverified (low-confidence) figures, each with its reason |
| Sources | Every document used: type, quarter, publication date, SHA-256, file |

**Explanations:**
- A segment row shows a quote only if the quote names that segment, using `segment_keywords` in `commentary_rules.yaml`. Otherwise one generic quote would repeat on every row.
- A company-level row prefers a quote that names its metric (EBITDA, margin, PAT, …).

## Review and approval (`copilot/review.py`, `app.py`)

**Review screen:**
- Pick a company and quarter.
- Read the report and open the source of any figure: the PDF page image, the XBRL fact and its context, or the analyst-model cell.
- Approve, reject, comment on or correct each metric row, guidance candidate and flag.
- Approve the report, then export.

**Rules:**
- **Every item must be reviewed** (approve, reject or correct; a comment alone doesn't count).
- **Low-confidence figures** (decided 13 Oct): approving such a row needs a note saying what was checked against the source. The figures then become **Manually verified**. The check is stored against the exact value, so it **survives re-runs** while the value is unchanged.
- **Correct:** needs a reason. The original extraction is kept; the correction is a new figure that supersedes it, and comparisons are recomputed.
- **Approval** needs a reviewer name, no unreviewed items and no unresolved low-confidence figure. It saves a **snapshot** and a SHA-256 **fingerprint** of the report's content.
- **Back to Draft:** if anything in the content changes later (a corrected value, a new transcript, a changed figure), the fingerprint no longer matches and the report returns to **Draft**. This is written to the audit log.
- **Stable review keys:** reviews are keyed by metric and segment or by quote, not by database id, so they survive pipeline re-runs.
- **Exporting never approves.**

## Exports (`copilot/export.py`)

- **Snapshots:** an approved report exports from its saved snapshot; anything else is built fresh and exported as **DRAFT**, with "DRAFT" on every sheet and a watermark on every PDF page.
- **Shared content:** Excel and PDF are written from the same display rows, so they match. A test checks every reported value appears in both.
- **Excel sheets:** Report, Guidance, Flags, Gaps, Sources, **Audit log** (this report's entries).
- **PDF:** landscape A4, with the status and SAMPLE banner on every page. The standard PDF fonts have no ₹ sign, so the PDF writes "Rs".
- **Files:** `output/<COMPANY>_<QUARTER>_<DRAFT|APPROVED>.xlsx/.pdf`. They are not kept in Git.

## State before approval

| Report | Items to review | Blockers besides review |
|---|---|---|
| Titan Q4 FY26 / Q1 FY27 | 20 / 22 | Low-confidence revenue (own quarter and comparators) and the EBITDA margins derived from it |
| Asian Paints | 19 / 14 | — |
| M&M | 19 / 19 | — |
| Infosys | 47 / 35 | — (many guidance candidates) |
| Reliance | 23 / 23 | Q1 FY27: low-confidence PAT |

## Fix made during approval

Running the checks again without re-extracting added the "cross-checked in…" note a second time. That changed one approved report's fingerprint and sent Reliance Q1 FY27 back to Draft after a re-run. The checks now rebuild their notes from scratch (`verify.extraction_note`), and the report was re-approved. The flow tests now reset their database copy to "nothing reviewed" first.

## Limits (Phase 1)

- **Corrections and derived figures.** Correcting an input does not recompute derived figures (for example, revenue → EBITDA margin). Correct the derived row too, if needed.
- **Reviewer identity** is a name typed on the screen, not a secure login.
- **PDF currency sign:** the PDF uses "Rs" instead of "₹".
