# Review of Steps 1–8 (13 Oct)

A cross-check of everything built so far against the procedure and our decisions, before Step 9.

## What was checked

| Check | Result |
|---|---|
| Fresh rebuild: clean clone + the same documents → `init-db`, `ingest`, `run` | **Identical** to the working database, both before the changes below (696 figures, 166 estimates, 498 comparisons, 77 documents) and after them (676 / 165 / 495 / 82). The only difference after: the working database also records the first sample-model version, as a superseded document |
| Test suite | All pass (85 after this review). Includes every procedure Section 8 case that applies to Steps 1–8 |
| Step records vs the current state | Stale counts corrected: Step 1 register (75 → 78 entries), Step 3 metrics (30 → 33), Step 4 documents and pages |
| Asian Paints revised Q4 FY26 XBRL (source of record) vs original | The revision changed **no tracked figure**. It only added audit disclosures (auditor, opinion, peer review) and reserves |

## Decisions taken in the review

| Topic | Finding | Decision |
|---|---|---|
| QoQ / YoY severity | On one set of bands, 79% of year-ago and 52% of prior-quarter moves graded High, against 20% for estimates | **Looser `period` bands** for prior and year-ago comparisons; the estimate bands are unchanged (`thresholds.yaml`) |
| Titan revenue | Bullion and other operating revenue swing revenue (₹6,313 crore in Q4 FY26 vs ₹1,019 crore a year earlier; +80% YoY) | **Report note** in `companies.yaml` (`report_notes`) |
| Titan net debt | ₹10,505 crore, almost all current borrowings that are mostly gold metal loans (inventory financing) | **Not shown**, as for M&M. The sample model was rebuilt without it (165 estimates; new hash) |
| Low-confidence figures | Titan revenue (5 quarters) and Reliance Q1 FY27 PAT | **Results press releases added** as a second cross-check source (new `press_release` document type) |

## Outcome of adding press releases

- **Reliance:** 5 press releases collected and ingested. They give gross revenue and **total** PAT (₹23,196 crore in Q1 FY27), not PAT attributable to owners (₹20,946 crore). So they did not clear the Q1 FY27 figure.
- **Titan:** files **no results press release on NSE**. Its 5 register entries are recorded as missing.
- **Still low confidence:** the same **6 figures** as before. Step 11's manual check clears them.

## Severity after the change (Q4 FY26 / Q1 FY27)

| Report | Low | Medium | High | Gaps | n.m. |
|---|---|---|---|---|---|
| Titan | 13 / 12 | 10 / 8 | 25 / 26 | 0 / 2 | 3 / 3 |
| Asian Paints | 14 / 4 | 5 / 11 | 4 / 6 | 1 / 0 | 0 / 0 |
| M&M | 16 / 16 | 12 / 14 | 17 / 15 | 0 / 0 | 0 / 0 |
| Infosys | 33 / 40 | 22 / 25 | 17 / 7 | 1 / 0 | 2 / 0 |
| Reliance | 29 / 22 | 22 / 22 | 5 / 10 | 1 / 0 | 0 / 0 |

Titan still has many Highs, because its jewellery business grew 30–50% year on year and bullion swings revenue. The report note explains this.

## Schema changes in this review

- `documents.type` gains `press_release`.
- The table is rebuilt in place by `db._migrate_document_types`, keeping every row (foreign-key check clean). The migration is written to the audit log.
