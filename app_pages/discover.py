import streamlit as st

from firstlook.modeling import eligible_targets, predictor_policy, suggested_model_plan
from firstlook.ui.components import evidence_inspector, finding_card, page_header, render_chart
from firstlook.ui.runtime import settings, start_analysis, start_model, start_question, workspace

ws, cfg = workspace(), settings()
page_header(
    "Follow the evidence.", "A focused set of observations. A useful next question. Room to change your mind."
)
if ws.dataset is None:
    st.info("Choose an example or open your dataset in Understand.")
    if st.button("Open a dataset", type="primary"):
        st.switch_page("app_pages/understand.py")
    st.stop()

with st.container(horizontal=True, gap="small"):
    if st.button("Run local investigation", icon=":material/refresh:", disabled=bool(ws.job_id) or ws.replay):
        try:
            start_analysis(ws)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    connected = cfg.available("jev") or cfg.available("terra") or cfg.available("tabpfn")
    if st.button(
        "Investigate with connected models",
        icon=":material/hub:",
        disabled=bool(ws.job_id) or ws.replay or not connected,
    ):
        try:
            start_analysis(ws, connected=True)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.caption(
        "Recorded replay"
        if ws.replay
        else (
            "Connected providers are ready"
            if connected
            else "Local analysis is ready. Model keys can be added later."
        )
    )
if connected and not ws.replay:
    protocol = suggested_model_plan(ws.dataset, ws.context())
    if protocol and ws.model_count < 2:
        target, split, split_field = protocol
        st.caption(
            f"Connected pass: predict {ws.dataset.label(target)} with "
            + (
                f"later observations held out by {ws.dataset.label(split_field)}."
                if split_field
                else "a seeded row holdout. Use Model lens for a group-aware protocol."
            )
            + " Set a focus in Understand to choose the target. Up to two model experiments per context."
        )

if ws.investigation is None:
    if ws.job_id:
        st.info("The first pass is running. Results appear here when the current task finishes.")
    else:
        st.info("Run the local investigation to compute a shortlist and challenge its leading observations.")
    st.stop()
inv, ds = ws.investigation, ws.dataset
if not ws.replay:
    from firstlook.semantic.model import get_model

    semantic_model = get_model(ds)
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
            for q in questions[:3]:
                st.markdown("**" + q.question + "**")
                st.caption(q.reason)
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
                            "Reason": d["reason"] or "Recorded definition satisfies this plan’s checks",
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
view = st.segmented_control(
    "Explore",
    ["Overview", "Relationships", "Model lens"],
    default="Overview",
    key="discover_view",
    persist_state="session",
    label_visibility="collapsed",
)

if view == "Model lens":
    st.subheader("Look for structure the summaries can miss.")
    st.caption(
        "Compare held-out prediction with fixed-budget baselines. A high score is not a causal explanation."
    )
    if not ws.replay:
        targets = eligible_targets(ds)
        if not targets:
            st.info(
                "Model exploration needs an eligible focus with at least 200 labeled rows and adequate class support."
            )
        else:
            default = targets.index(ws.focus) if ws.focus in targets else 0
            target = st.selectbox(
                "Model focus", targets, index=default, format_func=ds.label, key="model_target"
            )
            from firstlook.semantic.model import get_model

            declared_group = get_model(ds).model_group
            split = st.selectbox(
                "Evaluation split",
                ["group"] if declared_group else ["random", "group", "time"],
                format_func=lambda x: {
                    "random": "Held-out rows",
                    "group": "Unseen groups",
                    "time": "Later observations",
                }[x],
                key="model_split",
            )
            split_field = None
            if split != "random":
                options = (
                    [declared_group]
                    if declared_group
                    else [f.id for f in ds.record.fields if (split != "time" or f.role.value == "timestamp")]
                )
                if options:
                    split_field = st.selectbox(
                        "Split field", options, format_func=ds.label, key="model_split_field"
                    )
            candidates, excluded = predictor_policy(ds, target, ds.frame.loc[ws.context().row_ids])
            candidates = [f for f in candidates if f != split_field][:40]
            predictors = st.multiselect(
                "Permitted predictors",
                candidates,
                default=candidates,
                format_func=ds.label,
                key=f"predictors_{target}_{split}_{split_field}",
            )
            with st.expander("Excluded fields and protocol"):
                for f, reason in excluded.items():
                    st.caption(ds.label(f) + ": " + reason)
                st.caption(
                    "Seed 20261120 · at most 10,000 labeled rows · train-only preprocessing · 70/30 split."
                )
            hosted = st.checkbox(
                "Include hosted TabPFN",
                value=cfg.available("tabpfn"),
                disabled=not cfg.available("tabpfn"),
                key="model_hosted",
            )
            if not cfg.available("tabpfn"):
                st.caption(
                    "TabPFN is not configured. The same evaluation can run with actual local baselines."
                )
            if st.button(
                "Evaluate predictive structure", type="primary", disabled=bool(ws.job_id) or not predictors
            ):
                try:
                    start_model(ws, target, split, split_field, predictors, hosted)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    if ws.model:
        import pandas as pd

        run = ws.model
        st.caption(
            f"DIAGNOSTICS: {run.provider.upper()}  ·  {len(run.train_ids):,} TRAIN / {len(run.test_ids):,} HELD OUT"
        )
        st.dataframe(pd.DataFrame(run.metrics).T, alt="Held-out metrics for the evaluated models")
        for warning in run.warnings:
            st.caption(warning)
        for f in inv.findings:
            if f.family == "model":
                finding_card(f, inv)
    st.stop()

if not ws.replay:
    with st.form("question_form", border=False):
        question = st.text_input(
            "Ask a question about the evidence",
            max_chars=1000,
            placeholder="For example: does response differ by region?",
            key="question",
        )
        if st.form_submit_button(
            "Investigate question", icon=":material/arrow_forward:", disabled=bool(ws.job_id)
        ):
            try:
                start_question(ws, question)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

if inv.terra.get("synthesis"):
    with st.container(border=True):
        st.caption("READ THE EVIDENCE  ·  TERRA INTERPRETATION")
        synthesis = inv.terra["synthesis"]
        st.markdown(synthesis["interpretation"])
        st.caption(
            "Model interpretation. Measured observations and completed checks retain their own evidence."
        )
        for q in synthesis.get("next_questions", []):
            st.caption("Next question: " + q)
elif inv.terra.get("note"):
    st.caption(inv.terra["note"])
if inv.terra.get("model_note"):
    st.caption(inv.terra["model_note"])
if inv.terra.get("provider_note"):
    st.caption(inv.terra["provider_note"])

findings = list(inv.findings)
if view == "Relationships":
    findings = [
        f
        for f in findings
        if f.family in {"relationship", "group_distribution", "category_relationship", "quantile_bin_summary"}
    ]
if not any(f.family == "relationship" for f in inv.findings):
    st.caption(
        "No numeric pair met the configured association shortlist threshold (|r| or |ρ| ≥ 0.30 with adequate support). Distribution and group views can still be useful."
    )
if ws.inspect_id:
    f = next((f for f in inv.findings if f.id == ws.inspect_id), None)
    if f:
        with st.container(border=True):
            st.subheader(f.title)
            render_chart(f, inv, suffix="inspection", selection=True, height=400)
            evidence_inspector(f, inv)
            if st.button("Close inspection", key="close_inspection"):
                ws.inspect_id = None
                st.rerun()
if not findings:
    st.info("No supported views in this category. Try the overview or inspect field meanings.")
else:
    finding_card(findings[0], inv, lead=True)
    limit = 12 if st.toggle("Show more observations", key="show_more") else 6
    grid = st.grid(2, min_column_width=420, gap="small")
    for f in findings[1:limit]:
        with grid.cell():
            finding_card(f, inv)
with st.expander("Search scope and decision provenance"):
    st.caption(
        f"{len(inv.candidate_log):,} recorded screening entries. Ranking weights and thresholds are engineering defaults, not probabilities of truth."
    )
    st.json([d.model_dump(mode="json") for d in inv.decisions], expanded=False)
    st.dataframe(
        inv.candidate_log[:300], hide_index=True, alt="Recorded candidate screening and exclusion log"
    )
