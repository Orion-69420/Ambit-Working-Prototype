from decimal import Decimal as D

import pytest

from copilot import compare, config, db, verify

GROUPS = {"revenue": {"unit": "pct", "low_below": 2, "high_above": 5, "period": {"low_below": 5, "high_above": 15}},
          "margins": {"unit": "bps", "low_below": 50, "high_above": 150, "period": {"low_below": 100, "high_above": 300}}}


def test_period_comparisons_use_looser_bands():
    assert compare.severity(D("8"), GROUPS["revenue"], "estimate") == "high"
    assert compare.severity(D("8"), GROUPS["revenue"], "prior") == "medium"
    assert compare.severity(D("15.01"), GROUPS["revenue"], "year_ago") == "high"
    assert compare.severity(D("4.99"), GROUPS["revenue"], "year_ago") == "low"


# ---------------------------------------------------------------- changes and grading

def test_procedure_examples():
    assert compare.change(D("110"), D("100"), "pct")["change_pct"] == D("10.00")
    assert compare.change(D("18.5"), D("20.0"), "bps")["change_bps"] == D("-150.00")
    pp = compare.change(D("38"), D("54"), "pp")
    assert pp["change"] == D("-16.00") and pp["size"] == D("-16.00") and pp["change_pct"] is None


@pytest.mark.parametrize("base", [D("0"), D("-22201")])
def test_zero_or_negative_base_is_not_meaningful(base):
    ch = compare.change(D("-19947"), base, "pct")
    assert ch["not_meaningful"] == 1 and ch["change_pct"] is None and ch["change"] is not None


@pytest.mark.parametrize("size, expected", [
    (D("1.99"), "low"), (D("2"), "medium"), (D("5"), "medium"), (D("5.01"), "high"), (D("-5.01"), "high")])
def test_band_boundaries_graded_consistently(size, expected):
    assert compare.severity(size, GROUPS["revenue"]) == expected


def test_margin_bands():
    assert compare.severity(D("-150"), GROUPS["margins"]) == "medium"
    assert compare.severity(D("49.99"), GROUPS["margins"]) == "low"
    assert compare.severity(None, GROUPS["margins"]) is None


# ---------------------------------------------------------------- number matching

def test_number_regex_tolerates_split_digits_but_not_merged_columns():
    assert verify.number_regex("8,358.91").search("Revenue from operations 8,35 8.9 1 8,549.44")
    assert verify.number_regex("10,541.94").search("10,541 .94 9,246.70")
    assert not verify.number_regex("58,187.57").search("158,187.57")
    assert not verify.number_regex("187").search("58,187.57")


def test_formats_cover_indian_grouping_and_decimals():
    f = verify.formats("269496")
    assert {"269,496", "2,69,496", "269496"} <= f
    assert "10,541.94" in verify.formats("10541.94")


# ---------------------------------------------------------------- end to end on a small database

@pytest.fixture
def setup(tmp_path):
    cfg = config.load_all()
    conn = db.init_db(tmp_path / "t.sqlite")

    def doc(company, quarter, typ, pages):
        cur = conn.execute("INSERT INTO documents (company, quarter, type, file_path, sha256, ingested_at)"
                           " VALUES (?, ?, ?, 'x', ?, ?)", (company, quarter, typ, f"{company}{quarter}{typ}", db.now()))
        for i, t in enumerate(pages, 1):
            conn.execute("INSERT INTO pages (document_id, page, text) VALUES (?, ?, ?)", (cur.lastrowid, i, t))
        return cur.lastrowid

    def fig(company, quarter, metric, value, method="xbrl", period=None, segment=None, doc_id=None, **kw):
        row = dict(company=company, quarter=quarter, metric=metric, period=period or quarter, basis="consolidated",
                   segment=segment, value=None if value is None else str(value),
                   unit=cfg.metrics[metric]["unit"], method=method, status="extracted", created_at=db.now(),
                   document_id=doc_id, source_ref="OneD" if method == "xbrl" else "1",
                   source_detail="X", original_unit="INR" if method == "xbrl" else None) | kw
        cols = ", ".join(row)
        return conn.execute(f"INSERT INTO figures ({cols}) VALUES ({', '.join('?' * len(row))})",
                            tuple(row.values())).lastrowid

    return cfg, conn, doc, fig


def test_cross_source_passes_on_a_later_release_and_notes_it(setup):
    cfg, conn, doc, fig = setup
    x = doc("RELIANCE", "Q4FY26", "xbrl", [])
    doc("RELIANCE", "Q4FY26", "results_release", ["OCR text with the current column missing 269,496"])
    doc("RELIANCE", "Q1FY27", "results_release", ["Revenue from Operations 311,850 298,621 248,660"])
    fid = fig("RELIANCE", "Q4FY26", "revenue", 298621, doc_id=x)
    verify.run(conn, cfg, "RELIANCE", "Q4FY26")
    status, note = conn.execute("SELECT status, note FROM figures WHERE id = ?", (fid,)).fetchone()
    assert status == "verified" and "Q1FY27 results release" in note


def test_cross_source_accepts_press_release(setup):
    cfg, conn, doc, fig = setup
    x = doc("RELIANCE", "Q1FY27", "xbrl", [])
    doc("RELIANCE", "Q1FY27", "results_release", ["OCR text without the figure"])
    doc("RELIANCE", "Q1FY27", "press_release", ["Net profit attributable to owners of Rs 20,946 crore"])
    fid = fig("RELIANCE", "Q1FY27", "pat_owners", 20946, doc_id=x)
    verify.run(conn, cfg, "RELIANCE", "Q1FY27")
    status, note = conn.execute("SELECT status, note FROM figures WHERE id = ?", (fid,)).fetchone()
    assert status == "verified" and "press release" in note


def test_cross_source_failure_is_low_confidence(setup):
    cfg, conn, doc, fig = setup
    x = doc("TITAN", "Q1FY27", "xbrl", [])
    doc("TITAN", "Q1FY27", "results_release", ["Sale of products 20,787 Other operating revenues 569"])
    fid = fig("TITAN", "Q1FY27", "revenue", 21356, doc_id=x)
    verify.run(conn, cfg, "TITAN", "Q1FY27")
    status, note = conn.execute("SELECT status, note FROM figures WHERE id = ?", (fid,)).fetchone()
    assert status == "low_confidence" and "cross-source" in note


def test_pdf_value_must_be_on_cited_page(setup):
    cfg, conn, doc, fig = setup
    p = doc("INFY", "Q1FY27", "results_release", ["Excluding trainees 84.9 83.0 85.2"])
    ok = fig("INFY", "Q1FY27", "infy_utilisation", "84.9", method="pdf", doc_id=p, original_value="84.9")
    bad = fig("INFY", "Q1FY27", "infy_attrition", "13.0", method="pdf", doc_id=p, original_value="13.0%")
    verify.run(conn, cfg, "INFY", "Q1FY27")
    st = dict(conn.execute("SELECT id, status FROM figures").fetchall())
    assert st[ok] == "verified" and st[bad] == "low_confidence"


def test_segment_sum_mismatch_marks_segments_low(setup):
    cfg, conn, doc, fig = setup
    x = doc("MM", "Q1FY27", "xbrl", [])
    doc("MM", "Q1FY27", "results_release", ["Revenue 1,000"])
    fig("MM", "Q1FY27", "revenue", 1000, doc_id=x)
    fig("MM", "Q1FY27", "segment_revenue_total", 1000, doc_id=x)
    fig("MM", "Q1FY27", "inter_segment_revenue", 10, doc_id=x)
    a = fig("MM", "Q1FY27", "segment_revenue", 700, segment="Automotive", doc_id=x)
    fig("MM", "Q1FY27", "segment_revenue", 200, segment="Farm Equipment", doc_id=x)   # 900 - 10 != 1000
    verify.run(conn, cfg, "MM", "Q1FY27")
    assert conn.execute("SELECT status FROM figures WHERE id = ?", (a,)).fetchone()[0] == "low_confidence"


def test_derived_inherits_low_confidence_from_inputs(setup):
    import json
    cfg, conn, doc, fig = setup
    x = doc("TITAN", "Q1FY27", "xbrl", [])
    doc("TITAN", "Q1FY27", "results_release", ["EBITDA 2,888"])
    rev = fig("TITAN", "Q1FY27", "revenue", 21356, doc_id=x)                      # not in release -> low
    e = fig("TITAN", "Q1FY27", "ebitda", 2888, doc_id=x)
    m = fig("TITAN", "Q1FY27", "ebitda_margin", "13.5232", method="derived", source_ref=None, source_detail=None,
            derivation=json.dumps({"formula": "ebitda / revenue * 100", "input_figures": {"ebitda": e, "revenue": rev}}))
    verify.run(conn, cfg, "TITAN", "Q1FY27")
    status, note = conn.execute("SELECT status, note FROM figures WHERE id = ?", (m,)).fetchone()
    assert status == "low_confidence" and "revenue" in note


def test_comparator_copy_preference_and_missing_estimate_gap(setup):
    cfg, conn, doc, fig = setup
    d27 = doc("INFY", "Q1FY27", "results_release", [])
    d26 = doc("INFY", "Q4FY26", "results_release", [])
    cur = fig("INFY", "Q1FY27", "infy_utilisation", "84.9", method="pdf", doc_id=d27, status="verified")
    fig("INFY", "Q1FY27", "infy_utilisation", "83.0", method="pdf", period="Q4FY26", doc_id=d27, status="verified")
    fig("INFY", "Q4FY26", "infy_utilisation", "82.0", method="pdf", doc_id=d26, status="verified")  # own-doc copy
    compare.run(conn, cfg, "INFY", "Q1FY27")
    rows = {r[0]: r[1:] for r in conn.execute(
        "SELECT k.comparator, g.value, k.change_bps, k.gap_reason FROM comparisons k"
        " LEFT JOIN figures g ON g.id = k.comparator_figure_id WHERE k.figure_id = ?", (cur,))}
    assert rows["prior"][0] == "83.0"                      # current document's copy wins
    assert rows["prior"][1] == "190.00"
    assert rows["estimate"][2] == "no estimate in the model"
    assert rows["year_ago"][2] == "no year-ago figure"


def test_annual_only_metrics_recorded_as_gaps(setup):
    cfg, conn, doc, fig = setup
    compare.run(conn, cfg, "MM", "Q1FY27")
    rows = conn.execute("SELECT metric, status, note FROM figures WHERE metric IN ('operating_cash_flow', 'capex')").fetchall()
    assert {r[0] for r in rows} == {"operating_cash_flow", "capex"}
    assert all(r[1] == "missing" and "full-year" in r[2] for r in rows)
