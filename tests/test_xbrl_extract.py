import json
from decimal import Decimal

import pytest

from copilot import config, db, derive, xbrl_extract

Q = "Q1FY27"   # 2026-04-01 .. 2026-06-30


def xbrl(facts, contexts=None, prefix="in-capmkt", basis="Consolidated"):
    """Build a minimal SEBI-style XBRL instance. facts: (element, context, value or None for nil)."""
    contexts = contexts or {}
    ctx = {
        "OneD": ("<xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>", ""),
        "YTD": ("<xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>", ""),
        "OneI": ("<xbrli:instant>2026-06-30</xbrli:instant>", ""),
    } | contexts
    body = "".join(
        f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>'
        + (f"<xbrli:segment>{seg}</xbrli:segment>" if seg else "")
        + f"</xbrli:entity><xbrli:period>{per}</xbrli:period></xbrli:context>"
        for cid, (per, seg) in ctx.items())
    body += f'<{prefix}:NatureOfReportStandaloneConsolidated contextRef="OneD">{basis}</{prefix}:NatureOfReportStandaloneConsolidated>'
    for el, cid, val in facts:
        if val is None:
            body += f'<{prefix}:{el} contextRef="{cid}" unitRef="INR" xsi:nil="true"/>'
        else:
            body += f'<{prefix}:{el} contextRef="{cid}" unitRef="INR" decimals="-5">{val}</{prefix}:{el}>'
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" '
            f'xmlns:{prefix}="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt" '
            'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' + body + "</xbrli:xbrl>")


def seg_ctx(n, axis="ReportableSegmentsAxis", prefix="in-capmkt"):
    return ("<xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate>",
            f'<xbrldi:explicitMember dimension="{prefix}:{axis}">{prefix}:ReportableSegments{n}Member</xbrldi:explicitMember>')


CORE = [("RevenueFromOperations", "OneD", "100000000000"),      # 10,000 crore
        ("ProfitBeforeExceptionalItemsAndTax", "OneD", "15000000000"),
        ("FinanceCosts", "OneD", "1000000000"),
        ("DepreciationDepletionAndAmortisationExpense", "OneD", "2000000000"),
        ("OtherIncome", "OneD", "500000000"),
        ("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod", "OneD", "300000000"),
        ("ProfitOrLossAttributableToOwnersOfParent", "OneD", "11000000000"),
        ("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "OneD", "12.5")]


@pytest.fixture
def cfg():
    return config.load_all()


def write(tmp_path, text):
    p = tmp_path / "x.xml"
    p.write_text(text, encoding="utf8")
    return p


def by_metric(figs):
    return {f["metric"]: f for f in figs if f["segment"] is None}


def test_core_figures_scaled_to_crore_and_sourced(cfg, tmp_path):
    figs = by_metric(xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(CORE))))
    assert figs["revenue"]["value"] == Decimal("10000")
    assert figs["revenue"]["source_detail"] == "RevenueFromOperations"
    assert figs["revenue"]["source_ref"] == "OneD"
    assert figs["revenue"]["original_value"] == "100000000000"
    assert figs["basic_eps"]["value"] == Decimal("12.5")


def test_ebitda_excludes_associates_and_records_derivation(cfg, tmp_path):
    figs = by_metric(xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(CORE))))
    # 1500 + 100 + 200 - 50 - 30 = 1720 crore; margin 17.2%
    assert figs["ebitda"]["value"] == Decimal("1720.0000")
    assert figs["ebitda_margin"]["value"] == Decimal("17.2000")
    d = json.loads(figs["ebitda"]["derivation"])
    assert d["formula"].endswith("- associates_share") and d["inputs"]["associates_share"] == "30"


def test_year_to_date_context_is_ignored(cfg, tmp_path):
    facts = [f for f in CORE if f[0] != "RevenueFromOperations"] + [("RevenueFromOperations", "YTD", "999")]
    figs = by_metric(xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(facts))))
    assert figs["revenue"]["status"] == "missing" and figs["revenue"]["value"] is None
    assert figs["ebitda_margin"]["status"] == "missing"     # derived from a missing input


def test_nil_fact_is_missing_not_zero(cfg, tmp_path):
    facts = [f for f in CORE if f[0] != "OtherIncome"] + [("OtherIncome", "OneD", None)]
    figs = by_metric(xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(facts))))
    assert figs["other_income"]["status"] == "missing" and figs["other_income"]["value"] is None
    assert figs["ebitda"]["status"] == "missing" and "other_income" in figs["ebitda"]["note"]


def test_namespace_prefix_does_not_matter(cfg, tmp_path):
    figs = by_metric(xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(CORE, prefix="sebi"))))
    assert figs["revenue"]["value"] == Decimal("10000")


def test_wrong_basis_stops_extraction(cfg, tmp_path):
    with pytest.raises(xbrl_extract.ExtractError, match="basis"):
        xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(CORE, basis="Standalone")))


def test_segments_matched_by_label_not_position(cfg, tmp_path):
    ctxs = {"S1": seg_ctx(1), "S2": seg_ctx(2)}
    facts = CORE + [("DescriptionOfReportableSegment", "S1", "Farm Equipment"),
                    ("DescriptionOfReportableSegment", "S2", "Automotive"),
                    ("SegmentRevenue", "S1", "20000000000"), ("SegmentRevenue", "S2", "80000000000")]
    figs = xbrl_extract.extract(cfg, "MM", Q, write(tmp_path, xbrl(facts, ctxs)))
    seg = {f["segment"]: f["value"] for f in figs if f["metric"] == "segment_revenue"}
    assert seg == {"Farm Equipment": Decimal("2000"), "Automotive": Decimal("8000")}


def test_segment_alias_maps_renamed_segment(cfg, tmp_path):
    ctxs = {"S1": seg_ctx(1)}
    facts = CORE + [("DescriptionOfReportableSegment", "S1", "Watches and Wearables"),
                    ("SegmentRevenue", "S1", "11340000000")]
    figs = xbrl_extract.extract(cfg, "TITAN", Q, write(tmp_path, xbrl(facts, ctxs)))
    assert [f["segment"] for f in figs if f["metric"] == "segment_revenue"] == ["Watches"]


def test_unknown_segment_label_stops_extraction(cfg, tmp_path):
    ctxs = {"S1": seg_ctx(1)}
    facts = CORE + [("DescriptionOfReportableSegment", "S1", "Space Tourism"), ("SegmentRevenue", "S1", "1")]
    with pytest.raises(xbrl_extract.ExtractError, match="Space Tourism"):
        xbrl_extract.extract(cfg, "MM", Q, write(tmp_path, xbrl(facts, ctxs)))


def test_store_replaces_previous_run_and_refuses_after_correction(cfg, tmp_path):
    conn = db.init_db(tmp_path / "t.sqlite")
    figs = xbrl_extract.extract(cfg, "ASIANPAINT", Q, write(tmp_path, xbrl(CORE)))
    xbrl_extract.store(conn, "ASIANPAINT", Q, None, figs)
    xbrl_extract.store(conn, "ASIANPAINT", Q, None, figs)
    n = conn.execute("SELECT count(*) FROM figures").fetchone()[0]
    assert n == len(figs)
    rev = conn.execute("SELECT id FROM figures WHERE metric = 'revenue'").fetchone()[0]
    conn.execute("INSERT INTO figures (company, quarter, metric, period, basis, value, unit, method, status,"
                 " supersedes, reason, created_at) VALUES ('ASIANPAINT', ?, 'revenue', ?, 'consolidated', '1',"
                 " 'inr_crore', 'manual', 'manually_verified', ?, 'typo in filing', ?)", (Q, Q, rev, db.now()))
    with pytest.raises(xbrl_extract.ExtractError, match="corrections"):
        xbrl_extract.store(conn, "ASIANPAINT", Q, None, figs)


def test_derive_is_exact_and_safe():
    assert derive.evaluate("a / b * 100", {"a": Decimal("1"), "b": Decimal("3")}) == Decimal("33.3333")
    assert derive.evaluate("a + b", {"a": Decimal("0.1"), "b": Decimal("0.2")}) == Decimal("0.3000")
    assert derive.evaluate("a + b", {"a": Decimal("1"), "b": None}) is None
    with pytest.raises(derive.DeriveError):
        derive.evaluate("a / b", {"a": Decimal("1"), "b": Decimal("0")})
    with pytest.raises(derive.DeriveError):
        derive.evaluate("__import__('os')", {})


def test_quarters_needed_includes_comparators():
    assert config.quarters_needed("Q1FY27") == ["Q1FY27", "Q4FY26", "Q1FY26"]
    assert config.quarters_needed("Q3FY26") == ["Q3FY26"]
