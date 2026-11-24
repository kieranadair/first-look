"""A focused native route keeps inspection anchored at the top of the page."""

import streamlit as st

from firstlook.state import pin
from firstlook.ui.components import evidence_inspector, page_header, render_chart
from firstlook.ui.runtime import workspace

ws = workspace()
page_header("Inspect finding", "Keep the picture, its definition and its limits in view.", compact=True)
if ws.dataset is None:
    st.info("Open a dataset, then choose Inspect on a finding.")
    st.page_link("app_pages/understand.py", label="Open a dataset", icon=":material/table_chart:")
    st.stop()

inv = ws.investigation
inspected = next((f for f in inv.findings if f.id == ws.inspect_id), None) if inv else None
if inv is None or inspected is None:
    st.caption("Choose a finding to inspect in the current investigation.")
    st.page_link("app_pages/discover.py", label="Browse findings", icon=":material/query_stats:")
    st.stop()

with st.container(horizontal=True, gap="small"):
    if st.button("Back to findings", key="close_inspection", icon=":material/arrow_back:"):
        ws.inspect_id = None
        st.switch_page("app_pages/discover.py")
    if st.button("Challenge this finding", key="inspect_challenge", icon=":material/fact_check:"):
        ws.challenge_id = inspected.id
        st.switch_page("app_pages/challenge.py")
    pinned = any(p["finding"]["id"] == inspected.id for p in ws.pins)
    if st.button(
        "Pinned" if pinned else "Pin finding",
        key="inspect_pin",
        icon=":material/bookmark:",
        disabled=pinned,
    ):
        pin(ws, inspected.id)
        st.toast("Finding and completed checks added to Evidence.")
        st.rerun()
st.subheader(inspected.title)
st.markdown(inspected.observation)
chart, evidence = st.columns([1.6, 1], gap="medium")
with chart:
    compiled = render_chart(inspected, inv, suffix="inspection", selection=not ws.replay, height=320)
    if not ws.replay and any(compiled.row_map.values()):
        st.caption(
            "Select marks to compare a cohort, or apply a selection to begin a filtered investigation."
        )
with evidence:
    evidence_inspector(inspected, inv, compact=True)
