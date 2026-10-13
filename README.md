# Results-to-Thesis Monitoring Copilot (Phase 1)

A local, rule-based prototype built by IFSA IIT Kharagpur for Ambit. It does the first pass an equity analyst does when a company reports its quarterly results.

## What it does

On results day an analyst reads the company's filing, results release, investor presentation and earnings-call transcript. They pick out the numbers that matter, compare them with their own model and with earlier quarters, and judge what changed. This copilot does that first pass and produces one **Change Report** per company and quarter.

For every tracked metric, the report shows:
- **The reported value**, read from the company's own documents.
- **The change** against the prior quarter, the same quarter last year, and the analyst's estimate, each graded **Low / Medium / High** by size.
- **What management said** about it: an exact quote from the earnings call, with speaker and page.
- **Exactly where the number came from:** the XBRL tag, or the PDF page and table row, plus whether it passed the automated checks.

Each report opens with a **headline summary**: the 3–5 largest moves against the estimate, written as plain sentences, for example:

> PAT attributable to owners of ₹5,455 crore was 8.0% above the estimate of ₹5,051 crore (Medium).

It also has:
- **Guidance changes:** this quarter's guidance beside last quarter's. For example, Infosys revenue guidance moved from 1.5–3.5% to 1.5–3%.
- **Governance and accounting flags**, such as auditor qualifications or restatements.
- **Gaps:** anything not disclosed or not verified, with the reason.
- **Sources:** every document used, with its SHA-256 hash.

Reports are exported to **Excel and PDF**.

**Three principles:**
1. **Every figure is sourced.** If a number can't be found or checked, it goes under Gaps. It is never guessed, zero-filled or swapped for another period.
2. **The analyst model is read-only.** The copilot reads estimates from it and never writes to it. Its hash is checked before and after every read.
3. **The analyst stays in control.** Nothing is final until every item has been reviewed and the report approved. A later change sends the report back to Draft.

Phase 1 is rule-based, with **no LLM or paid API**.

**Phase 1 coverage:**
- **Companies:** Titan, Asian Paints, Mahindra & Mahindra, Infosys and Reliance Industries.
- **Quarters:** Q4 FY26 and Q1 FY27, consolidated.
- **Reports:** 10, all approved.
- **Verification:** all 655 figures in them were re-checked against their sources.

## How it works

```
 NSE filings ──► collect ──► ingest ──► extract ──────────┐
 (XBRL, results release,     (hash,     XBRL figures      │
  presentation, transcript)   page text) PDF KPIs          ├──► verify ──► compare ──► report ──► review ──► export
                                         transcript quotes │    (checks)   (changes,   (build)    (analyst)  (Excel,
 analyst model ─────────────────────────► estimates ──────┘               grades)                           PDF)
                                         (read-only)
                        every step is written to an append-only audit log
```

1. **Collect** (`scripts/collect_sources.py`). Downloads each company's filings from NSE's public data: the XBRL results filing, the results release, the investor presentation and the call transcript, for the two report quarters and their comparator quarters. Every file's URL, date and SHA-256 is recorded in `config/sources.yaml`. Anything unavailable is recorded as missing, with the reason.
2. **Ingest** (`copilot/ingest.py`). Registers each document after checking its hash, and stores the text of every PDF page, numbered as in a PDF viewer. Scanned (image-only) pages are flagged.
3. **Extract.**
   - **Financials from XBRL** (`xbrl_extract.py`): revenue, PAT, EPS, the inputs to EBITDA, and segment revenue and results. A fact is used only if it covers exactly that quarter's three months on the configured basis. Values become exact ₹ crore decimals. Segments are matched by name, because their position changes between filings. EBITDA and the margin are derived with their formula and inputs recorded.
   - **Operating KPIs from PDFs** (`pdf_extract.py`): for example Titan like-to-like growth, Asian Paints volume growth, M&M SUV volumes, Infosys utilisation and Jio ARPU. Each value is found by word position: where a row label meets a column header, or directly above a quarter label on a chart. Never "a number somewhere on the page". The rules live in `config/pdf_rules/<company>.yaml`.
   - **Transcripts** (`commentary.py`): splits each call into speaker turns and sentences with page numbers, and picks out the following, each stored as an exact quote with speaker and page:
     - management **guidance** (forward-looking phrase + tracked topic)
     - **explanations** ("due to", "driven by")
     - **flags**, skipping negated mentions such as "no qualified opinion"
   - **Estimates** (`estimates.py`): reads the mapped cells of the analyst model, read-only and from cached values only.
4. **Verify** (`verify.py`). Automated checks on every figure:
   - the source is recorded
   - the value is on the cited page
   - correct period, basis and unit
   - XBRL revenue and PAT appear in the results release
   - segments add up to the total
   - derived figures use only verified inputs

   Each figure ends as **Verified**, **Low confidence** (with the reason) or **Missing**.
5. **Compare and grade** (`compare.py`). Change against the prior quarter, the year-ago quarter and the estimate:
   - % for amounts, basis points for margins, percentage points for growth rates
   - "n.m." when the base is zero or negative
   - graded against `config/thresholds.yaml`
   - a missing comparator is recorded as a gap
6. **Report** (`report.py`). Builds the report from the database. The headline uses only verified figures.
7. **Review and approve** (`app.py`, `review.py`). On the review screen the analyst opens the source behind any number (the PDF page image, the XBRL fact, or the model cell) and approves, rejects, comments on or corrects each item. Corrections keep the original. A low-confidence figure can be approved only with a note saying what was checked against the source. Approval saves a snapshot and a fingerprint of the report; if anything changes later, the report returns to Draft.
8. **Export** (`export.py`). Excel (including the report's audit log) and PDF, both from the same snapshot. Unapproved reports are marked DRAFT.

## Using it

You need **Python 3.11**.

```
py -3.11 -m venv .venv                         # macOS/Linux: python3.11 -m venv .venv
.venv\Scripts\activate                         # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**Build everything from scratch.** Source documents, the database and the reports are not kept in Git.

```
python scripts/collect_sources.py                      # download filings from NSE into data/
python run.py init-db                                  # create the database
python run.py ingest --company all --quarter all       # register documents, store page text
python run.py run    --company all --quarter all       # extract, estimates, verify, compare, transcripts
python run.py export --company all --quarter all       # Excel + PDF into output/
```

`--company` accepts TITAN, ASIANPAINT, MM, INFY, RELIANCE or `all`; `--quarter` accepts a quarter such as Q1FY27, or `all`.

**Review and approve:**

```
streamlit run app.py --server.address localhost
```

Open http://localhost:8501, enter your name, pick a company and quarter, and review each item. Then click **Approve report** and **Export Excel + PDF**.

**Checks and tests:**

```
python run.py check-config               # validate the configuration
pytest                                   # 109 tests
python scripts/verify_register.py        # re-check every displayed figure against its source
python scripts/check_procedure.py        # cross-check the build against the Phase 1 procedure
python scripts/build_pipeline_doc.py     # rebuild docs/Pipeline_Documentation.docx with current counts
```

## Configuration

All business rules are in readable YAML under `config/`. The code holds no company-specific numbers.

| File | Holds |
|---|---|
| `companies.yaml` | Companies, segment name aliases, notes shown in each report |
| `metrics.yaml` | The metric dictionary: definitions, units, XBRL elements, PDF labels, formulas |
| `thresholds.yaml` | Low / Medium / High bands: against the estimate, and looser bands against prior and year-ago quarters |
| `sources.yaml` | Every source document with its URL, date and SHA-256 |
| `pdf_rules/<company>.yaml` | Where each KPI sits in that company's presentation or fact sheet |
| `commentary_rules.yaml` | Transcript rules: speaker formats, management rosters, guidance, explanation and flag phrases, topics |
| `model_map.yaml` | Which analyst-model cell holds each estimate |

**The analyst model is a synthetic sample** (`models/sample_analyst_model.xlsx`), because no real model was available. Every report says so. To use a real model, map its cells in `model_map.yaml`.

## Project layout

```
app.py        review screen (Streamlit)
run.py        command line
copilot/      the pipeline: ingest, xbrl_extract, pdf_extract, estimates, commentary, verify,
              compare, report, review, export (+ db, config, derive)
config/       YAML configuration
scripts/      collect_sources, build_sample_model, verify_register, check_procedure
models/       sample analyst model
docs/         decisions and records for every step, metric dictionary, verification register,
              procedure cross-check, handover
tests/        pytest
data/         source documents + SQLite database (not in Git)
output/       Excel and PDF reports (not in Git)
```

## Further reading

| Document | Contents |
|---|---|
| [docs/Pipeline_Documentation.docx](docs/Pipeline_Documentation.docx) ([PDF](docs/Pipeline_Documentation.pdf)) | The full pipeline documentation and access guide, in the format of the Phase 1 procedure |
| [docs/metric_dictionary.md](docs/metric_dictionary.md) | Every metric, its source and how changes are graded |
| [docs/procedure_crosscheck.md](docs/procedure_crosscheck.md) | Each procedure requirement checked against the build (44 pass, 8 noted departures, 0 fail) |
| [docs/step11_handover.md](docs/step11_handover.md) | Deliverables, acceptance checklist, open items |
| [docs/manual_verification.csv](docs/manual_verification.csv) | All 655 report figures with their source and re-checked value |
| `docs/step1_scope.md` … `docs/step10_report.md` | What each build step did and every decision taken |

The implementation procedure (`Ambit_Phase1_Procedure.docx`) is internal and kept out of this public repository.

## Known limitations (Phase 1)

- **PDF rules are written per company and layout.** A redesigned slide needs a rule update.
- **Scanned (image-only) PDFs are not read.** Titan's Q1 FY26 deck is one, so those year-ago KPIs are gaps.
- **Transcript rules find keyword candidates.** The analyst decides what is real guidance.
- **Estimates are synthetic** until Ambit's model is mapped.
- **Cash flow and balance sheet:** these are filed only for the full year or at 31 March, so they appear as gaps, or as net debt for Q4 only.
- **Corrections and derived figures.** Correcting an input does not recompute the figures derived from it, so correct those rows too.
- **Reviewer identity** is a typed name, not a login.
- **PDF currency sign:** PDF reports write "Rs" because the standard PDF fonts have no ₹ sign.

**Still open:**
- the 2–3 minute demo video
- the team's hand spot-check of 30 flagged figures
- an item-by-item analyst review (the 10 reports were bulk-approved on instruction)
