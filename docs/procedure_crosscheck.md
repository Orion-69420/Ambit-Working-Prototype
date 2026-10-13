# Procedure cross-check (13 Oct)

Every requirement of the Phase 1 procedure (Steps 1–11 and the Section 4 data rules) was checked against the real files, database and outputs. The script `scripts/check_procedure.py` does the checking and can be re-run at any time:

```
python scripts/check_procedure.py
python scripts/check_procedure.py --md docs/procedure_crosscheck_table.md   # write the table
```

**Result: 44 PASS, 8 NOTE, 0 FAIL.**

A **NOTE** is a deliberate departure from the procedure, recorded in the step records, or an item still open:

| NOTE | Why |
|---|---|
| Step 5: comparators "from the same filing" | SEBI integrated filings carry only their own quarter, so each comparator comes from that quarter's own filing (all 5 quarters were downloaded) |
| Step 6: segments from the PDF | Taken from XBRL instead: it's structured and comes from the same filing (Step 3 decision). The PDF is a cross-check |
| Step 6: pdfplumber tables | PyMuPDF word positions are used instead, because most KPIs are charts |
| Step 6: units from the table caption | The KPIs have fixed units defined in the dictionary; no money KPI is read from a PDF |
| Step 8: pp and period bands | Growth rates are compared in percentage points, and prior/year-ago moves use looser bands (Step 3 and the review after Step 8) |
| Step 11: person-checked figures | 655 figures were re-read automatically with 0 mismatches. A hand spot-check of 30 flagged rows is **open** |
| Step 11: analyst approval | All 10 reports were approved as a **bulk approval on the user's instruction**, not item by item |
| Step 11: demo video | **Not recorded yet** |

**Some PASS rows rest on earlier checks rather than a fresh one.** For example, "fresh clone installs" was shown on clean copies in Steps 2, 8 and 11, and the approval rules are covered by `tests/test_report_flow.py`. Their evidence column names the source.

## Results

| Step | Requirement | Result | Evidence |
|---|---|---|---|
| 1 Lock scope, collect documents | Scope agreed (companies, quarters, metrics, EBITDA, thresholds, basis) | **PASS** | 5 companies, quarters Q4FY26, Q1FY27; decided by the team (Ambit sign-off dropped for the prototype) - docs/step1_scope.md |
| 1 Lock scope, collect documents | XBRL + results release for every target and comparator quarter; presentations; current and prior transcripts | **PASS** | 75 required documents, all in the register |
| 1 Lock scope, collect documents | Every file recorded in sources.yaml; unavailable ones marked missing | **PASS** | 81 collected (file present, SHA-256 matches); 7 missing with a reason (INFY Q4FY26 presentation; INFY Q1FY27 presentation; TITAN Q4FY25 press_release; TITAN Q1FY26 press_release; TITAN Q3FY26 press_release; TITAN Q4FY26 press_release; TITAN Q1FY27 press_release) |
| 2 Repository and database | Folder structure and modules of Section 3 | **PASS** | 24 paths present |
| 2 Repository and database | requirements.txt with the Section 3 stack, pinned | **PASS** | lxml==6.1.3, PyMuPDF==1.28.2, pdfplumber==0.11.10, openpyxl==3.1.5, streamlit==1.65.0, reportlab==5.0.1, PyYAML==6.0.3, pytest==9.1.1 |
| 2 Repository and database | SQLite schema (Section 4) and audit-log helper | **PASS** | 7 Section-4 tables + pages, reports; audit_log rows: 1454 |
| 2 Repository and database | Command line: run.py ingest / run / export --company --quarter | **PASS** | subcommands: init-db, check-config, ingest, run, export |
| 2 Repository and database | Fresh clone installs and creates an empty database with one command each | **PASS** | checked on clean copies (Steps 2, 8-review, 11): pip install -r requirements.txt; python run.py init-db |
| 3 Metric dictionary and configuration | Every metric has definition, unit, period type, source mapping and threshold group | **PASS** | 22 report metrics + 11 inputs |
| 3 Metric dictionary and configuration | XBRL element names taken from the actual filings | **PASS** | 18 elements, all present in the downloaded filings |
| 3 Metric dictionary and configuration | companies.yaml, thresholds.yaml, commentary_rules.yaml written | **PASS** | 5 threshold groups (+ period bands); 6 topic sets; transcript rules for 5 companies |
| 3 Metric dictionary and configuration | Validation stops the run on unknown units, duplicate ids, undefined inputs | **PASS** | tests/test_config.py |
| 4 Ingest documents | Every document registered with ID, SHA-256 and metadata | **PASS** | 83 documents (81 source files + analyst model) |
| 4 Ingest documents | Every PDF page's text stored, numbered from 1 | **PASS** | 3052 pages, counts equal each PDF's page count |
| 4 Ingest documents | Scanned pages flagged for manual handling | **PASS** | 215 pages in 14 documents flagged (docs/step4_ingest.md) |
| 5 Core financials from XBRL | Revenue, PAT, EPS and EBITDA inputs for every company-quarter (or recorded missing) | **PASS** | 25 company-quarters x 8 figures present |
| 5 Core financials from XBRL | Each figure stored with element name and context ID | **PASS** | 0 XBRL figures without element/context |
| 5 Core financials from XBRL | Derived metrics record formula and inputs | **PASS** | 65 derived figures, all with formula and inputs |
| 5 Core financials from XBRL | 3-month context only; basis checked; YTD and dimension contexts ignored | **PASS** | xbrl_extract.in_period + basis check; tests/test_xbrl_extract.py (YTD ignored, wrong basis stops) |
| 5 Core financials from XBRL | Comparator values from the same filing where present | **NOTE** | SEBI integrated filings carry only their own quarter, so comparators come from each quarter's own filing (all 5 quarters downloaded) |
| 6 Segments and KPIs from PDFs | A rule file per company | **PASS** | ASIANPAINT, INFY, MM, RELIANCE, TITAN |
| 6 Segments and KPIs from PDFs | Agreed KPIs extracted for every report quarter with a page reference | **PASS** | 12 KPIs, both report quarters, all with page |
| 6 Segments and KPIs from PDFs | Value taken at the matched row/column only (never elsewhere on the page) | **PASS** | grid/chart/labelled rules by word position; tests cover the commentary-mention and same-number-elsewhere traps |
| 6 Segments and KPIs from PDFs | Indian number formats: commas, brackets, '–' as missing | **PASS** | pdf_extract.parse_number + tests |
| 6 Segments and KPIs from PDFs | Segment revenue and segment result | **NOTE** | read from XBRL (structured, same filing) instead of the PDF - decided in Step 3; PDF used only as a cross-check |
| 6 Segments and KPIs from PDFs | Read tables with pdfplumber | **NOTE** | PyMuPDF word positions are used instead: most KPIs are charts with no table structure (pdfplumber stays installed) |
| 6 Segments and KPIs from PDFs | Units from the table caption (crore / lakh / million) | **NOTE** | the 12 KPIs have fixed units defined in metrics.yaml; no money KPI is read from a PDF |
| 7 Estimates from the analyst model | Every mapped estimate loaded with its cell reference | **PASS** | 165 estimates, each with sheet and cell; 0 without value |
| 7 Estimates from the analyst model | Workbook hash unchanged after every read | **PASS** | 8 reads logged, hash before = after in all |
| 7 Estimates from the analyst model | Read-only, cached values only, never saved | **PASS** | openpyxl read_only + data_only; tests: formula without cache = missing |
| 7 Estimates from the analyst model | Sample model labelled 'Sample' (no real model available) | **PASS** | models/sample_analyst_model.xlsx; every estimate is_sample; 'Estimate (SAMPLE)' + banner in reports |
| 8 Verify, compare, grade | Automated checks set every figure's status | **PASS** | statuses: {'manually_verified': 6, 'missing': 64, 'verified': 606} |
| 8 Verify, compare, grade | Every metric has its comparisons or a recorded gap | **PASS** | 188 report rows, 0 incomplete |
| 8 Verify, compare, grade | % for amounts, bps for margins, n.m. for zero/negative base, Low/Medium/High | **PASS** | 8 n.m. comparisons (absolute change only); tests cover 110 vs 100, 18.5% vs 20.0%, band boundaries |
| 8 Verify, compare, grade | Growth-rate KPIs in pp; looser bands for prior/year-ago moves | **NOTE** | decided in Step 3 and the review after Step 8 (thresholds.yaml) |
| 9 Guidance and flags from transcripts | Every item an exact quote with page and speaker | **PASS** | {'explanation': 102, 'guidance': 86}; 0 unsourced |
| 9 Guidance and flags from transcripts | Guidance table vs prior quarter for every report quarter ('not repeated', never 'withdrawn') | **PASS** | commentary.guidance_table; statuses repeated / updated, new, not repeated |
| 9 Guidance and flags from transcripts | Flags skip negated mentions; marked 'for analyst review' | **PASS** | 0 flags: the single flag phrase in 15 transcripts is negated; tests cover 'no qualified opinion' |
| 9 Guidance and flags from transcripts | Speaker turns and sentences keep their page | **PASS** | per-company speaker rules + management rosters; tests |
| 10 Report, review screen, exports | Report assembled with the Section 6 sections | **PASS** | header, headline (3-5 verified moves vs estimate), metric table, guidance, flags, gaps, sources |
| 10 Report, review screen, exports | One company-quarter documents -> approved Excel and PDF end to end | **PASS** | 10 of 10 approved and still current; 20 APPROVED files in output/ |
| 10 Report, review screen, exports | Approval rule; return to draft on change; drafts labelled DRAFT | **PASS** | report.blockers / status / fingerprint; tests/test_report_flow.py |
| 10 Report, review screen, exports | Review screen: open the source of any figure; approve / reject / comment / correct | **PASS** | app.py (Streamlit), smoke-tested with streamlit AppTest |
| 11 Manual verification and handover | Every figure in every report checked and logged | **PASS** | 655 rows, 0 mismatches (independent automated re-read) |
| 11 Manual verification and handover | Checked by a person (not the rule author) | **NOTE** | 30 rows flagged for a hand spot-check; 0 signed so far |
| 11 Manual verification and handover | All reports reviewed and approved by the analyst | **NOTE** | 10 of 10 approved - as a bulk approval on the user's instruction, not item by item |
| 11 Manual verification and handover | Demo video (2-3 min) | **NOTE** | not recorded yet (deferred) |
| 11 Manual verification and handover | README finished | **PASS** | README.md |
| Data rules (Section 4) | Exact decimals, never floats | **PASS** | 0 figures stored as floating point |
| Data rules (Section 4) | Missing is missing, never zero | **PASS** | 0 missing figures with a value |
| Data rules (Section 4) | Corrections saved as a new value with a reason; original kept | **PASS** | schema CHECK + review.record; tests |
| Data rules (Section 4) | Audit log append-only | **PASS** | UPDATE/DELETE rejected by triggers |
