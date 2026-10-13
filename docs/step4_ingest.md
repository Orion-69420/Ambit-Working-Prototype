# Step 4: Ingest documents

Status: **Done (13 Oct).** To rerun:

```
python run.py init-db
python run.py ingest --company all --quarter all
```

Done when: every document has an ID and a hash, and every PDF page's text is stored.

## Result

| | Count |
|---|---|
| Documents registered (ID + SHA-256) | 73 in Step 4 (25 XBRL, 25 results releases, 15 transcripts, 8 presentations). Now 77: Step 6 added 3 Titan decks and Step 7 the analyst model |
| Register entries not ingested | 2 Infosys presentations. Missing by decision: KPIs come from the fact sheet |
| PDF pages stored | 2,741 in Step 4; 2,941 with the Titan decks (numbered from 1, as in a PDF viewer) |
| Pages flagged as scanned | 153 in 12 documents in Step 4; 215 in 14 with the Titan decks (Titan Q1 FY26 is almost entirely scanned) |
| Audit log | One `document_ingested` entry per document, with its hash, plus `scanned_pages_flagged` per affected document |

How ingestion behaves:
- **Hash check:** each file's hash must match the one recorded in `config/sources.yaml` when it was collected. A changed file is refused and logged as `ingest_failed`.
- **Reruns:** running ingest again skips documents already registered with the same hash.

## Scanned pages (manual handling)

| Document | Pages | Effect |
|---|---|---|
| Titan, Asian Paints, M&M decks (both target quarters) | 1 page each | Image-only slides, not KPI slides. None |
| Reliance decks (Q4 FY26, Q1 FY27) | 8–9 pages each | Image-only slides. The Jio KPI table (p19) is text. None |
| Reliance Q1 FY26 results release | pp 3–9 | Scanned statements. Consolidated results are still readable as text on pp 10 and 14 |
| Infosys Q4 FY25, Q1 FY26, Q3 FY26 results bundles | 29–65 pages each | Scanned signed statements inside the bundles. Consolidated results tables are still text elsewhere in each bundle (3–7 pages) |
| Infosys Q4 FY26 results bundle | p 98 | None |

None of the scanned pages hold a figure the reports need:
- Core figures come from XBRL.
- KPI pages are text.
- The Step 8 cross-check (XBRL vs results release) can use the text pages listed above.
