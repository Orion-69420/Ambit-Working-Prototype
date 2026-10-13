import pytest

from copilot import commentary, config, db


@pytest.fixture
def cfg():
    return config.load_all()


def speakers(ts):
    return [(t.speaker, t.role) for t in ts]


# ---------------------------------------------------------------- speaker turns

def test_colon_speakers_roster_and_header_lines(cfg):
    pages = [(1, "Sub: Transcript\nTITAN MANAGEMENT SPEAKERS:\nMR. AJOY CHAWLA\n"),
             (2, "Titan Company Limited\nAugust 07, 2026\nModerator: Welcome to the call.\n"
                 "Ajoy Chawla:\nWe expect jewellery growth to stay strong.\n"),
             (3, "Page 3 of 17\nDevanshu Bansal: What is the outlook for jewellery?\nArun Narayan: Thanks.")]
    ts = commentary.turns(pages, cfg, "TITAN")
    assert speakers(ts) == [("Moderator", "moderator"), ("Ajoy Chawla", "management"),
                            ("Devanshu Bansal", "analyst"), ("Arun Narayan", "management")]
    assert all("Titan Company Limited" not in text for t in ts for _, text in t.parts)


def test_reliance_explicit_roles(cfg):
    pages = [(3, "Sh V Srikanth 00:00:01 – 00:09:45 (Group Performance)\nO2C margins were strong.\n"
                 "Questioner (Manish Adukia, Goldman Sachs)\nWhat is the outlook?\n"
                 "Company Speaker (Anshuman Thakur)\nWe expect ARPU to rise.")]
    assert speakers(commentary.turns(pages, cfg, "RELIANCE")) == [
        ("V Srikanth", "management"), ("Manish Adukia", "analyst"), ("Anshuman Thakur", "management")]


def test_bare_name_speakers_need_to_be_known(cfg):
    pages = [(1, "Moderator\nThe next question is from the line of Kumar Rakesh from BNP Paribas.\n"
                 "Kumar Rakesh\nHow is the guidance?\nSalil Parekh\nOur guidance is 1.5% to 3%.\n"
                 "Thank You\nChief Financial Officer\n")]
    names = speakers(commentary.turns(pages, cfg, "INFY"))
    assert names == [("Moderator", "moderator"), ("Kumar Rakesh", "analyst"), ("Salil Parekh", "management")]


def test_sentences_keep_their_page(cfg):
    t = commentary.Turn("Salil Parekh", "management", [(6, "Revenue grew well. We expect"), (7, "margins to hold.")])
    ss = commentary.sentences(t)
    assert [(s.text, s.page) for s in ss] == [("Revenue grew well.", 6), ("We expect margins to hold.", 6)]
    t2 = commentary.Turn("X", "management", [(6, "Revenue grew well."), (7, "We expect margins to hold.")])
    assert [s.page for s in commentary.sentences(t2)] == [6, 7]


# ---------------------------------------------------------------- rules

def classify(cfg, text, role="management", company="INFY"):
    rx = commentary._compile(cfg, company)
    return commentary.classify(commentary.Sentence(text, 1, "S", role), rx)


def test_guidance_needs_management_phrase_and_topic(cfg):
    assert ("guidance", "cc_growth") in [(t, k) for t, k, _ in classify(
        cfg, "We are changing our revenue growth guidance to 1.5% to 3% in constant currency terms.")]
    assert not [x for x in classify(cfg, "We expect a good festive season.") if x[0] == "guidance"]    # no topic
    assert not classify(cfg, "Our margin guidance is 20% to 22%.", role="analyst")                   # not management


def test_questions_and_disclaimers_are_not_guidance(cfg):
    assert not classify(cfg, "Do you want to give a guidance on the margin?")
    assert not classify(cfg, "Certain statements on future revenue growth are forward-looking statements.")


def test_explanation(cfg):
    assert ("explanation", "margin") in [(t, k) for t, k, _ in classify(
        cfg, "Margins were lower due to wage hikes.")]


def test_negated_flags_are_skipped(cfg):
    assert not classify(cfg, "There is no qualified opinion from the auditors.")
    assert not classify(cfg, "I don't think we are going to have a penalty on diesel.")
    flags = [x for x in classify(cfg, "The auditor issued a qualified opinion on the subsidiary.") if x[0] == "flag"]
    assert flags and flags[0][1] == "auditor"
    assert [x for x in classify(cfg, "We received a show-cause notice from SEBI.", role="analyst") if x[0] == "flag"]


def test_moderator_sentences_are_ignored(cfg):
    assert not classify(cfg, "Our guidance on revenue growth remains.", role="moderator")


# ---------------------------------------------------------------- guidance table

def test_guidance_table_statuses(tmp_path):
    conn = db.init_db(tmp_path / "t.sqlite")
    for q in ("Q4FY26", "Q1FY27"):
        conn.execute("INSERT INTO documents (company, quarter, type, file_path, sha256, ingested_at)"
                     " VALUES ('INFY', ?, 'transcript', 'x', ?, ?)", (q, q, db.now()))

    def add(q, topic, quote):
        conn.execute("INSERT INTO statements (company, quarter, type, topic, quote, document_id, page, speaker,"
                     " rule_matched) VALUES ('INFY', ?, 'guidance', ?, ?, 1, 1, 'S', 'guidance')", (q, topic, quote))
    add("Q4FY26", "cc_growth", "Guidance is 1.5% to 3.5%.")
    add("Q1FY27", "cc_growth", "Guidance is now 1.5% to 3%.")
    add("Q4FY26", "deals", "We target large deals.")
    add("Q1FY27", "margin", "Margin guidance 20% to 22%.")
    tab = {t: s for t, s, _, _ in commentary.guidance_table(conn, "INFY", "Q1FY27")}
    assert tab == {"cc_growth": "repeated / updated", "deals": "not repeated", "margin": "new"}
