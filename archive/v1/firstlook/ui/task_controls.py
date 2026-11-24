"""Native controls keep task assumptions beside their consequences."""

from typing import Any, cast

import pandas as pd
import streamlit as st

from firstlook.analytical_tasks import (
    TaskDefinition,
    AvailabilityRule,
    current_task,
    availability_rules,
    save_task,
    save_availability,
)
from firstlook.contracts import Role


def task_editor(ws):
    ds = ws.dataset
    task = current_task(ds)
    st.caption(
        "Describe the question and when information must be known. Saving changes the analytical context; the population description documents intent while actual selections determine row membership."
    )
    times = [f.id for f in ds.record.fields if f.role == Role.TIME and not f.excluded]
    targets = [None] + [
        f.id
        for f in ds.record.fields
        if not f.excluded and f.role in {Role.MEASURE, Role.CATEGORY, Role.BOOL, Role.ORDINAL}
    ]
    columns = st.columns([1.25, 1], gap="medium")
    with columns[0]:
        st.subheader("Question and intended use")
        with st.form("analytical_task"):
            question = st.text_input("Analytical question", value=task.question, max_chars=1000)
            purposes = ["descriptive", "diagnostic", "prediction"]
            purpose = st.selectbox(
                "Intended use",
                purposes,
                index=purposes.index(task.purpose),
                format_func=lambda v: {
                    "descriptive": "Describe recorded data",
                    "diagnostic": "Explore predictive structure",
                    "prediction": "Predict using information known at the decision time",
                }[v],
            )
            unit = st.text_input("Unit of analysis", task.unit, max_chars=200)
            population = st.text_area("Intended population", task.population, max_chars=600, height=80)
            target = st.selectbox(
                "Recorded target, when applicable",
                targets,
                index=targets.index(task.target) if task.target in targets else 0,
                format_func=lambda v: ds.label(v) if v else "Not specified",
            )
            decision = st.text_input("When would a prediction be made?", task.decision_time, max_chars=300)
            anchor = st.selectbox(
                "Anchor timestamp",
                [None] + times,
                index=([None] + times).index(task.anchor_field) if task.anchor_field in times else 0,
                format_func=lambda v: ds.label(v) if v else "Not specified",
            )
            outcome_known = st.selectbox(
                "Outcome becomes known at",
                [None] + times,
                index=([None] + times).index(task.outcome_known_field)
                if task.outcome_known_field in times
                else 0,
                format_func=lambda v: ds.label(v) if v else "Not specified",
            )
            horizon = st.number_input(
                "Outcome window in days · 0 for an existing recorded target",
                min_value=0,
                max_value=365,
                value=task.horizon_days,
            )
            complete = st.text_input(
                "Data complete through · ISO timestamp with time zone",
                value=task.complete_through,
                help="Required for a forward outcome window. This is an explicit collection attestation, not the maximum observed date.",
            )
            metrics = ["auto", "MAE", "RMSE", "Balanced accuracy", "Macro F1", "Log loss"]
            metric = st.selectbox(
                "Primary comparison metric", metrics, index=metrics.index(task.primary_metric)
            )
            if st.form_submit_button("Save analytical task", type="primary"):
                try:
                    save_task(
                        ds,
                        TaskDefinition(
                            dataset=ds.record.fingerprint,
                            question=question,
                            purpose=cast(Any, purpose),
                            unit=unit,
                            population=population,
                            target=target,
                            decision_time=decision,
                            anchor_field=anchor,
                            outcome_known_field=outcome_known,
                            horizon_days=int(horizon),
                            complete_through=complete.strip(),
                            primary_metric=cast(Any, metric),
                        ),
                    )
                    ws.invalidate()
                    ws.message = "Task saved. Dependent results will use the revised definition."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with columns[1]:
        st.subheader("What could be known?")
        fid = st.selectbox(
            "Field availability",
            [f.id for f in ds.record.fields if not f.excluded],
            format_func=ds.label,
            key="availability_field",
        )
        rule = availability_rules(ds).get(fid, AvailabilityRule(field=fid))
        st.caption(
            "Unknown availability remains an assumption in diagnostic work. A prospective task excludes unreviewed, late or undocumented mutable predictors consistently across all models."
        )
        with st.form("availability_" + fid):
            statuses = ["unreviewed", "known_at_anchor", "after_timestamp", "unavailable"]
            status = st.selectbox(
                "Availability rule",
                statuses,
                index=statuses.index(rule.status),
                format_func=lambda v: v.replace("_", " ").capitalize(),
            )
            timestamp = st.selectbox(
                "Availability timestamp, if used",
                [None] + times,
                index=([None] + times).index(rule.timestamp) if rule.timestamp in times else 0,
                format_func=lambda v: ds.label(v) if v else "Not specified",
            )
            lag = st.number_input(
                "Additional reporting delay in hours",
                min_value=0.0,
                max_value=8760.0,
                value=float(rule.lag_hours),
            )
            mutable = st.checkbox("Exported values may have changed since the event", value=rule.mutable)
            history = st.checkbox(
                "The recorded values preserve the relevant historical versions", value=rule.history_available
            )
            roles = ["unspecified", "event", "recorded", "known", "scheduled"]
            role = st.selectbox(
                "Timestamp meaning, when this field is a date", roles, index=roles.index(rule.timestamp_role)
            )
            evidence = st.text_area(
                "Collection notes supporting this declaration", rule.evidence, max_chars=1200, height=100
            )
            if st.form_submit_button("Save availability rule"):
                try:
                    save_availability(
                        ds,
                        AvailabilityRule(
                            field=fid,
                            status=cast(Any, status),
                            timestamp=timestamp,
                            lag_hours=lag,
                            mutable=mutable,
                            history_available=history,
                            timestamp_role=cast(Any, role),
                            evidence=evidence,
                        ),
                    )
                    ws.invalidate()
                    ws.message = "Availability saved. Source values are unchanged."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        st.page_link("app_pages/models.py", label="Preview model readiness", icon=":material/fact_check:")
        st.page_link(
            "app_pages/event_lab.py", label="Construct an outcome from events", icon=":material/event_repeat:"
        )


def preflight_panel(dataset, readiness):
    with st.container(border=True):
        st.markdown("**Before fitting: task readiness**")
        if readiness["status"] == "blocked":
            for error in readiness["errors"]:
                st.error(error)
            st.caption(readiness["boundary"])
            return
        st.caption(readiness["status"].replace("_", " ").capitalize() + " · " + readiness["task"]["question"])
        grid = st.grid(4, min_column_width=130, gap="small")
        grid.metric("Labelled source rows", readiness["labeled_rows"])
        grid.metric("Incomplete windows", readiness["incomplete_window_rows"])
        grid.metric("Purged training rows", readiness["purged_training_rows"])
        grid.metric("Permitted predictors", len(readiness["predictors"]))
        st.dataframe(
            pd.DataFrame(readiness["partitions"]),
            hide_index=True,
            alt="Exact proposed training and held-out support before fitting",
        )
        st.caption(
            f"Budget omissions: {readiness['budget_omitted_rows']:,} rows · total protocol omissions: {readiness.get('protocol_omitted_rows', 0):,} rows · primary metric: {readiness['primary_metric']}. {readiness['boundary']}"
        )
        details = [
            {"Field": dataset.label(f), "Treatment": "Excluded", "Reason": reason}
            for f, reason in readiness["excluded"].items()
        ]
        details += [
            {"Field": dataset.label(r["field"]), "Treatment": "Diagnostic assumption", "Reason": r["reason"]}
            for r in readiness["assumptions"]
        ]
        if details:
            st.dataframe(
                details,
                hide_index=True,
                height=min(240, 38 + 35 * len(details)),
                alt="Consequential predictor exclusions and unresolved availability assumptions",
            )


def recording_panel(ws, key):
    from firstlook.recording_process import report, recording_plan
    from firstlook.discovery import analyze
    from firstlook.ui.components import chart_view

    if ws.dataset is None or ws.replay:
        return
    times = [f.id for f in ws.dataset.record.fields if f.role == Role.TIME and not f.excluded]
    if not times:
        st.caption("Recording coverage over time needs a parsed timestamp field.")
        return
    packet = report(ws.dataset, ws.context())
    st.caption(
        f"All {packet['active_rows']:,} active source rows · {packet['undated_rows']:,} rows have no usable date. Recorded coverage can reveal selection or collection changes; it cannot prove their cause."
    )
    if packet["time"]:
        left, right = st.columns([1.4, 1], gap="medium")
        with left:
            result, finding = analyze(ws.dataset, ws.context(), recording_plan(ws.dataset, ws.context()))
            chart_view(finding.chart, result, key + "_coverage", height=320)
        with right:
            temporal = pd.DataFrame(packet["time"]).drop(columns=["row_ids"])
            field = st.selectbox(
                "Coverage field", packet["fields"], format_func=ws.dataset.label, key=key + "_field"
            )
            st.dataframe(
                temporal[temporal.field == field][["period", "rows", "missing", "missing_share", "distinct"]],
                hide_index=True,
                height=300,
                alt="Period denominators, missingness and observed category diversity",
            )
        for warning in packet["warnings"]:
            st.caption(warning)
        if packet["flags"]:
            st.dataframe(
                [{**r, "field": ws.dataset.label(r["field"])} for r in packet["flags"]],
                hide_index=True,
                alt="Computed coverage contrasts that merit review",
            )
        if packet["groups"]:
            with st.expander("Group coverage and category presence"):
                st.dataframe(
                    packet["groups"], hide_index=True, alt="Full-context group coverage with denominators"
                )
                st.dataframe(
                    packet["category_presence"],
                    hide_index=True,
                    alt="Observed category representation across periods",
                )
