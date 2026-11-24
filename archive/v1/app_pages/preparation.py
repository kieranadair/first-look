"""Progressive automatic understanding, focused review and portable meanings."""

import streamlit as st

from firstlook.ui.components import page_header
from firstlook.ui.preparation import context_input, current_draft, review_bundle, template_controls
from firstlook.ui.runtime import workspace

ws = workspace()
page_header(
    "Preparation",
    "Let the app assemble an understanding. Review the decisions that change your analysis, then explore.",
    compact=True,
)
if not ws.dataset:
    st.page_link("app_pages/understand.py", label="Open a dataset", icon=":material/table_chart:")
    st.stop()
if ws.replay:
    st.caption(
        "This preparation is recorded evidence. Its definitions and provider records are available in Evidence; replay makes no provider calls."
    )
    if ws.preparation:
        st.json(ws.preparation)
    st.stop()
current_draft(ws)
mode = (
    st.segmented_control(
        "Preparation work area",
        ["Review", "Context & documents", "Reuse & record"],
        default="Review",
        key="preparation_mode",
        persist_state="session",
    )
    or "Review"
)
if mode == "Review":
    review_bundle(ws)
elif mode == "Context & documents":
    context_input(ws)
else:
    template_controls(ws)
