"""Question-oriented perspectives with compact, adjacent analytical companions."""

import streamlit as st

from firstlook.contracts import Role
from firstlook.exploration import perspective_coverage
from firstlook.semantic.model import get_model
from firstlook.semantic.planner import metric_fields
from firstlook.semantics import dimensions, measures
from firstlook.ui.components import page_header, render_chart, scope_caption, workflow_note
from firstlook.ui.runtime import start_analysis, start_recipe, start_view, workspace

ws = workspace()
page_header(
    "Explore",
    "Choose an angle, inspect its context, then compare or challenge what catches your attention.",
    compact=True,
)
if ws.dataset is None:
    workflow_note(
        "Start here",
        "Open a table to explore its variation, relationships and missing information.",
        "Understand profiles the recorded data. Meaning defines business quantities. Explore and Compare turn those definitions into evidence.",
    )
    st.page_link("app_pages/understand.py", label="Open a dataset", icon=":material/table_chart:")
    st.stop()
ds = ws.dataset
if ws.investigation is None:
    workflow_note(
        "First pass",
        "Compute a bounded overview before choosing a direction.",
        "Local analysis works without API keys. It screens supported perspectives and records what the budget leaves unexamined.",
    )
    if st.button(
        "Build local overview", type="primary", disabled=bool(ws.job_id) or ws.replay, key="build_overview"
    ):
        try:
            start_analysis(ws)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.stop()
inv = ws.investigation
lens = (
    st.segmented_control(
        "Analytical perspective",
        ["Overview", "Distribution", "Categories", "Relationships", "Time"],
        default="Overview",
        key="exploration_lens",
        persist_state="session",
    )
    or "Overview"
)
nums, cats = measures(ds), dimensions(ds)
model = get_model(ds)
families = {
    "Distribution": {"distribution", "ecdf", "group_distribution", "group_shape", "histogram_sensitivity"},
    "Categories": {"metric", "frequency", "category_relationship", "categorical_facets", "concentration"},
    "Relationships": {"relationship", "quantile_bin_summary", "density", "influence"},
    "Time": {"time", "temporal"},
}
if lens == "Overview":
    coverage = inv.coverage if ws.replay else perspective_coverage(ds, inv, ws.opened)
    inv.coverage = coverage
    left, right = st.columns([1, 1.65], gap="medium")
    with left:
        st.markdown("**Which perspectives have we examined?**")
        st.caption("A finite catalog of perspectives, not a completeness score.")
        st.dataframe(
            [
                {
                    "Perspective": r["family"],
                    "Status": r["status"],
                    "Computed": r["computed"],
                    "Outside budget": r["outside_budget"],
                }
                for r in coverage
            ],
            hide_index=True,
            height=292,
            alt="Coverage of supported analytical perspectives",
        )
        st.caption(
            "Choose an angle above. Inspect its definition, compare a cohort, then challenge or preserve it."
        )
    with right:
        if inv.findings:
            finding = inv.findings[0]
            st.markdown("**A useful starting point**")
            st.caption(finding.title)
            render_chart(finding, inv, suffix="overview_start", height=285)
            st.caption(finding.observation)
            if st.button("Inspect this perspective", key="overview_open"):
                ws.inspect_id = finding.id
                ws.opened.add(finding.id)
                st.switch_page("app_pages/inspect.py")
    with st.container(horizontal=True):
        st.page_link(
            "app_pages/discover.py", label="Browse findings or ask a question", icon=":material/query_stats:"
        )
        st.page_link(
            "app_pages/compare.py", label="Define a cohort to compare", icon=":material/compare_arrows:"
        )
    if st.toggle("Show coverage definitions and exclusions", key="coverage_detail"):
        st.dataframe(
            coverage, hide_index=True, alt="Exact finite search scope and reasons for blocked perspectives"
        )
    st.stop()

purposes = {
    "Distribution": (
        "Look behind a typical value.",
        "Compare shape, tails and spread. Two groups can have the same average and very different distributions.",
    ),
    "Categories": (
        "Separate contribution, frequency and exposure.",
        "Choose an approved metric. Intersections and within-category proportions require explicit denominators.",
    ),
    "Relationships": (
        "Inspect direction, shape and changing spread.",
        "Correlations and conditional averages can miss structure. Keep the recorded pairs beside a complementary view.",
    ),
    "Time": (
        "Keep the observation process in view.",
        "Aggregation, smoothing and calendar phase answer different questions. Unknown dates stay unknown; complete-window recipes require scoped coverage.",
    ),
}
purpose, action = purposes[lens]
choices = [
    f
    for f in inv.findings
    if f.family in families[lens] or inv.results[f.result_id].plan.operation in families[lens]
]
if choices:
    ids = [f.id for f in choices]
    if ws.explore_id in ids:
        st.session_state["perspective_result_" + lens] = ws.explore_id
        ws.explore_id = None
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        selected = st.selectbox(
            "Computed perspective",
            ids,
            format_func=lambda i: next(f.title for f in choices if f.id == i),
            key="perspective_result_" + lens,
            width="stretch",
        )
        controls = st.popover(
            "Change perspective", icon=":material/tune:", on_change="rerun", key="perspective_setup_" + lens
        )
else:
    st.markdown("**" + purpose + "**")
    st.caption(action)
    controls = st.container(border=True)

recipe = None
fields = []
params: dict = {}
operation = None
if not choices or getattr(controls, "open", False):
    with controls:
        if lens == "Distribution" and nums:
            with st.container(horizontal=True, vertical_alignment="bottom"):
                value = st.selectbox("Measure", nums, format_func=ds.label, key="explore_distribution_field")
                mode = st.selectbox(
                    "Question",
                    ["Histogram", "Cumulative distribution", "Two group shapes", "Histogram sensitivity"],
                    key="distribution_mode",
                )
                if mode == "Two group shapes" and cats:
                    category = st.selectbox("Group", cats, format_func=ds.label, key="shape_category")
                    levels = sorted(
                        ds.frame.loc[ws.context().row_ids, category].dropna().astype(str).unique()
                    )
                    group_levels = st.multiselect(
                        "Two named groups",
                        levels[:200],
                        default=levels[:2],
                        max_selections=2,
                        key="shape_levels_" + category,
                    )
                    recipe, fields, params = "group_shape", [category, value], {"levels": group_levels}
                elif mode == "Histogram sensitivity":
                    normalization = st.selectbox(
                        "Histogram quantity",
                        ["count", "proportion", "density"],
                        format_func=lambda v: {
                            "count": "Row counts",
                            "proportion": "Proportion per bin",
                            "density": "Density (area=1)",
                        }[v],
                        key="histogram_normalization",
                    )
                    bins = st.slider("Bin count", 5, 50, 15, key="sensitivity_bins")
                    origin = st.slider(
                        "Origin shift (bin widths)", 0.0, 1.0, 0.5, 0.1, key="sensitivity_origin"
                    )
                    recipe, fields, params = (
                        "histogram_sensitivity",
                        [value],
                        {"bins": bins, "origin": origin, "normalization": normalization},
                    )
                else:
                    operation, fields = (
                        "ecdf" if mode == "Cumulative distribution" else "distribution",
                        [value],
                    )
        elif lens == "Relationships" and len(nums) >= 2:
            with st.container(horizontal=True, vertical_alignment="bottom"):
                x = st.selectbox("Explanatory axis", nums, format_func=ds.label, key="explore_x")
                y = st.selectbox(
                    "Response axis", [n for n in nums if n != x], format_func=ds.label, key="explore_y"
                )
                mode = st.selectbox(
                    "Perspective",
                    ["Center and spread", "Recorded pairs", "Density counts", "Influence"],
                    key="pair_mode",
                )
                fields = [x, y]
                if mode in {"Density counts", "Influence"}:
                    recipe = "density" if mode == "Density counts" else "influence"
                else:
                    operation = "quantile_bin_summary" if mode == "Center and spread" else "relationship"
        elif lens == "Categories" and cats:
            with st.container(horizontal=True, vertical_alignment="bottom"):
                mode = st.selectbox(
                    "Question",
                    ["Frequency", "Conditional cross-tab", "Metric facets", "Concentration"],
                    key="category_mode",
                )
                first = st.selectbox("Category", cats, format_func=ds.label, key="explore_cat")
                if mode == "Frequency":
                    operation, fields = "frequency", [first]
                elif mode == "Conditional cross-tab" and len(cats) >= 2:
                    second = st.selectbox(
                        "Conditioning category",
                        [c for c in cats if c != first],
                        format_func=ds.label,
                        key="explore_cat2",
                    )
                    normalization = st.selectbox(
                        "Quantity",
                        ["count", "whole", "within_x", "within_y", "residual"],
                        format_func=lambda v: {
                            "count": "Recorded pair counts",
                            "whole": "Share of complete pairs",
                            "within_x": "Within first category",
                            "within_y": "Within second category",
                            "residual": "Descriptive independence residual",
                        }[v],
                        key="crosstab_quantity",
                    )
                    operation, fields, params = (
                        "category_relationship",
                        [first, second],
                        {"normalization": normalization},
                    )
                elif model.metrics:
                    metric = st.selectbox(
                        "Approved metric",
                        [m.id for m in model.metrics],
                        format_func=lambda mid: model.metric(mid).label,
                        key="explore_cat_metric",
                    )
                    groups = [first]
                    if mode == "Metric facets" and len(cats) >= 2:
                        second = st.selectbox(
                            "Items within each panel",
                            [c for c in cats if c != first],
                            format_func=ds.label,
                            key="facet_items",
                        )
                        groups.append(second)
                    recipe = "categorical_facets" if mode == "Metric facets" else "concentration"
                    fields = list(dict.fromkeys(metric_fields(ds, model.metric(metric)) + groups))
                    params = {"metric": metric, "groups": groups}
        elif lens == "Time":
            times = [f.id for f in ds.record.fields if f.role == Role.TIME and not f.excluded]
            if times and model.metrics:
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    time = st.selectbox("Timestamp", times, format_func=ds.label, key="explore_time")
                    metric = st.selectbox(
                        "Approved metric",
                        [m.id for m in model.metrics],
                        format_func=lambda mid: model.metric(mid).label,
                        key="explore_time_metric",
                    )
                    mode = st.selectbox(
                        "Temporal question",
                        ["aggregation", "smooth", "calendar", "index"],
                        format_func=lambda v: {
                            "aggregation": "Period aggregation",
                            "smooth": "Trailing complete windows",
                            "calendar": "Calendar phase",
                            "index": "Common-baseline series",
                        }[v],
                        key="temporal_mode",
                    )
                    period = st.selectbox(
                        "Period",
                        ["D", "W", "MS"],
                        index=2,
                        format_func=lambda v: {"D": "Day", "W": "Week", "MS": "Month"}[v],
                        key="temporal_period",
                    )
                fields = list(dict.fromkeys(metric_fields(ds, model.metric(metric)) + [time]))
                recipe = "temporal"
                params: dict = {"metric": metric, "time_field": time, "mode": mode, "period": period}
                if mode == "smooth":
                    params["window"] = st.slider(
                        "Consecutive complete periods", 2, 12, 3, key="smoother_window"
                    )
                elif mode == "index":
                    mids = st.multiselect(
                        "Compatible approved series (two to four)",
                        [m.id for m in model.metrics],
                        format_func=lambda mid: model.metric(mid).label,
                        max_selections=4,
                        key="index_metrics",
                    )
                    params.update(
                        metrics=mids,
                        baseline=st.date_input("Common reference date", key="index_date").isoformat(),
                    )
                    fields = list(
                        dict.fromkeys(
                            [f for mid in mids for f in metric_fields(ds, model.metric(mid))] + [time]
                        )
                    )
            else:
                st.caption(
                    "A timestamp and an approved metric are needed. Define their observation process in Meaning."
                )
        else:
            st.caption("This perspective needs additional eligible fields. Review roles and meanings first.")
        if st.button(
            "Open this perspective",
            type="primary",
            disabled=bool(ws.job_id) or ws.replay or not (recipe or operation),
            key="open_perspective",
        ):
            try:
                if recipe:
                    start_recipe(ws, recipe, fields, params)
                else:
                    start_view(
                        ws,
                        str(operation),
                        fields,
                        params,
                        purpose + " " + " / ".join(ds.label(f) for f in fields),
                    )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

if not choices:
    st.info("Choose fields and open a perspective. An absent shortlist view does not mean no pattern exists.")
    st.stop()

finding = next(f for f in choices if f.id == selected)
related = inv.related_views.get(finding.result_id, {})
companion = next((f for f in inv.findings if f.result_id == related.get("companion")), None)
display = [companion, finding] if companion else [finding]
grid = st.grid(len(display), min_column_width=330, gap="small")
for f in display:
    with grid.cell():
        with st.container(border=True, height="stretch"):
            st.markdown("**" + f.title + "**")
            render_chart(f, inv, suffix="perspective_" + f.id, selection=not ws.replay, height=310)
            st.caption(scope_caption(inv.results[f.result_id]))
            st.caption(f.observation)
if not ws.replay:
    with st.container(horizontal=True):
        if st.button("Inspect definition and exact values", key="perspective_inspect"):
            ws.inspect_id = finding.id
            ws.opened.add(finding.id)
            st.switch_page("app_pages/inspect.py")
        if st.button("Challenge this perspective", key="perspective_challenge"):
            ws.challenge_id = finding.id
            st.switch_page("app_pages/challenge.py")
        if st.button("Pin perspective", key="perspective_pin"):
            from firstlook.state import pin

            pin(ws, finding.id)
            st.toast("Perspective preserved in Evidence.")
if st.toggle("Show exact computed values", key="perspective_values"):
    st.dataframe(
        inv.results[finding.result_id].frame().drop(columns=["row_ids", "row_id"], errors="ignore"),
        hide_index=True,
        alt="Exact values, support and definitions behind this perspective",
    )
for warning in inv.results[finding.result_id].warnings:
    st.caption(warning)
