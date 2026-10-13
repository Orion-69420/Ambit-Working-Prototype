# Metric dictionary: Phase 1

The full definitions, XBRL element names, PDF labels and formulas are in `config/metrics.yaml`. This page is the readable summary.

**Basis:** all figures are consolidated, except Asian Paints gross margin, which the company discloses only standalone. Money is in ₹ crore.

## Financial metrics (all companies)

| Metric | Source | Type | Change shown as |
|---|---|---|---|
| Revenue from operations | XBRL `RevenueFromOperations` | Reported | % |
| EBITDA | XBRL inputs | Derived: profit before exceptional items and tax + finance costs + D&A − other income − share of associates/JVs | % |
| EBITDA margin | — | Derived: EBITDA ÷ revenue × 100 | bps |
| PAT attributable to owners | XBRL `ProfitOrLossAttributableToOwnersOfParent` | Reported | % |
| Basic EPS | XBRL `BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations` | Reported | % |
| Segment revenue | XBRL `SegmentRevenue`, by segment | Reported | % |
| Segment result (EBIT) | XBRL `SegmentProfitLossBeforeTaxAndFinanceCosts`, by segment | Reported | % |
| Net debt | XBRL borrowings − cash, at 31 March | Derived | % |
| Operating cash flow, capex | XBRL, full year only | Reported | always listed under Gaps |

Notes on coverage:
- **Segments:** Titan, M&M, Infosys and Reliance only. Asian Paints reports a single segment.
- **Net debt:** Asian Paints, Infosys and Reliance only, for Q4 FY26. M&M is excluded because its borrowings include Mahindra Finance's lending. Titan is excluded because its borrowings are mostly gold metal loans.

## Operating KPIs

| Company | KPI | Source | Change shown as |
|---|---|---|---|
| Titan | Jewellery secondary sales growth, overall (Tanishq, Mia, Zoya, domestic) | Presentation table | pp |
| Titan | Jewellery like-to-like secondary growth | Presentation table | pp |
| Asian Paints | Decorative India volume growth | Presentation chart | pp |
| Asian Paints | Gross margin (standalone) | Presentation chart | bps |
| M&M | SUV volumes ('000) | Presentation chart; Q4 FY26 values come from the Q1 FY27 deck | % |
| M&M | SUV revenue market share | Presentation chart | bps |
| Infosys | Constant-currency revenue growth (YoY) | Fact sheet in the results bundle | pp |
| Infosys | Utilisation, excluding trainees | Fact sheet | bps |
| Infosys | Voluntary attrition (last 12 months) | Fact sheet | bps |
| Reliance | Jio ARPU (₹ per month) | Presentation table | % |
| Reliance | Jio customer base (Mn) | Presentation table | % |
| Reliance | Jio per-capita data use (GB per month) | Presentation table | % |

## How a change is graded

The severity grades the **size** of a move, not whether it is good or bad.
- Moves **against the estimate** use the main bands. They feed the headline summary.
- Moves **against the prior quarter and the year-ago quarter** use looser bands. Otherwise ordinary growth would grade most of them High.

| Group | Applies to | vs estimate: Low / Medium / High | vs prior and year-ago: Low / Medium / High |
|---|---|---|---|
| Revenue | Revenue, segment revenue | < 2% / 2–5% / > 5% | < 5% / 5–15% / > 15% |
| Profit | EBITDA, segment result, PAT, EPS, net debt | < 5% / 5–10% / > 10% | < 10% / 10–25% / > 25% |
| Margins | EBITDA margin, gross margin, utilisation, attrition, market share | < 50 / 50–150 / > 150 bps | < 100 / 100–300 / > 300 bps |
| Operating KPIs | SUV volumes, Jio ARPU, customers, data | < 5% / 5–10% / > 10% | < 10% / 10–20% / > 20% |
| Rate KPIs | Growth rates the companies disclose | < 2 / 2–5 / > 5 pp | < 5 / 5–10 / > 10 pp |

**Units of change:**
- **pp** (percentage points) for growth rates. For example, growth falling from 38% to 33% is −5 pp, not −13%.
- **bps** for margins and other percentage levels.
- **% change** for amounts.
- If the base is zero or negative, only the absolute change is shown, marked "n.m." (not meaningful).
