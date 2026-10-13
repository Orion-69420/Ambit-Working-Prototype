# Step 7: Read estimates from the analyst model

Status: **Done (13 Oct).** Built with a **sample** model, because no real analyst model is available.

**Update after the Step 8 review:** the model was rebuilt without Titan net debt. It now holds **165 estimates** and has a new hash; the counts below are from the first build.

To rebuild the sample model (needed only if the figures change):

```
python scripts/build_sample_model.py
```

To read the estimates (part of the normal run, after Steps 5–6):

```
python run.py run --company all --quarter all
```

Done when: every mapped estimate is loaded with its cell reference, and the model's hash is unchanged.

## Result

- **166 estimates read**, none without a value. They cover:
  - revenue, EBITDA, EBITDA margin, PAT and EPS
  - segment revenue and segment results for every segment
  - the 12 operating KPIs
  - net debt (Q4 FY26 only)
  - both target quarters
- **The model's SHA-256 is identical before and after every read.** Both hashes are written to the audit log.
- **Registration:** the model is a document of type `analyst_model`. Each estimate stores its sheet, cell, estimate date and `is_sample = 1`.

## The sample model (`models/sample_analyst_model.xlsx`)

Decided 13 Oct: one sheet per company, synthetic values offset from the actuals, and core + segments + KPIs covered.

| | |
|---|---|
| Sheets | `About` (marks the file as SAMPLE and synthetic), then one sheet per company |
| Layout | Rows are metrics (segments and KPIs included); columns are `Q4FY26E` and `Q1FY27E`. Row 4 holds the estimate dates (10 Apr 2026, 10 Jul 2026, before any company reported) |
| Values | Each estimate is the reported figure moved by a fixed offset (−12% to +8%, ±10–180 bps, or ±0.5–7 pp), picked deterministically from company, metric, segment and quarter |
| Consistency | EBITDA margin = estimated EBITDA ÷ estimated revenue. EPS moves in proportion to PAT |
| Not modelled | Operating cash flow and capex (annual only, always in Gaps) |

Graded against the actuals with the Step 3 bands, the sample gives **98 Low, 35 Medium and 33 High** variances, a realistic spread for testing reports.

**The workbook is committed to Git**, so every clone reads the same file with the same hash. Rebuilding it changes the hash, because xlsx files embed timestamps.

`config/model_map.yaml` maps each metric and segment to its cell for each quarter. The builder generates it, and it is validated on load: an unknown company, metric or segment, or a unit mismatch, stops the run.

## How reading works (`copilot/estimates.py`)

- **Read-only:** opened with `load_workbook(read_only=True, data_only=True)`, so only cached values are read and the file is never saved.
- **Formulas:** a formula with no cached value, or an empty cell, is recorded as a **missing** estimate. It is never calculated.
- **Exact values:** Excel numbers are converted to exact decimals (57328.55 stays 57328.55).
- **Hash check:** the file is hashed before and after reading. Any change stops the run with an error.

## Departures from the procedure

- `estimates` gains a `segment` column, because segment estimates need one.
- The model is registered as a document with company and quarter set to `ALL`, because it covers every company.
