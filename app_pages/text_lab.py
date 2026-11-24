"""Frozen text interpretations beside coverage and matched predictive evidence."""

import re

import pandas as pd
import streamlit as st

from firstlook.contracts import AnalysisPlan, ChartSpec, ResultArtifact, Role, digest
from firstlook.modeling import eligible_targets
from firstlook.semantic.model import get_model
from firstlook.text_features import (
    TextFeatureRun,
    TextFeatureSpec,
    feature_summary,
    feature_table,
    preview_text_cost,
)
from firstlook.ui.components import page_header, chart_view
from firstlook.ui.runtime import (
    workspace,
    settings,
    start_text_proposal,
    start_text_coding,
    start_feature_model,
)

ws, cfg = workspace(), settings()
page_header(
    "Text lab",
    "Turn a selected text field into reviewable interpretations. Keep unknowns, source records and predictive evidence in view.",
)
if ws.dataset is None:
    st.info("Open a table with notes, descriptions or other text before creating coded features.")
    st.page_link("app_pages/understand.py", label="Open a table", icon=":material/table_chart:")
    st.stop()
ds, ctx = ws.dataset, ws.context()
fields = [f.id for f in ds.record.fields if f.role in {Role.TEXT, Role.CATEGORY} and not f.excluded]
fields.sort(
    key=lambda f: (ds.field(f).role != Role.TEXT, "note" not in ds.label(f).casefold(), ds.field(f).position)
)
if not ws.replay:
    st.caption(
        "1 · Define concrete yes/no questions.  2 · Review sharing scope and freeze a coding run.  3 · Inspect coverage, compare records or evaluate prediction."
    )
    if not fields:
        st.info("No included text fields are available. Review field roles in Understand.")
        st.stop()
    setup = (
        st.popover("Create another coding run", icon=":material/tune:", on_change="rerun")
        if ws.text_runs
        else st.container(border=True)
    )
    if not ws.text_runs or getattr(setup, "open", False):
        with setup:
            st.subheader("Define the coding plan")
            field = st.selectbox("Text to interpret", fields, format_func=ds.label, key="text_source")
            st.caption(
                "Each feature is a separate question: several can be true for one record. Missing information remains unknown rather than becoming a negative observation."
            )
            st.checkbox("Allow external analysis for this dataset", key="external_ok")
            share = st.checkbox(
                "Allow sending the selected text to the configured providers",
                key="external_text_" + ds.record.fingerprint,
            )
            st.caption(
                "Jev receives selected source text and question criteria. Optional Terra proposals receive at most eight text examples, without targets. Inputs are retained in your evidence export; use text you are permitted to share."
            )
            if st.button(
                "Suggest questions with Terra",
                disabled=bool(ws.job_id)
                or not cfg.available("terra")
                or not share
                or not st.session_state.get("external_ok"),
                key="suggest_text_questions",
            ):
                try:
                    start_text_proposal(ws, field)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            proposal = (
                ws.text_proposal
                if ws.text_proposal.get("context") == ctx.id and ws.text_proposal.get("field") == field
                else {}
            )
            initial = [
                {
                    "Feature": f["label"],
                    "Question": f["question"],
                    "Yes criterion": f["yes"],
                    "No criterion": f["no"],
                }
                for f in proposal.get("features", [])
            ]
            editor = st.data_editor(
                pd.DataFrame(
                    initial, columns=pd.Index(["Feature", "Question", "Yes criterion", "No criterion"])
                ),
                num_rows="dynamic",
                hide_index=True,
                key="text_definitions_" + field + "_" + digest(proposal),
                alt="Editable frozen text feature questions and yes/no criteria",
            )
            st.caption(
                "Add one to six rows. Example: ‘Physical damage’ · ‘Does the note explicitly describe physical damage?’ Supply concrete descriptions of a yes and a no."
            )
            limit = st.slider(
                "Maximum selected source rows",
                1,
                240,
                60,
                key="text_rows",
                help="A fixed seeded sample is used when the active population is larger. Predictive comparison normally needs at least 200 labelled selected rows.",
            )
            definitions, error = [], ""
            try:
                for i, row in editor.dropna(how="all").iterrows():
                    if any(pd.isna(row[k]) for k in ["Feature", "Question", "Yes criterion", "No criterion"]):
                        raise ValueError("Complete all four cells for each feature.")
                    label = str(row["Feature"]).strip()
                    key = (
                        (re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_") or "feature")[:32]
                        + "_"
                        + str(i)
                    )
                    if not key[0].isalpha():
                        key = "f_" + key
                    definitions.append(
                        TextFeatureSpec(
                            key=key,
                            label=label,
                            question=str(row["Question"]),
                            yes=str(row["Yes criterion"]),
                            no=str(row["No criterion"]),
                        ).model_dump(mode="json")
                    )
                if not 1 <= len(definitions) <= 6 or len({f["label"] for f in definitions}) != len(
                    definitions
                ):
                    raise ValueError("Define one to six distinct named features.")
            except ValueError as exc:
                error = str(exc)
            if error:
                st.caption(error)
            else:
                try:
                    cost = preview_text_cost(ds, ctx, field, definitions, limit)
                    over_budget = (
                        cost["input_budget_bytes"] > 2_000_000 or cost["largest_batch_bytes"] > 48_000
                    )
                    st.markdown(
                        f"**{cost['rows']:,} selected / {cost['source_population']:,} active rows · {cost['features']} frozen features**"
                    )
                    st.caption(
                        f"{cost['unique_codable_texts']} unique codable texts · at most {cost['max_requests']} requests / {cost['questions']} judgments · {cost['source_characters']:,} unique source characters. {cost['missing_or_empty']} missing/empty and {cost['overlong']} overlong records retain their status. Two experiments per context."
                    )
                    if over_budget:
                        st.info(
                            "This plan exceeds the bounded input budget. Reduce selected rows or shorten criteria before coding."
                        )
                    if st.button(
                        "Freeze questions and code selected text",
                        type="primary",
                        disabled=bool(ws.job_id)
                        or over_budget
                        or not share
                        or not cfg.available("jev")
                        or not st.session_state.get("external_ok")
                        or ws.text_run_count >= 2,
                        key="code_text",
                    ):
                        start_text_coding(ws, field, definitions, limit)
                        st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if not cfg.available("jev"):
                st.caption(
                    "The owner can enable Jev in Streamlit Secrets. Prepare questions without a key; local heuristics are not presented as Jev answers."
                )
if not ws.text_runs:
    st.info(
        "Completed runs show classified coverage, unresolved text and source cohorts here. Text questions are frozen before predictive evaluation."
    )
    st.stop()
run_id = st.selectbox(
    "Frozen coding run",
    [r["id"] for r in ws.text_runs],
    format_func=lambda v: next(
        f"{ds.label(r['source_field'])} · {len(r['source_rows'])} rows · {len(r['definitions'])} features"
        for r in ws.text_runs
        if r["id"] == v
    ),
    key="text_run",
)
run = TextFeatureRun.model_validate(next(r for r in ws.text_runs if r["id"] == run_id))
st.caption(
    f"{run.selection} · {len(run.records):,} selected / {run.source_population:,} source rows. Model-coded interpretations are not observed facts. Unknowns are excluded from yes/no denominators."
)
st.dataframe(
    feature_summary(run),
    hide_index=True,
    column_config={
        "Classified coverage": st.column_config.NumberColumn(format="percent"),
        "Yes share among classified": st.column_config.NumberColumn(format="percent"),
    },
    alt="Feature counts with explicit classification coverage and denominators",
)
left, right = st.columns([1.25, 1], gap="medium")
with left:
    chosen = st.selectbox(
        "Feature to inspect",
        [f.key for f in run.definitions],
        format_func=lambda k: next(f.label for f in run.definitions if f.key == k),
        key="text_inspect_feature",
    )
    definition = next(f for f in run.definitions if f.key == chosen)
    st.markdown("**" + definition.question + "**")
    records = [
        {
            "label": status.replace("_", " "),
            "value": sum(row["features"][chosen]["status"] == status for row in run.records),
            "row_ids": [row["row_id"] for row in run.records if row["features"][chosen]["status"] == status],
        }
        for status in ["yes", "no", "unresolved", "missing", "too_long"]
    ]
    identity = digest([run.id, chosen, "display"])
    plan = AnalysisPlan(
        id=identity,
        operation="text_feature_display",
        fields=[run.source_field],
        context=run.context,
        question=definition.question,
        params={"source_run": run.id},
    )
    result = ResultArtifact(
        id=identity, plan=plan, records=records, support=len(run.records), metadata={"display_only": True}
    )
    chart = ChartSpec(
        id=digest([identity, "chart"]),
        result_id=identity,
        context=run.context,
        template="bar",
        x_label="Model-coded source row count",
        y_label=definition.label,
        zero_baseline=True,
        alt="Coding outcomes including unresolved, missing and overlong text",
    )
    chart_view(chart, result, "text_" + chosen, height=300)
with right:
    st.markdown("**Read the definition and source records together**")
    st.caption("Yes: " + definition.yes)
    st.caption("No: " + definition.no)
    if not ws.replay and not ds.frame.empty:
        for label, status in [("Compare yes records", "yes"), ("Compare no records", "no")]:
            ids = [r["row_id"] for r in run.records if r["features"][chosen]["status"] == status]
            if st.button(label, disabled=not ids or bool(ws.job_id), key="text_cohort_" + status):
                from firstlook.comparison import preview
                from firstlook.discovery import Investigation

                ws.investigation = ws.investigation or Investigation(ctx)
                preview(
                    ws,
                    ids,
                    run.id,
                    digest([run.id, chosen, status]),
                    scope="Exact source rows with this model-coded status, within the selected text run",
                )
                st.switch_page("app_pages/compare.py")
        sample = feature_table(run).head(12)
        sample[ds.label(run.source_field)] = [ds.frame.at[i, run.source_field] for i in sample.source_row_id]
        st.dataframe(sample, hide_index=True, alt="Source text beside coded outcomes")
    st.download_button(
        "Download coded values",
        feature_table(run).to_csv(index=False),
        "first-look-coded-features.csv",
        "text/csv",
        key="download_text_values",
    )
    st.page_link(
        "app_pages/judgments.py",
        label="Inspect exact questions and probabilities",
        icon=":material/fact_check:",
    )
st.subheader("Does the coding add predictive information?")
st.caption(
    "Compare original permitted predictors with original-plus-coded features on exactly the same held-out rows. Targets and held-out errors are never sent to the question proposer. Predictive gain does not establish a cause."
)
if run.evaluation:
    evaluation = run.evaluation
    rows = [
        {"Predictors": label, "Model": model, **metrics}
        for label, key in [("Original", "baseline"), ("Original + coded", "augmented")]
        for model, metrics in evaluation[key]["metrics"].items()
    ]
    st.dataframe(rows, hide_index=True, alt="Matched held-out metrics with and without coded features")
    st.caption(evaluation["protocol"])
    for key in ["baseline", "augmented"]:
        for warning in evaluation[key]["warnings"]:
            st.caption(warning)
elif not ws.replay:
    targets = [t for t in eligible_targets(ds) if t != run.source_field]
    if len(run.source_rows) < 200 or not targets:
        st.caption(
            "Predictive comparison needs 200 labelled selected rows and an independent eligible target. Freeze a larger coding run if this question matters."
        )
    else:
        model = get_model(ds)
        with st.form("text_model_protocol"):
            target = st.selectbox("Recorded predictive target", targets, format_func=ds.label)
            split = st.selectbox("Holdout", ["group"] if model.model_group else ["random", "group", "time"])
            group_fields = [
                f.id
                for f in ds.record.fields
                if not f.excluded
                and f.role in ({Role.TIME} if split == "time" else {Role.ID, Role.CATEGORY, Role.ORDINAL})
            ]
            split_field = (
                st.selectbox(
                    "Holdout field",
                    [model.model_group] if model.model_group else group_fields,
                    format_func=ds.label,
                )
                if split != "random" and group_fields
                else None
            )
            available = st.checkbox(
                "I confirm this source text was available before the outcome being predicted"
            )
            hosted = st.checkbox(
                "Include hosted TabPFN for augmented predictors", disabled=not cfg.available("tabpfn")
            )
            submitted = st.form_submit_button(
                "Evaluate frozen features", disabled=bool(ws.job_id) or ws.text_model_count >= 2
            )
        if submitted:
            try:
                start_feature_model(ws, run.id, target, split, split_field, available, hosted)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
