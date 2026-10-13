from decimal import Decimal

import pymupdf
import pytest

from copilot import pdf_extract as pe


def make_pdf(tmp_path, items, name="t.pdf", size=(960, 540)):
    """items: (x, y, text) placed on one page."""
    pdf = pymupdf.open()
    page = pdf.new_page(width=size[0], height=size[1])
    for x, y, text in items:
        page.insert_text((x, y), text, fontsize=10)
    path = tmp_path / name
    pdf.save(path)
    return path


# ---------------------------------------------------------------- number parsing

@pytest.mark.parametrize("text, value, approx", [
    ("1,240.10", Decimal("1240.10"), False),
    ("2,69,496", Decimal("269496"), False),          # Indian grouping
    ("(35.2)", Decimal("-35.2"), False),             # brackets mean negative
    ("-0.5%", Decimal("-0.5"), False),
    ("c.33%", Decimal("33"), True),
    ("~1.8%", Decimal("1.8"), True),
    ("₹ 215.6", Decimal("215.6"), False),
])
def test_parse_number(text, value, approx):
    assert pe.parse_number(text) == (value, approx)


@pytest.mark.parametrize("text", ["–", "-", "nil", ""])
def test_dash_and_blank_are_missing_not_zero(text):
    assert pe.parse_number(text)[0] is None


def test_quarter_from_date_and_label():
    assert pe.quarter_from_date("Jun", "2026") == "Q1FY27"
    assert pe.quarter_from_date("Mar", "2026") == "Q4FY26"
    assert pe.quarter_from_date("December", "2025") == "Q3FY26"
    assert pe.quarter_from_label("4", "26") == "Q4FY26"


# ---------------------------------------------------------------- rule kinds

def test_grid_ignores_commentary_that_mentions_the_metric(tmp_path):
    path = make_pdf(tmp_path, [
        (30, 30, "Key Operating Metrics"),
        (350, 100, "Q1"), (350, 112, "FY26"), (430, 100, "Q4"), (430, 112, "FY26"), (510, 100, "Q1"), (510, 112, "FY27"),
        (600, 140, "Rs 7 YoY increase in ARPU driven by mix"),     # commentary, above the row
        (30, 150, "ARPU"), (240, 150, "Rs / month"), (350, 150, "208.8"), (430, 150, "214.0"), (510, 150, "215.6"),
    ])
    rule = dict(kind="grid", page_anchors=["Key Operating Metrics"], row=["ARPU"], columns="quarter",
                value_pattern=r"^\d+(\.\d+)?$")
    page, found = pe.apply(rule, path, "Q1FY27")
    assert {q: r["value"] for q, r in found.items()} == {
        "Q1FY26": Decimal("208.8"), "Q4FY26": Decimal("214.0"), "Q1FY27": Decimal("215.6")}


def test_grid_takes_matched_row_when_same_number_appears_elsewhere(tmp_path):
    path = make_pdf(tmp_path, [
        (30, 30, "Effort & Utilization"),
        (390, 60, "Jun 30, 2026"), (460, 60, "Mar 31, 2026"), (530, 60, "Jun 30, 2025"),
        (40, 80, "Utilization"),
        (45, 95, "Including trainees"), (400, 95, "84.9"), (470, 95, "79.7"), (540, 95, "82.7"),
        (45, 110, "Excluding trainees"), (400, 110, "84.9"), (470, 110, "83.0"), (540, 110, "85.2"),
    ], size=(612, 792))
    rule = dict(kind="grid", page_anchors=["Effort & Utilization"], row=["Utilization", "Excluding trainees"],
                columns="date", value_pattern=r"^\d+(\.\d+)?$")
    _, found = pe.apply(rule, path, "Q1FY27")
    assert {q: r["value"] for q, r in found.items()} == {
        "Q1FY27": Decimal("84.9"), "Q4FY26": Decimal("83.0"), "Q1FY26": Decimal("85.2")}
    assert "Excluding trainees" in found["Q4FY26"]["detail"]


def test_chart_reads_value_above_each_quarter_and_skips_annotations(tmp_path):
    path = make_pdf(tmp_path, [
        (30, 30, "Gross Margin Trend"),
        (100, 120, "~1.8%"), (100, 200, "44.9%"), (200, 210, "43.2%"), (300, 190, "45.6%"),
        (90, 400, "Q4 FY25"), (190, 400, "Q1"), (210, 400, "FY26"), (290, 400, "Q4FY26"),
    ])
    rule = dict(kind="chart", page_anchors=["Gross Margin Trend"], value_pattern=r"^\d{2}(\.\d+)?%$")
    _, found = pe.apply(rule, path, "Q4FY26")
    assert {q: r["value"] for q, r in found.items()} == {
        "Q4FY25": Decimal("44.9"), "Q1FY26": Decimal("43.2"), "Q4FY26": Decimal("45.6")}


def test_chart_region_separates_side_by_side_charts(tmp_path):
    path = make_pdf(tmp_path, [
        (30, 30, "MARKET LEADERSHIP IN SUV"),
        (100, 200, "174.7"), (95, 300, "Q1F27"),           # left chart
        (600, 200, "25.0%"), (595, 300, "Q1F27"),          # right chart
    ])
    left = dict(kind="chart", page_anchors=["MARKET LEADERSHIP"], region=[0, 0.5], value_pattern=r"^\d+(\.\d+)?$")
    right = dict(kind="chart", page_anchors=["MARKET LEADERSHIP"], region=[0.5, 1], value_pattern=r"^\d+(\.\d+)?%$")
    assert pe.apply(left, path, "Q1FY27")[1]["Q1FY27"]["value"] == Decimal("174.7")
    assert pe.apply(right, path, "Q1FY27")[1]["Q1FY27"]["value"] == Decimal("25.0")


def test_labelled_takes_first_block_when_captions_repeat(tmp_path):
    path = make_pdf(tmp_path, [
        (30, 30, "Jewellery Secondary YoY Growth"),
        (650, 110, "Tanishq"), (730, 120, "36%"), (845, 120, "32%"), (730, 140, "Overall"), (845, 140, "Like to like"),
        (650, 200, "CaratLane"), (730, 210, "35%"), (845, 210, "23%"), (730, 230, "Overall"), (845, 230, "Like to like"),
    ])
    rule = dict(kind="labelled", page_anchors=["Secondary", "Overall"], label="Like to like", occurrence=1,
                value_pattern=r"^\d+(\.\d+)?%$")
    assert pe.apply(rule, path, "Q3FY26")[1] == {"Q3FY26": pytest.approx(
        {"value": Decimal("32"), "approx": False, "printed": "32%", "detail": "Like to like (above caption)"})}


def test_text_rule_and_approximate_flag(tmp_path):
    path = make_pdf(tmp_path, [(30, 30, "Fact Sheet"), (30, 60, "2.6% QoQ 2.4% YoY CC Growth")])
    rule = dict(kind="text", page_anchors=["Fact Sheet"], pattern=r"(?P<value>\d+(?:\.\d+)?)%\s*(?:Q4\s*)?YoY\s*CC Growth")
    assert pe.apply(rule, path, "Q1FY27")[1]["Q1FY27"]["value"] == Decimal("2.4")


def test_missing_anchor_and_scanned_document_raise(tmp_path):
    path = make_pdf(tmp_path, [(30, 30, "A page of ordinary text about something unrelated entirely")])
    with pytest.raises(pe.RuleError, match="no page contains"):
        pe.apply(dict(kind="text", page_anchors=["Fact Sheet"], pattern="(?P<value>1)"), path, "Q1FY27")
    blank = pymupdf.open()
    for _ in range(3):
        blank.new_page()
    blank.save(tmp_path / "scan.pdf")
    with pytest.raises(pe.RuleError, match="scanned image"):
        pe.apply(dict(kind="text", page_anchors=["Fact Sheet"], pattern="(?P<value>1)"), tmp_path / "scan.pdf", "Q1FY27")
