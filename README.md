# Results-to-Thesis Monitoring Copilot (Phase 1)

A local, rule-based prototype by IFSA IIT Kharagpur for Ambit. For each company and quarter it produces a fully sourced Change Report. No LLM or paid API is used.

- Scope and decisions: [docs/step1_scope.md](docs/step1_scope.md)
- Procedure: `Ambit_Phase1_Procedure.docx` (Phase 1 implementation procedure)

## Setup

You need Python 3.11.

```
py -3.11 -m venv .venv                        # macOS/Linux: python3.11 -m venv .venv
.venv\Scripts\activate                        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py init-db                         # creates data/copilot.sqlite
```

## Source documents

Source documents are not kept in Git. To fetch them from NSE into `data/` and record each one in `config/sources.yaml`:

```
python scripts/collect_sources.py
```

## Command line

```
python run.py ingest --company MM --quarter Q1FY27    # Step 4
python run.py run    --company MM --quarter Q1FY27    # Steps 5-9
python run.py export --company MM --quarter Q1FY27    # Step 10
```

Both `--company` and `--quarter` accept `all`. Company IDs are TITAN, ASIANPAINT, MM, INFY and RELIANCE. Quarters are Q4FY25, Q1FY26, Q3FY26, Q4FY26 and Q1FY27.

## Layout

```
config/       companies, sources, and later metrics, thresholds and rules (YAML)
copilot/      application modules; schema.sql holds the SQLite schema
data/         source documents and the SQLite file (not in Git)
docs/         scope record, manual verification register
output/       Excel and PDF reports (not in Git)
scripts/      one-off tools (document collection)
tests/        pytest
```

## Tests

```
pytest
```
