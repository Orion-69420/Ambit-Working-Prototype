# Step 8: Verify, compare and grade

Status: **Done (13 Oct).** Part of the normal run:

```
python run.py run --company all --quarter all
```

**Updated by the review after Step 8** (`docs/review_after_step8.md`):
- Prior and year-ago moves are graded on looser `period` bands.
- Titan net debt is no longer shown.
- Results press releases are also searched by the cross-source check.

The severity table below is from before that review; the review record has the current one.

Done when: every metric for every company-quarter has its comparisons or a recorded gap. **Checked: all 190 report rows across the 10 reports pass.**

## Automated checks (`copilot/verify.py`)

| Check | How | On failure |
|---|---|---|
| Source recorded | XBRL: document, element, context. PDF: document and page | `missing` (goes to Gaps) |
| Value on cited page | PDF figure: the printed value appears on the cited page | Low confidence |
| Period | Figure belongs to a tracked quarter. XBRL contexts are checked for the exact three months at extraction | Low confidence |
| Basis | Matches the metric's configured basis (consolidated; standalone for Asian Paints gross margin) | Low confidence |
| Unit | XBRL money is `INR`; EPS is `INRPerShare` | Low confidence |
| Cross-source | XBRL revenue and PAT appear in that quarter's results release, **or in a later release's comparator columns** (decided 13 Oct; the note records which release) | Low confidence |
| Segment sum | Segment revenues − inter-segment = segment total = revenue. Titan's segments add up to total income. Reliance checks segments → total only (see below) | Low confidence |
| Derived inputs | Every input of EBITDA, margin or net debt is verified | Low confidence |
| Margin recompute | **Not applicable.** No company-reported EBITDA margin is extracted, and companies' own definitions differ from ours | — |

Matching numbers in PDF text allows one stray space between characters ("8,35 8.9 1"), without joining neighbouring columns.

### Result

All figures pass except **6, which are low confidence**. Step 11's manual check clears them.

| Figure | Reason |
|---|---|
| Titan revenue, all 5 quarters | The release prints only sale of products + other operating revenue, never the total (decided 13 Oct: leave as low confidence) |
| Reliance Q1 FY27 PAT | The scanned release's OCR text drops the current column, and no later release exists yet |

The other Reliance figures that the OCR missed are confirmed in the next quarter's release. For example, Q4 FY26 revenue of 298,621 appears in the Q1 FY27 release.

**Reliance segments:** its segment revenue is "Value of Sales & Services", which **includes GST**. Revenue from operations is net of GST, and the GST line is not tagged in the XBRL. So only segments → segment total is reconciled (`segment_sum_to: segment_total` in `companies.yaml`).

## Comparisons and grading (`copilot/compare.py`)

- **Comparator copy:** the copy read from the target quarter's document first, then the comparator quarter's own document, then any other document (procedure Section 2). XBRL comparators always come from their own filing. KPI comparators come from the current deck or fact sheet. M&M Q4 FY26 KPIs come from the Q1 FY27 deck.
- **Changes:** % for amounts, bps for margins and % levels, pp for growth rates. A zero or negative base shows the absolute change only, marked **n.m.**
- **Grading:** uses the stored value rounded to 2 decimals. On the bands, "under 2%" is Low and exactly 2% is Medium.
- **Gaps:** a missing comparator or estimate is recorded with a reason. Operating cash flow and capex are recorded as missing figures with their reason ("full-year only").
- **Sample estimates:** every "vs estimate" comparison is against the sample model.

| Report | Compared | Gaps | Low | Medium | High | n.m. |
|---|---|---|---|---|---|---|
| Titan Q4 FY26 / Q1 FY27 | 53 / 49 | 1 / 2 | 12 / 12 | 5 / 5 | 33 / 29 | 3 / 3 |
| Asian Paints | 23 / 21 | 1 / 0 | 10 / 2 | 4 / 8 | 9 / 11 | 0 / 0 |
| M&M | 45 / 45 | 0 / 0 | 14 / 11 | 3 / 9 | 28 / 25 | 0 / 0 |
| Infosys | 74 / 72 | 1 / 0 | 19 / 27 | 21 / 19 | 32 / 26 | 2 / 0 |
| Reliance | 56 / 54 | 1 / 0 | 24 / 14 | 10 / 12 | 22 / 28 | 0 / 0 |

- **Gaps:** net debt has no prior-quarter figure (no balance sheet at 31 December), and Titan's Q1 FY27 KPIs have no year-ago figure (the Q1 FY26 deck is scanned).
- **n.m.:** Titan's corporate (unallocated) segment result, and Infosys net debt (net cash).
- **Many Highs are QoQ and YoY moves.** These companies grew fast, and the procedure uses the same bands for all three comparisons. For example, Titan's YoY revenue includes bullion sales.

Spot-checked on M&M Q1 FY27:
- revenue vs estimate: 58,187.57 vs 57,328 = **+1.50%**, Low
- EBITDA margin vs estimate: **−37.5 bps**, Low
- SUV market share vs prior quarter: exactly **50 bps**, Medium (boundary)
