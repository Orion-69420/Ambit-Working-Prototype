# Step 1: Lock scope and collect documents

Status: **Done (13 Oct).** Scope is locked. Documents: 76 collected (73 in Step 1, plus 3 Titan comparator decks added in Step 6), and the 2 missing are covered by another source.

Done when: the sample is locked, and every required document is either in `data/` or listed as missing in `config/sources.yaml`. Ambit sign-off is not required for this prototype.

## Sample

| Company | Broad type | What it helps us test |
|---|---|---|
| Titan | Retail | Segment reporting + operating KPIs |
| Asian Paints | Consumer/manufacturing | Segment + operational metrics |
| Mahindra & Mahindra | Auto | Multiple businesses/segments + complex financial reporting |
| Infosys | IT services | IT KPIs: constant-currency growth, utilisation, attrition, deal wins |
| Reliance Industries | Conglomerate | Multiple segments + very different disclosure structure |

## Decisions (13 Oct) and how they depart from the procedure

| Decision | Procedure said | Now |
|---|---|---|
| Sample size | 3 companies, one manufacturing sub-sector, 6 reports | **5 companies, 5 sectors, 10 reports** |
| Infosys | IT metric set is Phase 3 | **In Phase 1**: common metric set (incl. derived EBITDA), with IT metrics as its operating KPIs |
| Auto company | — | **M&M replaces Tata Motors**: the 2025 demerger would make year-ago comparatives restated, which is Phase 3 |
| Retail company | — | **Titan replaces Trent**: Trent holds no earnings calls, so it has no transcripts |
| Infosys presentation | Investor presentation | Not filed on NSE, so **KPIs come from the fact sheet in the results bundle** |
| Revised filings | — | **The revised filing is the source of record**, and the original is kept beside it |
| Analyst model | Real or sample | **Sample model** in an agreed layout, with every estimate labelled "Sample" |
| Severity thresholds | Proposed bands | **Same bands for all sectors** |

Unchanged:
- Quarters: Q4 FY26 and Q1 FY27
- Comparators: Q3 FY26, Q4 FY25 and Q1 FY26
- Basis: consolidated
- FY: April–March
- Metric list and EBITDA definition: as in procedure Section 2 (confirmed 13 Oct). EBITDA = profit before exceptional items and tax + finance costs + depreciation and amortisation − other income

Note on M&M: its consolidated figures include Mahindra Finance, which is an NBFC. NBFC metrics stay out of scope.

## Operating KPIs (chosen 13 Oct)

The KPIs were chosen from the downloaded Q4 FY26 and Q1 FY27 decks. For Infosys, the fact sheet stands in for the deck. Page numbers below are for Q1 FY27.

| Company | KPI | Unit | Where | Comparators |
|---|---|---|---|---|
| Titan | Jewellery secondary sales growth, overall *(changed in Step 6)* | % YoY | "Secondary YoY Growth" table (p21) | Each deck states its own quarter only; comparators come from the comparator quarters' decks |
| Titan | Jewellery like-to-like secondary growth *(changed in Step 6)* | % YoY | Same table | Same. Replaces the prose figures, which mixed overall and like-to-like growth |
| Asian Paints | Decorative India volume growth | % YoY | Volume growth slide (p14) | 10-quarter series on the slide |
| Asian Paints | Standalone gross margin | % of net sales | Gross margin trend slide (p24) | 9-quarter series on the slide. Standalone, not consolidated |
| M&M | SUV volumes | '000 units | Market leadership in SUV slide (p30) | 9-quarter series on the slide |
| M&M | SUV revenue market share | % | Same slide | Same |
| Infosys | Constant-currency revenue growth | % QoQ and YoY | Fact sheet p1 | Shown on the fact sheet |
| Infosys | Utilisation, excluding trainees | % | Fact sheet p2 | Current, prior and year-ago columns |
| Infosys | Voluntary attrition (LTM, IT services) | % | Fact sheet p2 | Same |
| Reliance | Jio ARPU | ₹ per month | RJIL key operating metrics (p19) | Current, prior and year-ago columns |
| Reliance | Jio customer base | Mn | Same table | Same |
| Reliance | Jio per-capita data consumption | GB per month | Same table | Same |

KPI notes:
- **M&M Q4 FY26:** the Q4 deck is a full-year deck with annual figures only. Q4 FY26 KPI values are read from the 9-quarter series in the **Q1 FY27 deck** (`data/MM/Q1FY27/presentation.pdf`). The report must label this source as published 30 Jul 2026, after Q4 results day.
- **Growth-rate KPIs** (Titan's two, Asian Paints volume growth, Infosys CC growth) are already rates of change. Step 3 should compare them in percentage points, not as % change of a %.
- **Titan** (revised in Step 6): both KPIs come from the deck's "Secondary YoY Growth" table, with exact values.
- **Not chosen:**
  - Titan store count and retail area (no year-ago figure in the deck)
  - Infosys large-deal TCV
  - Jio churn
  - Reliance O2C (it doesn't disclose its own GRM)
  - M&M tractors (only growth percentages)

**Knock-on effects:** going from 6 to 10 reports means more manual verification in Step 11, and each company needs its own PDF rules (Step 6). The procedure and the timeline (Section 9) need updating to match.

## Document collection

The register is `config/sources.yaml` (75 entries in Step 1; 78 after Step 6 added Titan's three comparator decks). For each company it lists:
- XBRL and results release for all 5 quarters
- Presentation for the 2 target quarters
- Transcripts for Q3 FY26, Q4 FY26 and Q1 FY27

Every collected entry records its NSE URL, broadcast date and SHA-256 hash.

To reproduce the collection:

```
pip install pyyaml
python scripts/collect_sources.py
```

The script uses NSE's public APIs: `integrated-filing-results` for XBRL and `corporate-announcements` for PDFs. It picks each document by rule, anchored on the date of the consolidated XBRL results.

Content checks run on every PDF (PyMuPDF):
- No scanned results releases.
- Every results release mentions consolidated results, the right quarter-end date and revenue from operations.
- Every transcript is an earnings call labelled with the right quarter.

| Missing | Reason | Covered by |
|---|---|---|
| Infosys presentations (Q4 FY26, Q1 FY27) | Not filed on NSE. infosys.com blocks scripted downloads | Fact sheet inside `results_release.pdf`, which has constant-currency growth, utilisation, attrition, large deals and headcount |

Notes:
- **Asian Paints Q4 FY26 XBRL:** the revised filing (15 Jul 2026) is `xbrl.xml`. The original (29 May 2026) is kept as `xbrl_original.xml`.
- **Infosys results releases:** these are large bundles of 15–41 MB that include the auditors' reports.

## Open items for the team (no Ambit sign-off needed)

- [ ] Design the layout of the sample analyst model (Step 7)
- [ ] Name who acts as the reviewing analyst on the review screen
