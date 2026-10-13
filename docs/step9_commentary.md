# Step 9: Extract guidance and flags from transcripts

Status: **Done (13 Oct).** Part of the normal run:

```
python run.py run --company all --quarter all
```

Done when: each company-quarter has its guidance table and flag list, with every item quoted and sourced. **All 10 report quarters have both.** Every stored item has its exact quote, page, speaker and document.

## Result (15 transcripts: Q3 FY26, Q4 FY26 and Q1 FY27 for each company)

| | Count |
|---|---|
| Guidance candidates | 86 |
| Explanations ("due to", "driven by" …) | 102 |
| Governance / accounting flags | **0**. Across all 15 transcripts only one flag phrase occurs ("…I don't think we are going to have a **penalty** on diesel…", M&M Q3 FY26), and it is correctly skipped as negated |

Guidance against the prior quarter (status by topic):

| Report | Topics |
|---|---|
| Titan Q4 FY26 / Q1 FY27 | jewellery, margin: not repeated; revenue: new · jewellery: new; revenue: repeated / updated |
| Asian Paints | costs: not repeated; margin: new; revenue, volume: repeated / updated · margin, revenue, volume: repeated / updated |
| M&M | farm: new; revenue: not repeated; SUV: repeated / updated · costs: new; farm: not repeated; SUV: repeated / updated |
| Infosys | CC growth, margin, revenue: repeated / updated; deals, people: not repeated · CC growth, margin: repeated / updated; revenue, costs: not repeated |
| Reliance | capex, margin: not repeated; O2C: new; revenue: repeated / updated · margin: new; O2C: not repeated; revenue: repeated / updated |

**Example it catches:** Infosys's revenue guidance moved from "1.5% to 3.5%… in constant currency" (Q4 FY26) to "1.5% to 3%" (Q1 FY27). Operating margin guidance stays at "20% to 22%".

## How it works (`copilot/commentary.py`, rules in `config/commentary_rules.yaml`)

1. **Speaker turns:** per-company patterns mark speakers.
   - "Name:" for Titan, Asian Paints and M&M.
   - A name on its own line for Infosys. It counts only if the name is a known speaker, so lines like "Thank You" are skipped.
   - Reliance's explicit labels: presentation segments with timestamps, "Company Speaker (…)" and "Questioner (…, firm)".
   - Page headers and footers are dropped. Text before the first speaker (cover letter, participant lists) is ignored.
2. **Who is management:** taken from each transcript's own management list and stored as a roster per company. M&M's Q4 analyst meet also has its business CEOs answer (Farm, Auto, Mahindra Finance, Lifespaces, Logistics, Aerospace), so they are on its roster. The moderator is excluded. Everyone else (analysts, journalists) is not management.
3. **Sentences:** each turn is split into sentences, and each sentence keeps the page on which it starts.
4. **Rules:**
   - **Guidance:** a management sentence with a forward-looking phrase and a tracked topic. Questions and safe-harbour boilerplate are excluded.
   - **Explanation:** a management sentence with a topic and a cause phrase.
   - **Flag:** a flag phrase from any non-moderator speaker, unless negated just before it ("no", "not", "n't", "never" …). Flags are always "for analyst review".
5. **Guidance table:** current guidance by topic beside the prior quarter's.
   - Both quarters have it: "repeated / updated".
   - Current only: "new".
   - Prior only: **"not repeated"** (never "withdrawn").
6. **Audit:** every extraction and every flag is written to the audit log.

## Tuning done on the real transcripts

- **"we will" dropped from the guidance phrases.** It matches almost every management sentence and buried the real guidance.
- **Questions are no longer guidance**, even when management repeats them ("Do you want to give a guidance…?").
- **Infosys topic fix.** "guidance" was itself an Infosys topic keyword, which filed margin guidance under CC growth. CC growth now needs "revenue (growth) guidance" or "constant currency".
- **Negations now include contractions** ("don't"), which fixed the M&M false flag.
- **Headings are not speakers.** Lines such as "TITAN MANAGEMENT SPEAKERS" or "Chief Financial Officer" are no longer read as speaker names.

## Known limits (keyword rules, Phase 1)

- **Candidates, not conclusions.** Some items are general statements rather than numeric guidance. The analyst approves or rejects each one on the review screen (Step 10).
- **Duplicates.** Infosys states its guidance in both the press conference and the earnings call, so it appears twice.
- **Topics.** A sentence gets the first matching topic, with the company's own topics tried first.
