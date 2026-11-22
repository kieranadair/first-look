"""One coherent comparison occupies one board; source population is never silently replaced."""

import streamlit as st

from firstlook.comparison import preview
from firstlook.contracts import digest
from firstlook.semantic.model import get_model
from firstlook.semantics import dimensions, measures
from firstlook.ui.components import comparison_board, page_header, workflow_note
from firstlook.ui.runtime import start_comparison, start_comparison_review, workspace, settings

ws, cfg = workspace(), settings()
page_header(
    "Compare in context.",
    "Keep a reference beside the cohort. Compare definitions and distributions without losing your place.",
    compact=True,
)
if ws.dataset is None:
    st.info("Open a dataset in Understand, then select marks in Explore or define a cohort here.")
    st.stop()
ds = ws.dataset
if ws.replay:
    if ws.comparisons:
        chosen = st.selectbox(
            "Recorded comparison",
            range(len(ws.comparisons)),
            format_func=lambda i: f"Comparison {i + 1} · {ws.comparisons[i].spec.operation}",
        )
        comparison_board(ws.comparisons[chosen], "recorded")
    else:
        st.info("This saved investigation has no comparison boards.")
    st.stop()
model = get_model(ds)
if st.session_state.pop("_hide_cohort_builder", False):
    st.session_state.cohort_builder = False
if ws.selection is None:
    st.session_state.cohort_builder = True
change = st.toggle("Choose or change the cohort", key="cohort_builder")
if change:
    workflow_note(
        "1 · Define a cohort",
        "A cohort is a set of recorded rows or whole entities inside the current reference.",
        "Choose a category and its levels, or select marks in an Explore chart. Previewing leaves the investigation and model intact.",
    )
    cats = dimensions(ds)
    if not cats:
        st.info("No categorical predicate is available. Select points or distribution marks in Explore.")
    else:
        with st.container(horizontal=True, vertical_alignment="bottom"):
            field = st.selectbox("Cohort category", cats, format_func=ds.label, key="cohort_field")
            values = sorted(ds.frame.loc[ws.context().row_ids, field].dropna().astype(str).unique())
            levels = st.multiselect(
                "Include levels", values[:200], key="cohort_levels_" + field, max_selections=50
            )
        if len(values) > 200:
            st.caption(
                "Only the first 200 recorded levels are listed. Select marks to identify a more specific cohort."
            )
        with st.container(horizontal=True, vertical_alignment="bottom"):
            policy = (
                st.segmented_control(
                    "Selection unit",
                    ["rows", "entities"] if model.entities else ["rows"],
                    default="rows",
                    format_func=lambda x: "Exact rows" if x == "rows" else "Whole entities",
                    key="cohort_policy",
                )
                or "rows"
            )
            entity = (
                st.selectbox(
                    "Entity",
                    [e.id for e in model.entities],
                    format_func=lambda i: model.entity(i).label,
                    key="cohort_entity",
                )
                if policy == "entities"
                else None
            )
            if st.button("Preview cohort", type="primary", disabled=not levels, key="preview_cohort"):
                try:
                    frame = ds.frame.loc[ws.context().row_ids]
                    ids = frame.index[frame[field].astype(str).isin(levels) & frame[field].notna()].tolist()
                    preview(
                        ws,
                        ids,
                        "predicate:" + digest([field, levels]),
                        digest([ws.context().id, field, levels]),
                        policy,
                        entity,
                        "Explicit recorded category predicate",
                    )
                    st.session_state["_hide_cohort_builder"] = True
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
if ws.selection is None:
    st.stop()
selection = ws.selection
st.caption(
    f"ANCHORED REFERENCE {len(selection.base.row_ids):,} rows · SELECTED {len(selection.rows):,} rows · {len(selection.rows) - len(selection.selected_rows):,} rows added by entity closure"
)
if not ws.comparison:
    st.caption(
        "Compare recomputes both populations. Begin filtered investigation makes the cohort the new working population; you can return to this reference."
    )
nums, cats = measures(ds), dimensions(ds)
options = (
    (["Distribution"] if nums else [])
    + (["Approved metric"] if model.metrics else [])
    + (["Category frequency"] if cats else [])
)
toolbar = st.container(horizontal=True, gap="small")
if ws.comparison:
    with toolbar:
        controls = st.popover("Change comparison question", icon=":material/tune:")
else:
    controls = st.container()
with controls:
    kind = (
        st.segmented_control("Comparison question", options, default=options[0], key="compare_kind")
        if options
        else None
    )
    kwargs = {}
    with st.container(horizontal=True, vertical_alignment="bottom"):
        if kind == "Distribution":
            kwargs = {
                "operation": "ecdf",
                "measure": st.selectbox("Measure", nums, format_func=ds.label, key="compare_measure"),
            }
        elif kind == "Approved metric":
            metric = st.selectbox(
                "Approved metric",
                [m.id for m in model.metrics],
                format_func=lambda i: model.metric(i).label,
                key="compare_metric",
            )
            group = st.selectbox(
                "Break down by",
                [None] + cats,
                format_func=lambda i: ds.label(i) if i else "Population total",
                key="compare_group",
            )
            kwargs = {"operation": "metric", "metric": metric, "groups": [group] if group else []}
        elif kind == "Category frequency":
            kwargs = {
                "operation": "frequency",
                "measure": st.selectbox("Category", cats, format_func=ds.label, key="compare_category"),
            }
        reference = st.selectbox(
            "Reference population",
            ["remainder", "whole"],
            format_func=lambda x: "All other rows" if x == "remainder" else "Whole anchored population",
            key="compare_reference",
        )
        denominator = (
            st.selectbox(
                "Ratio denominators",
                ["cohort", "anchored"],
                format_func=lambda x: (
                    "Within each population" if x == "cohort" else "Keep original population"
                ),
                key="compare_denominator",
                help="Applies to active-population ratios. Group-specific rate denominators retain their declared definition; entity allocation always retains its anchored reference.",
            )
            if kind == "Approved metric" and model.metric(metric).aggregation == "ratio"
            else "cohort"
        )
    kwargs.update(reference=reference, denominator=denominator)
    request = digest([selection.id, kwargs])
    with st.container(horizontal=True, gap="small"):
        if st.button(
            "Compare populations",
            type="primary",
            disabled=bool(ws.job_id) or not kind,
            key="compute_comparison",
        ):
            try:
                start_comparison(ws, **kwargs)
                st.session_state.comparison_request = request
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
with toolbar:
    if st.button("Begin filtered investigation", disabled=bool(ws.job_id), key="filter_cohort"):
        ws.begin_filtered()
        st.switch_page("app_pages/discover.py")
    if st.button("Clear cohort", disabled=bool(ws.job_id), key="clear_cohort"):
        ws.selection, ws.comparison = None, None
        ws.cohort_revision += 1
        st.rerun()
if ws.comparison:
    bundle = ws.comparison
    if st.session_state.get("comparison_request") != request:
        st.info("Controls changed. The board below retains its recorded definition until you compare again.")
    comparison_board(bundle)
    with st.container(horizontal=True):
        if st.button(
            "Save comparison to Evidence",
            key="save_comparison",
            disabled=any(b.id == bundle.id for b in ws.comparisons),
        ):
            ws.comparisons = ([bundle.model_copy(deep=True)] + ws.comparisons)[:3]
            ws.bound_views()
            st.toast(
                "Comparison definitions, populations and results preserved. Up to three boards per investigation."
            )
            st.rerun()
        if st.button(
            "Review comparison with Terra",
            disabled=bool(ws.job_id) or not cfg.available("terra") or bool(ws.comparison_review_count),
            key="review_comparison",
        ):
            try:
                start_comparison_review(ws)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.caption(
        "Model review is optional: Terra reads matched companions and proposes eligible Python checks; Jev can prioritize them. No model is refitted. One review per investigation, with dataset permission."
    )
