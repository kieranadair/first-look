"""A readable shortlist, with focused inspection one step away."""

import streamlit as st

from firstlook.modeling import suggested_model_plan
from firstlook.ui.components import finding_card, page_header, prepared_question_panel, claim_review_panel
from firstlook.ui.runtime import settings, start_analysis, start_question, workspace

ws, cfg = workspace(), settings()
page_header(
    "Findings", "Follow a promising observation. Inspect its evidence, compare it, then challenge it."
)
if ws.dataset is None:
    st.info("Choose an example or open your dataset in Understand.")
    if st.button("Open a dataset", type="primary"):
        st.switch_page("app_pages/understand.py")
    st.stop()

inv, ds = ws.investigation, ws.dataset

connected = any(cfg.available(provider) for provider in ("jev", "terra", "tabpfn"))
external_allowed = bool(st.session_state.get("external_ok", False))
toolbar = st.container(horizontal=True, vertical_alignment="center", gap="small")
with toolbar:
    if inv:
        view = (
            st.segmented_control(
                "Findings to browse",
                ["Overview", "Relationships"],
                default="Overview",
                key="discover_view",
                persist_state="session",
                label_visibility="collapsed",
                width="content",
            )
            or "Overview"
        )
        options = st.popover("Investigation options", icon=":material/tune:", on_change="rerun")
        st.page_link("app_pages/explore.py", label="Explore another angle", icon=":material/explore:")
    else:
        view = "Overview"
        options = st.container()

if inv is None or getattr(options, "open", False):
    with options:
        st.caption("Local analysis computes a shortlist without sending data to providers.")
        if st.button(
            "Run local investigation",
            icon=":material/refresh:",
            type="primary" if inv is None else "secondary",
            disabled=bool(ws.job_id) or ws.replay,
        ):
            try:
                start_analysis(ws)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if st.button(
            "Investigate with connected models",
            icon=":material/hub:",
            disabled=bool(ws.job_id) or ws.replay or not connected or not external_allowed,
        ):
            try:
                start_analysis(ws, connected=True)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if ws.replay:
            st.caption("Recorded replay. Open a new dataset to run another investigation.")
        elif not connected:
            st.caption("Local analysis is ready. The owner can configure model keys in Streamlit Secrets.")
        elif not external_allowed:
            st.caption("Allow external analysis for this dataset in Understand to enable connected models.")
            st.page_link("app_pages/understand.py", label="Review dataset permission", icon=":material/lock:")
        else:
            st.caption("Providers are configured. Connected work uses the owner's API allowance.")
        if connected and not ws.replay:
            protocol = suggested_model_plan(ds, ws.context())
            if protocol and ws.model_count < 2:
                target, split, split_field = protocol
                st.caption(
                    f"Connected pass: predict {ds.label(target)} with "
                    + (
                        f"later observations held out by {ds.label(split_field)}."
                        if split_field
                        else "a seeded row holdout. Use Models for a group-aware protocol."
                    )
                    + " Set a focus in Understand to choose the target. Up to two model experiments per context."
                )

if inv is None:
    st.info(
        "The first pass is running. Results appear here when the current task finishes."
        if ws.job_id
        else "Run a local investigation to compute observations from your table."
    )
    st.stop()

if not ws.replay:
    from firstlook.semantic.model import get_model

    semantic_model = get_model(ds)
    if semantic_model.clarifications:
        st.page_link(
            "app_pages/meaning.py",
            label=f"{len(semantic_model.clarifications)} analytical decisions to review in Meaning",
            icon=":material/schema:",
        )
    with st.form("question_form", border=False):
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            question = st.text_input(
                "Ask a question about the evidence",
                max_chars=1000,
                placeholder="For example: does response differ by region?",
                key="question",
                width="stretch",
            )
            submitted = st.form_submit_button(
                "Investigate question", icon=":material/arrow_forward:", disabled=bool(ws.job_id)
            )
        if submitted:
            try:
                start_question(ws, question)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

prepared_question_panel()

findings = list(inv.findings)
if view == "Relationships":
    findings = [
        f
        for f in findings
        if f.family in {"relationship", "group_distribution", "category_relationship", "quantile_bin_summary"}
    ]
if not findings:
    st.info("No supported views in this category. Try the overview or inspect field meanings.")
else:
    finding_card(findings[0], inv, lead=True)
    limit = 12 if st.toggle("Show more observations", key="show_more") else 6
    grid = st.grid(2, min_column_width=360, gap="small")
    for finding in findings[1:limit]:
        with grid.cell():
            finding_card(finding, inv)

if inv.terra.get("synthesis"):
    with st.container(border=True):
        st.markdown("**Terra's proposed interpretation**")
        synthesis = inv.terra["synthesis"]
        st.markdown(synthesis["interpretation"])
        claim_review_panel(inv.terra.get("claim_review"), "investigation")
        st.caption(
            "Model interpretation. Measured observations and completed checks retain their own evidence."
        )
        for question in synthesis.get("next_questions", []):
            st.caption("Next question: " + question)
elif inv.terra.get("note"):
    st.caption(inv.terra["note"])
for note in ("model_note", "provider_note"):
    if inv.terra.get(note):
        st.caption(inv.terra[note])
if not any(f.family == "relationship" for f in inv.findings):
    st.caption(
        "No numeric pair met the association shortlist threshold (|r| or |ρ| ≥ 0.30 with adequate support). Distribution and group views can still be useful."
    )

if not ws.replay:
    if semantic_model.clarifications:
        with st.expander("Decisions that could unlock stronger analyses"):
            prioritized = next(
                (
                    d.get("question")
                    for d in reversed(inv.semantic_decisions)
                    if d.get("stage") == "clarification_priority"
                ),
                None,
            )
            questions = sorted(semantic_model.clarifications, key=lambda q: q.id != prioritized)
            for clarification in questions[:3]:
                st.markdown("**" + clarification.question + "**")
                st.caption(clarification.reason)
            st.page_link("app_pages/meaning.py", label="Resolve analytical meaning", icon=":material/schema:")
    with st.expander("What the semantic planner allowed and held back"):
        import pandas as pd

        plans = [d for d in inv.semantic_decisions if d.get("operation") == "metric"]
        if plans:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Metric": semantic_model.metric(d["metric"]).label,
                            "Decision": d["status"],
                            "Reason": d["reason"] or "Recorded definition satisfies this plan's checks",
                        }
                        for d in plans
                    ]
                ),
                hide_index=True,
                alt="Metric eligibility decisions with explicit reasons",
            )
        st.page_link(
            "app_pages/meaning.py", label="Define or run a reusable metric", icon=":material/functions:"
        )
with st.expander("Search scope and decision provenance"):
    st.caption(
        f"{len(inv.candidate_log):,} recorded screening entries. Ranking weights and thresholds are engineering defaults, not probabilities of truth."
    )
    st.json([d.model_dump(mode="json") for d in inv.decisions], expanded=False)
    st.dataframe(
        inv.candidate_log[:300], hide_index=True, alt="Recorded candidate screening and exclusion log"
    )
