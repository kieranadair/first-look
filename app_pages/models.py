"""Predictive questions and recorded diagnostics have a dedicated work area."""

import streamlit as st

from firstlook.modeling import eligible_targets, predictor_policy
from firstlook.ui.components import finding_card, page_header
from firstlook.ui.runtime import settings, start_model, workspace

ws, cfg = workspace(), settings()
page_header(
    "Models",
    "Evaluate a declared prediction task, then inspect where the recorded holdout succeeds or struggles.",
    compact=True,
)
if ws.dataset is None or ws.investigation is None:
    st.caption("Build an overview before evaluating a prediction task and its held-out evidence.")
    st.page_link(
        "app_pages/understand.py" if ws.dataset is None else "app_pages/explore.py",
        label="Open a dataset" if ws.dataset is None else "Build an overview in Explore",
        icon=":material/explore:",
    )
    st.stop()
inv, ds = ws.investigation, ws.dataset
st.caption(
    "Local baselines and hosted TabPFN share a holdout. A prediction score describes the declared task; it does not establish causality."
)

configure = (
    st.popover("Change predictive task", icon=":material/tune:", on_change="rerun")
    if ws.model
    else st.container()
)
if ws.model is None or getattr(configure, "open", False):
    with configure:
        st.markdown("**Define the prediction task**")
        if not ws.replay:
            targets = eligible_targets(ds)
            if not targets:
                st.info(
                    "Model exploration needs an eligible focus with at least 200 labeled rows and adequate class support."
                )
            else:
                default = targets.index(ws.focus) if ws.focus in targets else 0
                from firstlook.semantic.model import get_model

                declared_group = get_model(ds).model_group
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    target = st.selectbox(
                        "Model focus", targets, index=default, format_func=ds.label, key="model_target"
                    )
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
                        else [
                            f.id for f in ds.record.fields if (split != "time" or f.role.value == "timestamp")
                        ]
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
                    help="Use fields that would be known when predicting this target. Contract exclusions still apply.",
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
                elif not st.session_state.get("external_ok"):
                    st.caption(
                        "Hosted TabPFN sends permitted training and test values to Prior Labs. Allow external analysis in Understand, or uncheck it to use local baselines."
                    )
                    st.page_link(
                        "app_pages/understand.py", label="Review dataset permission", icon=":material/tune:"
                    )
                else:
                    st.caption("Hosted TabPFN uses the dataset permission granted in Understand.")
                if st.button(
                    "Evaluate predictive structure",
                    type="primary",
                    disabled=bool(ws.job_id) or not predictors,
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
    st.dataframe(
        pd.DataFrame(run.metrics).T,
        height=min(220, 38 + 35 * len(run.metrics)),
        alt="Held-out metrics for the evaluated models",
    )
    st.caption(
        "Target: "
        + ds.label(run.target)
        + " · "
        + run.split
        + " holdout · recorded model "
        + run.id[:8]
        + ". Subgroup slices are exploratory; they do not constitute fresh validation."
    )
    if not any(f.family == "model" for f in inv.findings) and not ws.replay:
        from firstlook.modeling import diagnostic_findings

        diagnostic_findings(ds, inv, run)
        ws.bound_views()
    diagnostics = [f for f in inv.findings if f.family == "model"]
    groups = [f for f in diagnostics if f.chart.template == "bar"]
    pairs = [f for f in diagnostics if f not in groups]
    mode = st.segmented_control(
        "Diagnostic question",
        ["Prediction and errors", "Group errors"] if groups and pairs else ["Prediction and errors"],
        default="Prediction and errors",
        key="model_diagnostic_mode",
    )
    chosen = groups if mode == "Group errors" else pairs or groups
    grid = st.grid(2, min_column_width=330, gap="small")
    for f in chosen[:2]:
        with grid.cell():
            finding_card(f, inv)
    for warning in run.warnings:
        st.caption(warning)
st.stop()
