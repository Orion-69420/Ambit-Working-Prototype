# Results-to-Thesis Monitoring Copilot (Phase 1)

A local, rule-based prototype by IFSA IIT Kharagpur for Ambit. It reads each company's quarterly XBRL filing, results release, investor presentation and earnings-call transcript. It then produces a fully sourced **Change Report** for each company and quarter.

Each report compares every tracked metric with the prior quarter, the year-ago quarter and the analyst's estimate. It also shows what management said, with an exact quote, and exactly where each figure came from.

- **No LLM or paid API is used.**
- **The analyst stays in control:** the analyst model is only read, never changed, and no report is final without approval.

**Phase 1 coverage:**
- **Companies:** Titan, Asian Paints, Mahindra & Mahindra, Infosys and Reliance Industries.
- **Quarters:** Q4 FY26 and Q1 FY27, all consolidated.
- **Reports:** 10, all approved.

| Document | What it covers |
|---|---|
| [docs/metric_dictionary.md](docs/metric_dictionary.md) | One-page metric dictionary; full detail in `config/metrics.yaml` |
| [docs/step11_handover.md](docs/step11_handover.md) | Deliverables, acceptance checklist and open items |
| [docs/](docs/) | One record per step (`step1_scope` … `step10_report`, `review_after_step8`) with every decision taken |
| [docs/manual_verification.csv](docs/manual_verification.csv) | Every figure in every report, checked against its source |

The implementation procedure (`Ambit_Phase1_Procedure.docx`) is internal and kept out of this public repository.

## Setup

You need Python 3.11.

```
py -3.11 -m venv .venv                        # macOS/Linux: python3.11 -m venv .venv
.venv\Scripts\activate                        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py init-db                         # creates data/copilot.sqlite
```

## Rebuilding everything from scratch

The source documents, the database and the reports are not kept in Git. These commands rebuild them:

```
python scripts/collect_sources.py                     # download filings from NSE into data/ (records hashes)
python run.py init-db
python run.py ingest --company all --quarter all      # register documents, store page text
python run.py run    --company all --quarter all      # extract, read estimates, verify, compare, transcripts
python run.py export --company all --quarter all      # Excel + PDF reports into output/
python scripts/verify_register.py                     # re-check every displayed figure against its source
```

`--company` accepts TITAN, ASIANPAINT, MM, INFY, RELIANCE or `all`. `--quarter` accepts Q4FY25, Q1FY26, Q3FY26, Q4FY26, Q1FY27 or `all`. Reports exist for Q4FY26 and Q1FY27. `python run.py check-config` validates the configuration on its own.

`run` does the following, in order:
1. Extracts XBRL figures.
2. Extracts operating KPIs from the PDFs.
3. Reads estimates from the analyst model, read-only, and confirms its hash is unchanged.
4. Runs the automated checks.
5. Computes changes and severity grades.
6. Extracts guidance, explanations and flags from the transcripts.

## Reviewing and approving

```
streamlit run app.py --server.address localhost
```

On the review screen:
1. Enter your name, then pick a company and quarter.
2. Open the source of any figure: the PDF page image, the XBRL fact, or the analyst-model cell.
3. Review every item: **approve**, **reject**, **comment** or **correct**. A correction needs a reason, and the original value is kept.
4. Click **Approve report**, then **Export**.

**Approval rules:**
- A report can be approved only when every item is reviewed and no low-confidence figure is unresolved.
- Approving a low-confidence row needs a note saying what was checked against the source.
- If anything in an approved report changes later, it returns to **Draft**.
- Exports are labelled DRAFT until approved. Exporting never approves.

## Configuration (all in `config/`, validated on every run)

| File | Holds |
|---|---|
| `companies.yaml` | Companies, segment name aliases, report notes |
| `metrics.yaml` | The metric dictionary: definitions, units, XBRL elements, PDF labels, formulas |
| `thresholds.yaml` | Severity bands: against the estimate, and looser bands against the prior and year-ago quarters |
| `sources.yaml` | Every source document with its NSE URL, date and SHA-256 |
| `pdf_rules/<company>.yaml` | Where each operating KPI sits in the presentations or fact sheet |
| `commentary_rules.yaml` | Transcript rules: speakers, management rosters, guidance, explanation and flag phrases, topics |
| `model_map.yaml` | Analyst-model cell for each metric and quarter |

`models/sample_analyst_model.xlsx` holds **synthetic sample estimates**, because no real analyst model was available. Every report says so.

## Layout

```
app.py        review screen (Streamlit)
run.py        command line
copilot/      ingest, xbrl_extract, pdf_extract, estimates, verify, compare, commentary, report, review, export
config/       YAML configuration (above)
scripts/      collect_sources, build_sample_model, verify_register
models/       sample analyst model
docs/         step records, metric dictionary, verification register, handover
tests/        pytest (run: pytest)
data/         source documents + SQLite database (not in Git)
output/       Excel and PDF reports (not in Git)
```

## Known limitations (Phase 1)

- **PDF rules are written per company and per layout.** A changed slide or fact-sheet layout needs a rule update.
- **Scanned (image-only) PDFs are not read.** Titan's Q1 FY26 deck is one, so those Titan year-ago KPIs are listed as gaps.
- **Transcript rules find keyword candidates.** The analyst judges their meaning and approves or rejects each.
- **Estimates are synthetic**, until Ambit's model is mapped in `model_map.yaml`.
- **Quarterly coverage only.** Operating cash flow and capex are filed only for the full year, and net debt only at 31 March, so they appear as gaps or for Q4 only (Phase 2 item).
- **Corrections and derived figures.** Correcting an input figure does not recompute the figures derived from it, so correct those rows too.
- **Reviewer identity** is a name typed on the screen, not a secure login.
- **PDF currency sign:** the PDF reports write "Rs" because the standard PDF fonts have no ₹ sign. Excel and the screen use ₹.
