"""First Look · run with streamlit run streamlit_app.py."""

import streamlit as st

from firstlook import __version__
from firstlook.judgments import POLICY_VERSION
from firstlook.analytical_tasks import TASK_POLICY
from firstlook.ui.runtime import poll_job, settings, workspace
from firstlook.visualization import compiler as chart_compiler

st.set_page_config(
    page_title="First Look · discover, challenge, preserve",
    page_icon=":material/query_stats:",
    layout="wide",
    initial_sidebar_state=240,
)
ws, cfg = workspace(), settings()
st.logo(
    "static/wordmark-dark.svg" if st.context.theme.type == "dark" else "static/wordmark.svg",
    icon_image="static/mark.png",
    size="medium",
)
pages = {
    "Prepare": [
        st.Page(
            "app_pages/understand.py",
            title="Understand",
            icon=":material/table_chart:",
            default=True,
            help="Open a table, inspect its fields and set the direction for your first investigation.",
        ),
        st.Page(
            "app_pages/meaning.py",
            title="Meaning",
            icon=":material/schema:",
            help="Define quantities, entities, metrics and time policies that every analysis can reuse.",
        ),
    ],
    "Investigate": [
        st.Page(
            "app_pages/explore.py",
            title="Explore",
            icon=":material/explore:",
            help="Examine distributions, categories, relationships and time from complementary perspectives.",
        ),
        st.Page(
            "app_pages/discover.py",
            title="Findings",
            icon=":material/query_stats:",
            help="Browse computed observations, ask a question and inspect the evidence behind a finding.",
        ),
        st.Page(
            "app_pages/inspect.py",
            title="Inspect finding",
            icon=":material/open_in_full:",
            visibility="hidden",
        ),
        st.Page(
            "app_pages/compare.py",
            title="Compare",
            icon=":material/compare_arrows:",
            help="Keep a selected cohort beside its reference and compare their recorded populations.",
        ),
        st.Page(
            "app_pages/models.py",
            title="Models",
            icon=":material/model_training:",
            help="Evaluate a prediction task and inspect performance on the same held-out observations.",
        ),
        st.Page(
            "app_pages/text_lab.py",
            title="Text lab",
            icon=":material/text_snippet:",
            help="Turn selected text into frozen, reviewable model-coded features and compare their predictive contribution.",
        ),
        st.Page(
            "app_pages/event_lab.py",
            title="Event lab",
            icon=":material/event_repeat:",
            help="Build past-only features and complete future outcomes from one recorded event table, then inspect a fixed temporal holdout.",
        ),
        st.Page(
            "app_pages/challenge.py",
            title="Challenge",
            icon=":material/fact_check:",
            help="Check how a finding changes under a declared alternative, with both views together.",
        ),
    ],
    "Preserve": [
        st.Page(
            "app_pages/evidence.py",
            title="Evidence",
            icon=":material/bookmarks:",
            help="Annotate saved findings, revisit comparisons and export a reproducible investigation.",
        ),
        st.Page(
            "app_pages/judgments.py",
            title="Judgments",
            icon=":material/fact_check:",
            help="Inspect question definitions, probability distributions, ranking reasons and recorded model decisions.",
        ),
    ],
}
navigation = st.navigation(pages)
with st.sidebar:
    if ws.dataset:
        st.caption("Current dataset")
        st.markdown(f"**{ws.dataset.record.name}**")
        active = len(ws.context().row_ids) if not ws.dataset.frame.empty else ws.dataset.record.rows
        st.caption(f"{active:,} / {ws.dataset.record.rows:,} rows · {ws.dataset.record.columns} fields")
        if ws.focus:
            st.caption("Focus: " + ws.dataset.label(ws.focus))
        st.page_link(
            "app_pages/evidence.py",
            label=f"{len(ws.pins)} pinned · {len(ws.comparisons)} comparisons",
            icon=":material/bookmarks:",
        )
    ready = [n for n in ("jev", "tabpfn", "terra") if cfg.available(n)]
    st.caption("Model connections")
    st.caption("Configured: " + ", ".join(ready) if ready else "Local analysis · no API keys needed")
    if ready:
        st.caption(
            "External analysis "
            + (
                "permitted for this dataset"
                if st.session_state.get("external_ok")
                else "off for this dataset"
            )
        )
    with st.expander("About this workbench"):
        st.caption("Task policy: " + TASK_POLICY)
        st.caption(
            "An open-source exploration utility. Descriptive patterns and predictive diagnostics do not establish causality."
        )
        st.caption(
            "Jev prioritizes eligible choices. TabPFN supplies hosted predictions. Terra proposes and connects questions."
        )
        st.caption(
            "Local work makes no provider calls. External analysis requires your explicit dataset permission."
        )
        st.caption(f"First Look {__version__} · Apache-2.0")
        st.caption("Judgment policy: " + POLICY_VERSION)
        st.caption(
            "Chart renderer: " + getattr(chart_compiler, "RENDERER_VERSION", "older module — reboot required")
        )
if ws.message:
    st.toast(ws.message)
    ws.message = ""
poll_job()
navigation.run()
