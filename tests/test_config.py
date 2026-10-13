import pathlib
import shutil

import pytest
import yaml
from lxml import etree

from copilot import config

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def cfg_dir(tmp_path):
    """A writable copy of the real config."""
    shutil.copytree(config.CONFIG, tmp_path, dirs_exist_ok=True)
    return tmp_path


def edit_metrics(d, fn):
    p = d / "metrics.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf8"))
    fn(doc["metrics"], doc)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf8")


def problems(d):
    with pytest.raises(config.ConfigError) as e:
        config.load_all(d)
    return "\n".join(e.value.problems)


def test_real_config_is_valid():
    cfg = config.load_all()
    for m in cfg.metrics.values():
        if m["type"] != "input":
            assert m["definition"] and m["unit"] and m["period"] and m["threshold_group"]


def test_unknown_unit_stops_the_run(cfg_dir):
    edit_metrics(cfg_dir, lambda ms, _: ms[0].update(unit="rupees"))
    assert "unknown unit 'rupees'" in problems(cfg_dir)


def test_duplicate_id_stops_the_run(cfg_dir):
    edit_metrics(cfg_dir, lambda ms, _: ms.append(dict(ms[0])))
    assert "duplicate metrics.yaml metric id: revenue" in problems(cfg_dir)


def test_undefined_input_stops_the_run(cfg_dir):
    def bad(ms, _):
        m = next(m for m in ms if m["id"] == "ebitda_margin")
        m.update(inputs=["ebitda", "sales"], formula="ebitda / sales * 100")
    edit_metrics(cfg_dir, bad)
    assert "input 'sales' is not a defined metric" in problems(cfg_dir)


def test_threshold_unit_must_match_change_unit(cfg_dir):
    edit_metrics(cfg_dir, lambda ms, _: next(m for m in ms if m["id"] == "ebitda_margin").update(change_as="pct"))
    assert "threshold_group margins is in bps" in problems(cfg_dir)


def test_per_segment_metric_rejects_single_segment_company(cfg_dir):
    edit_metrics(cfg_dir, lambda ms, _: next(m for m in ms if m["id"] == "segment_revenue")["applies_to"].append("ASIANPAINT"))
    assert "single-segment company ASIANPAINT" in problems(cfg_dir)


def test_all_problems_reported_together(cfg_dir):
    def bad(ms, _):
        ms[0]["unit"] = "rupees"
        ms.append(dict(ms[1]))
    edit_metrics(cfg_dir, bad)
    out = problems(cfg_dir)
    assert "unknown unit" in out and "duplicate" in out


@pytest.mark.skipif(not any(DATA.glob("*/*/xbrl.xml")), reason="source documents not collected")
def test_xbrl_elements_exist_in_the_filings():
    """Every XBRL element in the dictionary appears in that company's filings."""
    cfg = config.load_all()
    names = {}
    for f in DATA.glob("*/*/xbrl.xml"):
        root = etree.parse(str(f)).getroot()
        names.setdefault(f.parts[-3], set()).update(
            etree.QName(e).localname for e in root if isinstance(e.tag, str))
    for m in cfg.metrics.values():
        for el in m["sources"].get("xbrl", []):
            companies = cfg.companies if m["applies_to"] == "all" else m["applies_to"]
            for c in companies:
                assert el in names[c], f"{m['id']}: {el} not in any {c} filing"


@pytest.mark.skipif(not any(DATA.glob("*/*/xbrl.xml")), reason="source documents not collected")
def test_every_segment_label_is_known():
    cfg = config.load_all()
    for f in DATA.glob("*/*/xbrl.xml"):
        co = f.parts[-3]
        known = {l for labels in cfg.companies[co]["segments"].values() for l in labels}
        root = etree.parse(str(f)).getroot()
        labels = {e.text for e in root if isinstance(e.tag, str)
                  and etree.QName(e).localname == "DescriptionOfReportableSegment"}
        assert labels <= known, f"{f}: unknown segment labels {labels - known}"
