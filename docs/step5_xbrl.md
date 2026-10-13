# Step 5: Extract core financials from XBRL

Status: **Done (13 Oct).** To rerun:

```
python run.py run --company all --quarter all
```

`run` currently runs only Step 5. With a single quarter, for example `--quarter Q1FY27`, it extracts that quarter plus its comparator quarters.

Done when: revenue, PAT, EPS and the EBITDA inputs are extracted for all company-quarters, or recorded as missing.

## Result

All **25 company-quarter filings** were extracted (5 companies × 5 quarters), giving 595 figures:
- revenue, PAT attributable to owners, basic EPS
- the five EBITDA inputs, with EBITDA and EBITDA margin derived from them
- 220 segment figures

**No core figure is missing.** The 54 `missing` figures are all expected:

| Missing | Count | Why |
|---|---|---|
| Net debt and its inputs, outside Q4 | 48 | The balance sheet is filed only at 31 March |
| Inter-segment revenue (some Titan and Infosys filings) | 6 | Not tagged in those filings. Recorded as missing, never zero |

Net debt at Q4 FY26 (₹ crore):

| Company | Net debt |
|---|---|
| Titan | 10,505 (mostly gold metal loans) |
| Asian Paints | 1,620 |
| Infosys | −22,201 (net cash) |
| Reliance | 2,28,444 |

## How it works (`copilot/xbrl_extract.py`)

- **Contexts:** a fact is used only if its context covers exactly that quarter's three months (Jan–Mar for Q4, not the year-to-date) and has no dimensions. Balance-sheet facts use the quarter-end instant.
- **Basis:** the filing's `NatureOfReportStandaloneConsolidated` must match the configured basis, or extraction stops.
- **Units:** money is converted from rupees to ₹ crore with exact decimals. The original value and unit are kept.
- **Sources:** each figure stores its element name and context ID.
- **Missing values:** a nil, absent or conflicting fact is stored as `missing` with a note. It is never stored as zero.
- **Segments:** labels are matched through the aliases in `companies.yaml`. An unknown label stops extraction.
- **Derived metrics:** EBITDA and the margin record their formula, input values and input figure IDs. Formulas are evaluated with exact decimal arithmetic and never through `eval`.
- **Reruns:** a rerun replaces the earlier figures for that filing. It refuses if an analyst correction exists.
- **Audit:** every extraction is written to the audit log.
- **Status:** figures are stored as `extracted`. The Step 8 checks set `verified` or `low_confidence`.

## Findings

- **Per-segment revenue element:** the per-segment element is `SegmentRevenue`, which is before inter-segment eliminations. `SegmentRevenueFromOperations` is only the total. Added inputs: `inter_segment_revenue` and `segment_revenue_total` for the Step 8 reconciliation, and `total_income` for Titan.
- **Titan rename confirmed:** Q4 FY25 "Watches and Wearables" is ₹1,134 crore, the same value the Q1 FY26 filing shows for that quarter under "Watches".
- **Spot check against the results releases:** revenue and PAT were looked up in the release text for all 25 filings.
  - **Matched:** M&M and Infosys.
  - **Asian Paints:** the numbers are there, but the PDF text splits them ("10,541 .94"), so Step 8 must normalise spacing.
  - **Titan:** the release prints only the parts of revenue (sale of products + other operating revenue). They sum to the XBRL figure.
  - **Reliance:** the results releases are scanned pages with an imperfect OCR text layer that drops the current-quarter column. Most figures are confirmed through the next quarter's comparator columns. Q1 FY27 revenue (311,850) is confirmed. Q1 FY27 PAT (20,946) cannot be found in any text.

**Effect on Step 8:** the "XBRL vs results release" cross-check will mark several Reliance figures low confidence because the OCR is incomplete, not because the figures are wrong. Step 11's manual check will clear them.
