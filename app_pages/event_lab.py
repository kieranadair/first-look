"""Explicit event populations, past features and complete future labels."""

from typing import Any, cast

import pandas as pd
import streamlit as st

from firstlook.contracts import Role
from firstlook.event_tasks import EventTaskSpec, EventTaskRun, event_dataset, event_preflight
from firstlook.model_protocol import comparison_verdict
from firstlook.ui.components import page_header
from firstlook.ui.runtime import workspace, settings, start_event_preparation, start_event_evaluation
from firstlook.ui.task_controls import preflight_panel

ws, cfg = workspace(), settings()
page_header(
    "Event lab",
    "Turn a recorded event table into an explicit question about what happens next. Inspect the population and labels before fitting.",
)
if ws.dataset is None:
    st.info("Open an event table with entity identifiers and event timestamps.")
    st.page_link("app_pages/understand.py", label="Open a table", icon=":material/table_chart:")
    st.stop()
ds = ws.dataset
if not ws.replay:
    times = [
        f.id
        for f in ds.record.fields
        if f.role == Role.TIME and not f.excluded and ds.frame[f.id].notna().any()
    ]
    identities = [f.id for f in ds.record.fields if f.role in {Role.ID, Role.CATEGORY} and not f.excluded]
    if not times or not identities:
        st.info(
            "This recipe needs a parsed timestamp and an included entity field. Review roles in Understand."
        )
        st.page_link("app_pages/understand.py", label="Review fields", icon=":material/table_chart:")
        st.stop()
    st.caption(
        "1 · Define observed events and complete windows.  2 · Prepare a separate entity-at-time table.  3 · Inspect the fixed holdout and optionally evaluate models. The original table remains unchanged."
    )
    controls = (
        st.popover("Prepare another event task", icon=":material/tune:", on_change="rerun")
        if ws.event_runs
        else st.container(border=True)
    )
    if not ws.event_runs or getattr(controls, "open", False):
        with controls:
            st.subheader("Define a bounded event question")
            choices, boundaries = st.columns(2, gap="medium")
            with choices:
                entity = st.selectbox("Entity to score", identities, format_func=ds.label, key="event_entity")
                event_time = st.selectbox(
                    "When the event happened", times, format_func=ds.label, key="event_time"
                )
                event_ids = [None] + [f for f in identities if f != entity]
                event_id = st.selectbox(
                    "Distinct event identity",
                    event_ids,
                    format_func=lambda v: ds.label(v) if v else "Each recorded row is one event",
                    key="event_identity",
                )
                known_time = st.selectbox(
                    "When the event information became available",
                    [None] + [t for t in times if t != event_time],
                    format_func=lambda v: ds.label(v) if v else "Use event time with explicit attestation",
                    key="event_known",
                )
                recipe = (
                    st.segmented_control(
                        "Outcome",
                        ["recurrence", "event_count"],
                        default="recurrence",
                        format_func=lambda v: "Another event?" if v == "recurrence" else "Number of events",
                        key="event_recipe",
                    )
                    or "recurrence"
                )
                horizon = st.number_input(
                    "Future outcome window · days", min_value=1, max_value=365, value=30, key="event_horizon"
                )
                lookback = st.number_input(
                    "Past activity window · days", min_value=1, max_value=365, value=90, key="event_lookback"
                )
                reporting_delay = st.number_input(
                    "Maximum outcome reporting delay · days",
                    min_value=0,
                    max_value=365,
                    value=2 if known_time else 0,
                    key="event_reporting_delay_" + str(known_time),
                    help="Attest a bound for when outcome windows become fully known. The largest observed delay alone cannot prove that bound. Late training labels are purged.",
                )
            with boundaries:
                earliest = pd.to_datetime(ds.frame[event_time], utc=True).min()
                default_start = (earliest + pd.Timedelta(int(lookback), unit="D")).date()
                start = st.date_input("First anchor · midnight UTC", value=default_start, key="event_start")
                count = st.slider(
                    "Nonoverlapping anchor windows", min_value=3, max_value=6, value=3, key="event_anchors"
                )
                complete = st.date_input(
                    "Last date with complete event recording · inclusive UTC day",
                    value=pd.to_datetime(ds.frame[event_time], utc=True).max().date(),
                    key="event_complete",
                )
                st.caption(
                    "The date shown is only a starting suggestion. The latest recorded date does not establish completeness."
                )
                available = st.checkbox(
                    "I confirm event information was available when each event occurred",
                    key="event_available",
                )
                coverage = st.checkbox(
                    "I confirm observed events, complete recording for the displayed windows and the reporting-delay bound",
                    key="event_coverage",
                )
                st.caption(
                    "Only entities active in the past window enter the population. Entities appearing only in the future do not enter it. Event identities deduplicate repeated source rows; conflicting identities are rejected."
                )
            anchors = [
                str(pd.Timestamp(start, tz="UTC") + pd.Timedelta(int(horizon) * i, unit="D"))
                for i in range(int(count))
            ]
            end = str(
                pd.Timestamp(complete, tz="UTC") + pd.Timedelta(1, unit="D") - pd.Timedelta(1, unit="ns")
            )
            st.dataframe(
                [
                    {"Anchor": a, "Outcome ends": str(pd.Timestamp(a) + pd.Timedelta(int(horizon), unit="D"))}
                    for a in anchors
                ],
                hide_index=True,
                alt="Proposed past-to-future anchor windows before task preparation",
            )
            st.caption(
                "At most 6 anchors / 10,000 derived rows / 2 preparations per context. Incomplete windows are omitted, never labelled as no event. The final complete anchor is held out; this assesses later activity of known entities."
            )
            if st.button(
                "Prepare event task locally",
                type="primary",
                disabled=bool(ws.job_id)
                or not coverage
                or (not known_time and not available)
                or ws.event_prepare_count >= 2,
                key="prepare_events",
            ):
                try:
                    spec = EventTaskSpec(
                        dataset=ds.record.fingerprint,
                        entity=entity,
                        event_time=event_time,
                        event_id=event_id,
                        known_time=known_time,
                        available_at_event=available,
                        recipe=cast(Any, recipe),
                        lookback_days=int(lookback),
                        horizon_days=int(horizon),
                        reporting_delay_days=int(reporting_delay),
                        anchors=anchors,
                        complete_through=end,
                        coverage_confirmed=coverage,
                    )
                    start_event_preparation(ws, spec)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
if not ws.event_runs:
    st.info(
        "Prepared tasks show exact populations, source membership and outcome support here. No model or external request is needed for preparation."
    )
    st.stop()
chosen = st.selectbox(
    "Prepared event task",
    [r["id"] for r in ws.event_runs],
    format_func=lambda value: next(
        f"{r['spec']['recipe'].replace('_', ' ')} · {r['spec']['horizon_days']} days · {len(r['records'])} entity anchors"
        for r in ws.event_runs
        if r["id"] == value
    ),
    key="prepared_event",
)
run = EventTaskRun.model_validate(next(r for r in ws.event_runs if r["id"] == chosen))
derived = event_dataset(run)
view = (
    st.segmented_control(
        "Event task view",
        ["Population and labels", "Evaluate models"],
        default="Evaluate models" if run.model else "Population and labels",
        key="event_view_" + run.id + str(bool(run.model)),
    )
    or "Population and labels"
)
if view == "Population and labels":
    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        st.markdown("**Population and observation windows**")
        st.dataframe(
            run.preparation["anchor_populations"],
            hide_index=True,
            alt="Source-derived entity support at every complete anchor",
        )
        st.caption(run.preparation["population_rule"])
        st.caption(run.preparation["split_rule"])
        if run.preparation["censored_anchors"]:
            st.warning("Incomplete anchors omitted: " + ", ".join(run.preparation["censored_anchors"]))
        st.caption(
            f"{run.preparation.get('unknown_availability_source_rows', 0)} source rows have unknown availability · {run.preparation['deduplicated_source_rows']} repeated event rows deduplicated · {run.preparation.get('purged_training_rows', 0)} training rows purged for outcome reporting · {run.preparation['generalization']}."
        )
    with right:
        st.markdown("**Inspect the derived records**")
        st.dataframe(
            pd.DataFrame(run.records).head(30),
            hide_index=True,
            height=280,
            alt="Past-only event features and separately constructed forward outcomes",
        )
        st.download_button(
            "Download derived table",
            pd.DataFrame(run.records).to_csv(index=False),
            "first-look-event-task.csv",
            "text/csv",
            key="event_csv",
        )
    for warning in run.preparation["warnings"]:
        st.caption(warning)
    st.caption("Choose Evaluate models above to inspect readiness and run the fixed comparison.")
if view == "Evaluate models":
    readiness = event_preflight(run)
    if not run.model:
        preflight_panel(derived, readiness)
    if run.model:
        st.subheader("Observed predictive comparison")
        st.dataframe(
            pd.DataFrame(run.model.metrics).T,
            alt="Matched event-task model metrics including the previous-window baseline",
        )
        st.info(comparison_verdict(run.model))
        from firstlook.discovery import Investigation
        from firstlook.modeling import diagnostic_findings
        from firstlook.ui.components import chart_view

        inv = Investigation(run.derived_context)
        diagnostic_findings(derived, inv, run.model)
        grid = st.grid(2, min_column_width=330, gap="small")
        for finding in inv.findings[:2]:
            with grid.cell():
                st.markdown("**" + finding.title + "**")
                chart_view(finding.chart, inv.results[finding.result_id], "event_" + finding.id, height=310)
        with st.popover(
            "Inspect the recorded protocol", icon=":material/fact_check:", on_change="rerun"
        ) as event_protocol:
            if event_protocol.open:
                preflight_panel(derived, readiness)
        for warning in run.model.warnings:
            st.caption(warning)
    elif not ws.replay:
        hosted = st.checkbox(
            "Include hosted TabPFN on permitted derived predictors",
            disabled=not cfg.available("tabpfn") or not st.session_state.get("external_ok"),
            key="event_hosted",
        )
        if st.button(
            "Evaluate this fixed event task",
            disabled=bool(ws.job_id) or readiness["status"] == "blocked" or ws.event_model_count >= 2,
            key="evaluate_events",
        ):
            try:
                start_event_evaluation(ws, run.id, hosted)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.caption(
            "Two model evaluations per context; one final evaluation per frozen event task. Changing questions after seeing a holdout creates a new exploratory experiment."
        )
with st.expander("Exact source membership and recipe"):
    st.json(run.spec.model_dump(mode="json"), expanded=True)
    st.dataframe(
        run.memberships[:100],
        hide_index=True,
        alt="Original history and outcome row identities for derived entity anchors",
    )
st.page_link("app_pages/evidence.py", label="Preserve task and model evidence", icon=":material/bookmarks:")
