"""First Look · run with streamlit run streamlit_app.py."""

import streamlit as st

from firstlook.ui.runtime import poll_job, settings, workspace

st.set_page_config(
    page_title="First Look · discover, challenge, preserve", page_icon=":material/query_stats:", layout="wide"
)
ws, cfg = workspace(), settings()
st.logo("static/mark.png", icon_image="static/mark.png", size="small")
with st.sidebar:
    st.markdown("## First Look")
    st.caption("Discover. Challenge. Preserve.")
pages = {
    "Prepare": [
        st.Page("app_pages/understand.py", title="Understand", icon=":material/table_chart:", default=True),
        st.Page("app_pages/meaning.py", title="Meaning", icon=":material/schema:"),
    ],
    "Investigate": [
        st.Page("app_pages/explore.py", title="Explore", icon=":material/explore:"),
        st.Page("app_pages/discover.py", title="Findings", icon=":material/query_stats:"),
        st.Page("app_pages/compare.py", title="Compare", icon=":material/compare_arrows:"),
        st.Page("app_pages/models.py", title="Models", icon=":material/model_training:"),
        st.Page("app_pages/challenge.py", title="Challenge", icon=":material/compare_arrows:"),
    ],
    "Preserve": [
        st.Page("app_pages/evidence.py", title="Evidence", icon=":material/bookmarks:"),
    ],
}
navigation = st.navigation(pages)
with st.sidebar:
    if ws.dataset:
        st.space("small")
        st.caption("CURRENT DATASET")
        st.markdown(f"**{ws.dataset.record.name}**")
        st.caption(f"{ws.dataset.record.rows:,} rows · {ws.dataset.record.columns} fields")
        if ws.focus:
            st.caption("Focus: " + ws.dataset.label(ws.focus))
        st.caption(f"{len(ws.pins)} pinned observations")
    st.space("medium")
    ready = [n for n in ("jev", "tabpfn", "terra") if cfg.available(n)]
    st.caption("MODEL CONNECTIONS")
    st.caption("Configured: " + ", ".join(ready) if ready else "Local analysis · API keys not configured")
    with st.expander("About this workbench"):
        st.caption(
            "An open-source exploration utility. Descriptive patterns and predictive diagnostics do not establish causality."
        )
        st.caption(
            "Jev prioritizes eligible choices. TabPFN supplies hosted predictions. Terra proposes and connects questions."
        )
        st.caption(
            "Local work makes no provider calls. External analysis requires your explicit dataset permission."
        )
        st.caption("First Look 0.3 · Apache-2.0")
if ws.message:
    st.toast(ws.message)
    ws.message = ""
poll_job()
navigation.run()
