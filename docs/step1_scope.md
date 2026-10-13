# Step 1: Lock scope and collect documents

Status: **Done (13 Oct).** Scope is locked. Documents: 73 collected, and the 2 missing are covered by another source.

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
- Metric list and EBITDA definition: as in procedure Section 2

Note on M&M: its consolidated figures include Mahindra Finance, which is an NBFC. NBFC metrics stay out of scope.

**Knock-on effects:** going from 6 to 10 reports means more manual verification in Step 11, and each company needs its own PDF rules (Step 6). The procedure and the timeline (Section 9) need updating to match.

## Document collection

The register is `config/sources.yaml` (75 entries). For each company it lists:
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
