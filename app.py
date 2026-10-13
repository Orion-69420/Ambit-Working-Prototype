"""Review screen for the Change Reports (Step 10).

    streamlit run app.py

Pick a company and quarter, read the draft, open the source of any figure, review every item
(approve / reject / comment / correct), approve the report, and export it. All rules live in
copilot/report.py and copilot/review.py; this file only displays and calls them.
"""
import json

import pymupdf
import streamlit as st
from lxml import etree

from copilot import config, db, export, report, review

st.set_page_config(page_title="Change Report review", layout="wide")


@st.cache_resource
def cfg():
    return config.load_all()


def conn():
    c = db.connect()
    return c


@st.cache_data(show_spinner=False)
def page_image(path, page):
    with pymupdf.open(config.CONFIG.parent / path) as pdf:
        return pdf[page - 1].get_pixmap(dpi=110).tobytes("png")


def show_source(c, src, figure=None):
    if not src:
        st.caption("No source")
        return
    st.caption(src["text"])
    if src["kind"] == "pdf":
        doc = c.execute("SELECT file_path FROM documents WHERE id = ?", (src["document_id"],)).fetchone()
        st.image(page_image(doc["file_path"], src["page"]), caption=f"{doc['file_path']} – page {src['page']}")
        if src.get("detail"):
            st.caption(f"Located by: {src['detail']}")
    elif src["kind"] == "xbrl":
        doc = c.execute("SELECT file_path FROM documents WHERE id = ?", (src["document_id"],)).fetchone()
        root = etree.parse(str(config.CONFIG.parent / doc["file_path"])).getroot()
        element = src["element"].split(" [")[0]
        facts = [etree.tostring(e, encoding="unicode") for e in root
                 if isinstance(e.tag, str) and etree.QName(e).localname == element and e.get("contextRef") == src["context"]]
        ctx = [etree.tostring(e, encoding="unicode") for e in root.iter("{http://www.xbrl.org/2003/instance}context")
               if e.get("id") == src["context"]]
        st.code("\n".join(facts + ctx)[:3000], language="xml")
    elif src["kind"] == "derived" and figure:
        st.caption(f"Value {figure['value']}")


def review_form(c, company, quarter, key, reviewer, is_row=False, low=None):
    with st.form(f"form-{key}"):
        actions = ["approve", "reject", "comment"] + (["correct"] if is_row else [])
        action = st.radio("Action", actions, horizontal=True, key=f"a-{key}")
        hint = "Comment / reason" + (" (required: what you checked against the source)" if low else "")
        comment = st.text_input(hint, key=f"c-{key}")
        new_value = st.text_input("Corrected value (for 'correct')", key=f"v-{key}") if is_row else None
        if st.form_submit_button("Record"):
            try:
                review.record(c, cfg(), company, quarter, key, reviewer, action, comment, new_value)
                st.success(f"Recorded: {action}")
                st.rerun()
            except review.ReviewError as e:
                st.error(str(e))


def main():
    c = conn()
    companies = list(cfg().companies)
    with st.sidebar:
        st.header("Change Report review")
        company = st.selectbox("Company", companies, format_func=lambda x: cfg().companies[x]["name"])
        quarter = st.selectbox("Quarter", list(config.TARGET_QUARTERS))
        reviewer = st.text_input("Reviewer name", key="reviewer")
        st.caption("Reviewer identity is a name entered here, not a secure login (Phase 1).")

    rep = report.build(c, cfg(), company, quarter)
    st_ = report.status(c, cfg(), company, quarter, rep)
    content, latest = rep["content"], rep["reviews"]
    if st_.get("returned"):
        st.warning("An input changed after approval: the report is back in DRAFT.")

    with st.sidebar:
        st.metric("Status", st_["status"].upper())
        if st_["status"] == "approved":
            st.caption(f"Approved by {st_['approved_by']} at {st_['approved_at']}")
        done = sum(1 for i in rep["items"] if latest.get(i, {}).get("action") in report.DONE_ACTIONS)
        st.progress(done / max(1, len(rep["items"])), text=f"{done} of {len(rep['items'])} items reviewed")
        why = report.blockers(c, rep)
        for w in why:
            st.caption(f"• {w}")
        if st.button("Approve report", disabled=bool(why) or st_["status"] == "approved", type="primary"):
            try:
                report.approve(c, cfg(), company, quarter, reviewer)
                st.rerun()
            except report.ApprovalError as e:
                st.error(str(e))
        if st.button("Export Excel + PDF"):
            snap, files = export.export(c, cfg(), company, quarter, user=reviewer or None)
            st.success(f"Exported {snap['status'].upper()}: " + ", ".join(f.name for f in files))
            for f in files:
                st.download_button(f"Download {f.name}", f.read_bytes(), file_name=f.name, key=f"dl-{f.name}")

    st.title(f"{content['company_name']} – {content['quarter']}")
    st.caption(f"Basis: {content['basis']} · period {content['period'][0]} to {content['period'][1]} · "
               f"compared with {content['comparators']['prior']} and {content['comparators']['year_ago']}")
    if content["sample_estimates"]:
        st.error(report.SAMPLE_BANNER)
    for n in content["notes"]:
        st.info(n)

    st.subheader("Headline summary")
    for h in content["headline"] or [{"text": "No verified moves against estimate to report."}]:
        st.markdown(f"- {h['text']}")

    tabs = st.tabs(["Metrics", "Guidance", "Flags", "Gaps", "Sources"])
    sec = export.sections(rep | {"status": st_["status"]})
    with tabs[0]:
        st.dataframe([dict(zip(sec["metric_head"], r)) for r in sec["metrics"]], width='stretch', hide_index=True)
        for r, cells in zip(content["rows"], sec["metrics"]):
            low = report.low_confidence(r, company)
            mark = latest.get(r["key"], {}).get("action")
            title = f"{'✅' if mark in report.DONE_ACTIONS else '⬜'} {cells[0]} – {cells[1]}" + (" ⚠ low confidence" if low else "")
            with st.expander(title):
                cols = st.columns(2)
                with cols[0]:
                    st.markdown("**Reported**")
                    show_source(c, (r["current"] or {}).get("source"), r["current"])
                    if r["current"] and r["current"]["note"]:
                        st.caption(f"Note: {r['current']['note']}")
                with cols[1]:
                    for k, cmp_ in r["comparisons"].items():
                        st.markdown(f"**{k.replace('_', '-')}**: {report.fmt_value(cmp_['value'], r['unit'])} → "
                                    f"{report.fmt_change(cmp_)} {cmp_.get('severity') or ''}")
                        if cmp_.get("estimate"):
                            e = cmp_["estimate"]
                            st.caption(f"Analyst model {e['sheet']}!{e['cell']}" + (" (SAMPLE)" if e["sample"] else ""))
                        elif cmp_.get("figure"):
                            st.caption((cmp_["figure"]["source"] or {}).get("text", ""))
                for lbl, f, _ in low:
                    st.warning(f"{lbl} {f['period']}: {f['note']}")
                for h in latest.get(r["key"], {}).get("comments", []):
                    st.caption(f"💬 {h['reviewer']}: {h['comment']}")
                if mark:
                    st.caption(f"Last action: {mark} by {latest[r['key']]['reviewer']}")
                review_form(c, company, quarter, r["key"], reviewer, is_row=True, low=low)

    with tabs[1]:
        for g in content["guidance"]:
            st.markdown(f"#### {g['topic'].replace('_', ' ')} — {g['status']}")
            for s in g["prior"]:
                st.caption(f"Prior quarter: “{s['quote']}” ({s['speaker']}, p. {s['page']})")
        st.markdown("---")
        st.markdown("**Review every guidance candidate for this quarter**")
        for s in report._statements(c, company, quarter, "guidance"):
            mark = latest.get(s["key"], {}).get("action")
            with st.expander(f"{'✅' if mark in report.DONE_ACTIONS else '⬜'} [{s['topic']}] {s['quote'][:110]}"):
                st.write(f"“{s['quote']}” — {s['speaker']}, page {s['page']} (rule: {s['rule_matched']})")
                review_form(c, company, quarter, s["key"], reviewer)

    with tabs[2]:
        if not content["flags"]:
            st.success("No governance or accounting flags found in the transcript.")
        for f in content["flags"]:
            mark = latest.get(f["key"], {}).get("action")
            with st.expander(f"{'✅' if mark in report.DONE_ACTIONS else '⬜'} [{f['category']}] {f['quote'][:110]}"):
                st.write(f"“{f['quote']}” — {f['speaker']}, page {f['page']} · {f['label']}")
                review_form(c, company, quarter, f["key"], reviewer)

    with tabs[3]:
        st.dataframe([dict(zip(sec["gaps_head"], g)) for g in sec["gaps"]], width='stretch', hide_index=True)
    with tabs[4]:
        st.dataframe([dict(zip(sec["sources_head"], s)) for s in sec["sources"]], width='stretch', hide_index=True)


main()
