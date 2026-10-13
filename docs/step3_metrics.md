# Step 3: Metric dictionary and configuration

Status: **Done (13 Oct).** `python run.py check-config` validates all configuration files. Tests check the configuration against the downloaded filings.

Done when: every metric has a definition, unit, period type, source mapping and threshold group.

## Files

| File | Holds |
|---|---|
| `config/metrics.yaml` | 30 metrics in Step 3 (21 shown in reports, 9 inputs used only to derive other metrics); 33 after Step 5 added three reconciliation inputs (total income, inter-segment revenue, segment total). Also the unit registry |
| `config/companies.yaml` | Companies, and segment name aliases for matching XBRL segment labels |
| `config/thresholds.yaml` | 5 severity groups |
| `config/commentary_rules.yaml` | Rules for transcripts: guidance, explanation and flag phrases, negations, and topics per company |

## Metric dictionary (readable table)

| Metric | Source | Type | Change shown as | Severity group | Companies |
|---|---|---|---|---|---|
| Revenue from operations | XBRL `RevenueFromOperations` | Reported | % | revenue | All |
| EBITDA | Derived from XBRL inputs | Derived | % | profit | All |
| EBITDA margin | EBITDA ÷ revenue × 100 | Derived | bps | margins | All |
| PAT attributable to owners | XBRL `ProfitOrLossAttributableToOwnersOfParent` | Reported | % | profit | All |
| Basic EPS | XBRL `BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations` | Reported | % | profit | All |
| Segment revenue | XBRL `SegmentRevenueFromOperations`, by segment | Reported | % | revenue | Titan, M&M, Infosys, Reliance |
| Segment result (EBIT) | XBRL `SegmentProfitLossBeforeTaxAndFinanceCosts`, by segment | Reported | % | profit | Titan, M&M, Infosys, Reliance |
| Net debt | Borrowings − cash (XBRL, 31 March only) | Derived | % | profit | Asian Paints, Infosys, Reliance (not M&M; not Titan, after the Step 8 review); Q4 FY26 only |
| Operating cash flow, capex | XBRL, full-year only | Reported | — | — | Always listed in Gaps for Phase 1 |
| Titan: secondary growth (overall), like-to-like growth (changed in Step 6) | Presentation table | Reported | pp | rate_kpis | Titan |
| Asian Paints: decorative India volume growth | Presentation | Reported | pp | rate_kpis | Asian Paints |
| Asian Paints: gross margin (standalone) | Presentation | Reported | bps | margins | Asian Paints |
| M&M: SUV volumes | Presentation | Reported | % | operating_kpis | M&M |
| M&M: SUV revenue market share | Presentation | Reported | bps | margins | M&M |
| Infosys: CC growth | Fact sheet | Reported | pp | rate_kpis | Infosys |
| Infosys: utilisation, attrition | Fact sheet | Reported | bps | margins | Infosys |
| Reliance: Jio ARPU, customers, data per capita | Presentation | Reported | % | operating_kpis | Reliance |

**EBITDA** = profit before exceptional items and tax + finance costs + depreciation and amortisation − other income − share of profit of associates and JVs.

**Severity bands** (vs estimate; prior-quarter and year-ago moves use looser `period` bands, added after the Step 8 review: revenue 5 / 15%, profit 10 / 25%, margins 100 / 300 bps, operating KPIs 10 / 20%, rate KPIs 5 / 10 pp)

| Group | Low | Medium | High |
|---|---|---|---|
| revenue | under 2% | 2–5% | over 5% |
| profit | under 5% | 5–10% | over 10% |
| margins | under 50 bps | 50–150 bps | over 150 bps |
| operating_kpis | under 5% | 5–10% | over 10% |
| rate_kpis | under 2 pp | 2–5 pp | over 5 pp |

## What the filings showed

- **XBRL covers only its own quarter.** It has no prior-quarter or year-ago columns. All comparators therefore come from each quarter's own filing, which is why Step 1 downloaded all 5 quarters.
- **XBRL money values are in rupees** (for example, 581875700000 is ₹58,187.57 crore), so they are divided by 10^7 to give ₹ crore.
- **Segment facts are numbered by position, not name.** The positions change between quarters (Infosys reorders its segments), so segments are always matched by label. Any unknown label stops the run.
- **Titan** renamed "Watches and Wearables" to "Watches" from Q1 FY26; the two are treated as one segment, to be confirmed by value in Step 5. Titan's segment revenue also includes other income, so it adds up to total income rather than revenue from operations.
- **Asian Paints** reports a single segment, so segment metrics don't apply to it.
- **Associates' share** sits inside profit before exceptional items and tax for all five companies.
- **Cash flow** is filed only as a full-year figure in Q4. Balance-sheet items are filed only at 31 March.

## Decisions (13 Oct) and departures from the procedure

| Decision | Procedure said | Now |
|---|---|---|
| EBITDA | PBEIT + finance costs + D&A − other income | **Also subtracts the share of associates and JVs** (₹367–553 crore a quarter at M&M) |
| Segment source | Results release PDF | **XBRL** (structured, same filing). The PDF is used as a cross-check only |
| Growth-rate KPIs | % change | **Compared in percentage points**, in the new `rate_kpis` group (2 / 5 pp) |
| % level KPIs (utilisation, attrition, gross margin, market share) | Operating KPI bands, in % | **Compared in bps**, using the margins bands |
| Cash flow and net debt | Show if disclosed | Net debt at Q4 FY26 only (not for M&M, whose borrowings include Mahindra Finance's lending book). OCF and capex go to Gaps |
| Net debt severity | Not specified | Uses the profit bands (5 / 10%) |
