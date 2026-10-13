# The review website

The prototype's "website" is the **Change Report review screen**: a Streamlit app (`app.py`) that runs on your own computer and opens in a browser. It is how an analyst reads the Change Reports, checks where each number came from, and approves them. It isn't hosted on the internet; it runs locally against the database built by the pipeline.

## What it does

**Sidebar**
- **Reviewer name:** the name recorded against every action. It's a typed name, not a login.
- **Company and Quarter:** pick one of the 10 reports. There are 5 companies (Titan, Asian Paints, M&M, Infosys, Reliance) and 2 quarters (Q4 FY26, Q1 FY27).
- **Status:** DRAFT or APPROVED, with the approver and time.
- **Progress bar:** how many items are reviewed ("19 of 19 items reviewed"), plus anything still blocking approval.
- **Approve report:** enabled only when every item is reviewed and no low-confidence figure is unresolved.
- **Export Excel + PDF:** writes the report to `output/` and offers download buttons.

**Main page**
- **Header:** company, quarter, basis and comparison quarters, the red **SAMPLE** banner (the estimates are synthetic), and the company notes (for example Titan's bullion note).
- **Headline summary:** the 3–5 largest moves against the estimate, as sentences.
- **Tabs:**
  - **Metrics:** the full metric table. Open any row to see:
    - **the source behind the reported figure:** the PDF page itself as an image, or the raw XBRL fact and its context
    - the prior-quarter, year-ago and estimate comparisons, each with its own source or model cell
    - any low-confidence warning
    - the review history and the review form
  - **Guidance:** each topic's guidance this quarter beside last quarter's, and every guidance candidate to review.
  - **Flags:** governance and accounting flags. There are none in the current transcripts.
  - **Gaps:** what isn't disclosed or verified, and why.
  - **Sources:** every document used, with its date and SHA-256.

**Review actions** (on each metric row, guidance candidate and flag)

| Action | Effect |
|---|---|
| approve | Accepts the item. On a low-confidence row it needs a comment saying what was checked against the source |
| reject | Rejects it, for example a guidance candidate that isn't really guidance; it then leaves the report |
| comment | Adds a note. This does **not** count as reviewing the item |
| correct | Metric rows only: enter the right value and a reason. The original is kept and the comparisons are recalculated |

If anything in an approved report changes later (a correction, a re-run with different figures), the screen shows a warning and the report goes back to **DRAFT** until it is approved again.

**Current state (13 Oct):**
- **All 10 reports are APPROVED**, as a bulk approval on the user's instruction. So **Approve report** is greyed out on every report, and **Export** gives the APPROVED files.
- Item-by-item review is still possible: any correction returns that report to Draft for re-approval.

## Hosting it locally

### 1. One-time setup

You need Python 3.11 and the repository:

```
git clone https://github.com/Orion-69420/Ambit-Working-Prototype.git
cd Ambit-Working-Prototype
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS or Linux, use `python3.11 -m venv .venv` and `source .venv/bin/activate`.

### 2. Build the data (once, or after the sources change)

The website shows what's in `data/copilot.sqlite`. On a fresh clone that database doesn't exist yet, so build it first. This needs internet access to nseindia.com for the download.

```
python scripts/collect_sources.py
python run.py init-db
python run.py ingest --company all --quarter all
python run.py run    --company all --quarter all
```

On the machine where the prototype was built, this is already done; skip to step 3.

**Approvals are not in Git.** Reviews and approvals live only in that machine's database. On a fresh clone every report starts as DRAFT.

### 3. Start the website

From the repository folder, with the environment activated:

```
streamlit run app.py --server.address localhost
```

- Streamlit prints `URL: http://localhost:8501` and usually opens the browser itself.
- **Leave this terminal open.** The website runs only while this command is running.
- To stop it, press **Ctrl + C** in that terminal.

`--server.address localhost` makes the site reachable **only from this computer**. Without it, Streamlit also listens on your network address, and anyone on the same network could open the review screen.

### 4. Open it

- **Browser:** go to **http://localhost:8501** in Chrome, Edge or Firefox.
- **VS Code:** Ctrl + Shift + P → "Simple Browser: Show" → `http://localhost:8501`.

## Useful options

| Need | Command |
|---|---|
| Port 8501 is busy | `streamlit run app.py --server.address localhost --server.port 8502`, then open http://localhost:8502 |
| Don't open a browser automatically | add `--server.headless true` |
| Let a colleague on the same office network open it (only on a trusted network) | `streamlit run app.py --server.address 0.0.0.0`, then share `http://<your-computer's-IP>:8501`. There is no login, so anyone who can reach it can review and approve |

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| **"Failed to Load Page", ERR_CONNECTION_REFUSED** | The website isn't running. Start it with step 3 and keep that terminal open |
| `streamlit: command not found` / `No module named streamlit` | The environment isn't activated. Run `.venv\Scripts\activate` first, or use `.venv\Scripts\python -m streamlit run app.py --server.address localhost` |
| Error about a missing database, or empty reports | The data hasn't been built on this machine. Run step 2 |
| "Port 8501 is already in use" | Another copy is running: use it, stop it, or start on port 8502 |
| **Approve report** is greyed out | Either the report is already approved, or items are still unreviewed or low-confidence (listed under the progress bar) |
| A report suddenly shows DRAFT again | Something in it changed after approval (for example a correction or a re-run). Review and approve it again |
| Export says DRAFT | The report isn't approved, so files are labelled DRAFT. Approve it first for APPROVED files |

## Where the website's output goes

- **Exports** are written to `output/<COMPANY>_<QUARTER>_<APPROVED|DRAFT>.xlsx` and `.pdf`, and are also offered as downloads on the screen.
- **Every action** (reviews, approvals, exports) is written to the audit log in the database, and to the "Audit log" sheet of each exported Excel file.
