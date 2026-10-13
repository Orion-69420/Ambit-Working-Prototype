# Step 11: Manual verification, approval and handover

Status (13 Oct): **4 of 5 deliverables complete.** The demo video is still to be recorded, and the team's hand spot-check of 30 figures is still to be done.

## Deliverables (procedure Section 9)

| # | Deliverable | Status | Where |
|---|---|---|---|
| 1 | Working prototype and source code | ✅ | This repository. Rebuilds from scratch with the README commands (checked on a clean copy) |
| 2 | Change Reports, selected companies, two quarters | ✅ **10 reports** (5 companies × Q4 FY26, Q1 FY27), approved, each in Excel and PDF | `output/` on the working machine (not in Git; regenerate with `python run.py export --company all --quarter all`) |
| 3 | Metric dictionary | ✅ | `config/metrics.yaml` plus the one-page [metric_dictionary.md](metric_dictionary.md) |
| 4 | Demo video, 2–3 minutes | ⬜ **Not recorded yet** (deferred 13 Oct) | Suggested script in the section below |
| 5 | README | ✅ | [README.md](../README.md): setup, configuration, run, review, export, known limitations |

## Manual verification ([manual_verification.csv](manual_verification.csv))

- **655 rows:** every figure displayed in every report (reported, prior quarter, year-ago and estimate), each with its source and page or XBRL context.
- **How each value was re-read:** through a path independent of the extraction code (`scripts/verify_register.py`):
  - XBRL: the raw XML text
  - PDF: the cited page, freshly opened
  - derived figures: recomputed from raw XBRL values
  - estimates: the model cell
- **Result: 655 match, 0 mismatches.** The checker was tested to catch a wrong value of every kind (XBRL, PDF, derived, estimate).
- **These rows are marked "automated re-read", not a person's check.** The procedure asks for a person, ideally someone who didn't write the rule. So **30 rows (3 per report) are flagged `spot_check = YES`** for the team to check by hand against the source and sign in the spot-check columns (decided 13 Oct).
- **No rules needed fixing.** No report was edited by hand.

The 6 figures that the automated cross-check left as low confidence were checked against their sources before approval:
- **Titan revenue (5 quarters):** sale of products + other operating revenue in each release equals the XBRL figure.
- **Reliance Q1 FY27 PAT attributable to owners:** read as ₹20,946 crore on the scanned results page (p9).

## Approval

- **All 10 reports are approved**, on the user's instruction (13 Oct), as a bulk approval recorded as "Bulk approval on user instruction (Claude Code)".
- **Each item's comment says it was not individually reviewed.**
- **Exports:** the approved Excel and PDF files were exported from the approved snapshots.
- **Still to do:** an analyst can review item by item on the review screen at any time. Any correction returns that report to Draft for re-approval.

## Acceptance checklist (procedure Section 8)

| Check | Status |
|---|---|
| Companies, quarters, metrics and thresholds approved by Ambit | **Not applicable.** Ambit sign-off was dropped for this prototype (13 Oct); scope was decided by the team (docs/step1_scope.md, step3_metrics.md) |
| Change Reports generated | ✅ 10 (the procedure planned 6 for 3 companies; scope widened to 5) |
| Each report has current, prior-quarter, year-ago and estimate values, or a stated gap | ✅ All 188 report rows checked |
| Every figure has a source reference and a verification status | ✅ |
| Every figure manually verified and logged | ◐ All 655 re-read independently and logged. **Hand spot-check of 30 rows pending** |
| Guidance and flags quoted with page references | ✅ 86 guidance, 102 explanations, 0 flags (one negated match), all with quote, speaker and page |
| Analyst model unchanged (hash match) | ✅ Checked before and after every read and logged. The model is a **synthetic sample** |
| Every report approved on the review screen | ◐ Approved through the review logic as a bulk approval on instruction, not item by item on the screen |
| Excel and PDF exports match each other | ✅ Built from one snapshot. A test checks every value appears in both |
| Audit log covers ingest to export | ✅ ingest → extraction → checks → comparisons → transcripts → reviews → approval → export (each report's log is a sheet in its Excel file) |
| No LLM or paid API used | ✅ |
| Clean install from README works | ✅ Checked on a clean copy: same results, re-check 655 / 0 mismatches. Source download needs NSE access |
| Metric dictionary, demo video and README delivered | ◐ Demo video pending |

## Open items

1. **Record the demo video** (2–3 minutes). Flow: select company → view report → open a source → review an item → approve → export → audit log. All reports are approved, so record on a database copy with one report reset to Draft, or correct a value, which sends the report back to Draft.
2. **Team spot-check:** fill the spot-check columns for the 30 flagged rows in `manual_verification.csv`.
3. **Optional: item-by-item analyst review** of the bulk-approved reports on the review screen.
4. **Phase 2 inputs:** Ambit's real analyst model (map it in `config/model_map.yaml`) and quarterly cash flow and balance-sheet coverage.

## Demo script (suggested)

| Time | Show |
|---|---|
| 0:00–0:20 | Review screen. Pick a company and quarter. What the copilot does |
| 0:20–0:50 | Headline summary and metric table: moves vs estimate with severity, source and verification on every row |
| 0:50–1:20 | Open a row: the PDF page image or the XBRL fact behind the number |
| 1:20–1:45 | Guidance tab: for example Infosys revenue guidance 1.5–3.5% → 1.5–3%, quoted with speaker and page |
| 1:45–2:10 | Review an item, then **Approve report** |
| 2:10–2:30 | **Export**, then open the Excel and its Audit log sheet |
