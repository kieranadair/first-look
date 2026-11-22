"""Native semantic workbench: decide once, reuse across every analytical action."""

from typing import Any, cast

import pandas as pd
import streamlit as st

from firstlook.contracts import Role, digest
from firstlook.discovery import Investigation, analyze
from firstlook.semantic.model import (
    add_metric,
    commit_model,
    export_contract,
    get_model,
    import_contract,
    proposal_candidate,
)
from firstlook.semantic.planner import metric_plan
from firstlook.semantic.policy import decision
from firstlook.semantic.profile import inspect_relationship
from firstlook.semantic_contracts import Entity, FieldMeaning, MetadataProposal, Metric, TimePolicy
from firstlook.semantics import dimensions, measures
from firstlook.ui.components import page_header
from firstlook.ui.runtime import settings, start_semantic_review, workspace

ws = workspace()
page_header(
    "Meaning makes the difference.", "Define the analytical unit. Let every view, check and model reuse it."
)
if ws.dataset is None:
    st.info("Open a dataset in Understand first.")
    st.stop()
if ws.replay:
    st.info(
        "This is recorded evidence. Inspect its contract in Evidence, or open a new dataset to change meaning."
    )
    st.stop()
ds = ws.dataset
model = get_model(ds)
ctx = ws.context()


def saved(message):
    ws.invalidate()
    ws.message = message + " Dependent analyses will use the new contract."
    st.rerun()


summary = st.grid(4, min_column_width=160)
summary.metric("Open decisions", len(model.clarifications))
summary.metric("Reusable metrics", len(model.metrics))
summary.metric("Entity definitions", len(model.entities))
summary.metric("Observed relationships", len(model.relationships))
st.caption(
    "Exact structural evidence is automatic. Business meanings are proposals until you confirm them. Each definition is scoped to this table."
)
decisions_tab, metrics_tab, structure_tab, contract_tab = st.tabs(
    ["Decisions", "Metrics", "Structure & time", "Contract"]
)

with decisions_tab:
    st.subheader("Resolve the decisions that unlock work.")
    st.caption(
        "Start with the quantity you care about. Descriptive exploration remains available while other decisions are open."
    )
    for question in model.clarifications[:4]:
        with st.container(border=True):
            st.markdown("**" + question.question + "**")
            st.caption(question.reason)
            if question.suggested:
                st.badge("Proposal: " + question.suggested, icon=":material/lightbulb:")
            if question.affected_metrics:
                st.caption(
                    f"{len(question.affected_metrics)} proposed metric definitions depend on this decision."
                )
    if not model.clarifications:
        st.success(
            "The current clarification queue is resolved. Definitions remain inspectable and editable."
        )
    st.subheader("Quantity meaning")
    nums = measures(ds)
    if nums:
        fid = st.selectbox("Quantity", nums, format_func=ds.label, key="meaning_field")
        meaning = model.meaning(fid)
        kinds = [
            "unknown",
            "amount",
            "flow",
            "count",
            "state",
            "rate",
            "ratio",
            "cumulative",
            "temperature",
            "circular",
            "coordinate",
            "index",
            "composition",
        ]
        with st.form("quantity_definition_" + fid):
            cols = st.columns(2)
            kind = cols[0].selectbox(
                "What kind of quantity?",
                kinds,
                index=kinds.index(meaning.kind),
                help="Flow: events/amounts accrued. State: a level observed at an instant. Cumulative: a running counter. Rate/ratio: require an explicit denominator or weighting.",
            )
            unit = cols[1].text_input(
                "Known measurement unit",
                meaning.unit,
                max_chars=80,
                help="Enter a known unit, e.g. kWh, degC, kg. Do not infer one from the magnitude.",
            )
            currency = cols[0].text_input("Currency, if applicable", meaning.currency, max_chars=12)
            basis = cols[1].text_input("Reference / price / conversion basis", meaning.basis, max_chars=200)
            transforms = st.multiselect(
                "Permitted display transformations",
                ["identity", "log", "sqrt", "zscore", "difference", "percent_change"],
                default=meaning.allowed_transforms,
                help="Applied after aggregation. Domain and unit checks still apply; permitting a transform does not make every value valid.",
            )
            available = st.checkbox(
                "Available at prediction time",
                value=meaning.available_at_prediction,
                help="Clear for post-outcome values or information unavailable when a prediction would be made.",
            )
            if st.form_submit_button("Confirm quantity meaning", icon=":material/check:"):
                try:
                    candidate = model.model_copy(deep=True)
                    m = FieldMeaning.model_validate(
                        {
                            **candidate.meaning(fid).model_dump(mode="json"),
                            "kind": kind,
                            "unit": unit.strip(),
                            "currency": currency.strip(),
                            "basis": basis.strip(),
                            "confirmed": True,
                            "allowed_transforms": list(dict.fromkeys(["identity"] + transforms)),
                            "available_at_prediction": available,
                        }
                    )
                    candidate.meanings = [m if old.field == fid else old for old in candidate.meanings]
                    commit_model(ds, candidate, fid, "quantity", m.model_dump(mode="json"))
                    saved("Quantity meaning confirmed.")
                except ValueError as exc:
                    st.error(str(exc))
        st.caption(
            "A confirmed quantity does not establish its value grain. Confirm each total or weighted definition in Metrics."
        )
    if ws.semantic_review.get("metadata_proposals"):
        st.subheader("Terra’s semantic hypotheses")
        st.caption(
            "Proposals are checked against the table. Only your explicit selection changes meaning; schedules and gap assumptions require direct declaration."
        )
        proposals = ws.semantic_review["metadata_proposals"]
        for item in proposals:
            proposal = MetadataProposal.model_validate(item["proposal"])
            with st.container(border=True):
                st.markdown("**" + proposal.property.replace("_", " ") + " · " + proposal.value + "**")
                st.caption(proposal.reason)
                st.caption(item["validation"])
        eligible = [i for i, item in enumerate(proposals) if item["valid"]]
        selected_proposals = st.multiselect(
            "Metadata hypotheses to confirm",
            eligible,
            format_func=lambda i: (
                proposals[i]["proposal"]["subject"]
                + " · "
                + proposals[i]["proposal"]["property"]
                + " → "
                + proposals[i]["proposal"]["value"]
            ),
            key="metadata_selected",
        )
        if st.button(
            "Confirm selected metadata hypotheses",
            disabled=not selected_proposals or ws.semantic_review.get("context") != ctx.id,
            key="metadata_apply",
        ):
            try:
                from firstlook.ingest import Dataset

                temporary = Dataset(ds.record.model_copy(deep=True), ds.frame)
                for i in selected_proposals:
                    temporary.record.semantic_model = proposal_candidate(
                        temporary, MetadataProposal.model_validate(proposals[i]["proposal"])
                    )
                commit_model(
                    ds,
                    get_model(temporary),
                    "table",
                    "selected_metadata_hypotheses",
                    [proposals[i]["proposal"] for i in selected_proposals],
                )
                saved("Selected hypotheses confirmed together.")
            except ValueError as exc:
                st.error(str(exc))
    with st.expander("Ask Terra to review analytical meaning"):
        st.caption(
            "Optional: semantic hypotheses from bounded field summaries and the contract. Original rows are not sent in this review. Set external-data permission in Understand first."
        )
        if st.button(
            "Review semantic contract with Terra",
            key="review_contract",
            disabled=not settings().available("terra")
            or not st.session_state.get("external_ok", False)
            or bool(ws.job_id)
            or bool(ws.semantic_review_count),
        ):
            try:
                start_semantic_review(ws)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

with metrics_tab:
    st.subheader("Define once. Ask consistently.")
    st.caption(
        "Metrics are a small typed algebra, not generated Python. Denominators, entity grains, weights and transformations travel with the evidence."
    )
    selected = st.selectbox(
        "Recorded metric",
        [m.id for m in model.metrics],
        format_func=lambda mid: model.metric(mid).label,
        key="metric_existing",
    )
    current = model.metric(selected)
    check = decision(
        ds,
        current,
        [],
        next((t.field for t in model.time_policies if t.id == current.time_policy), None),
        ctx.row_ids,
    )
    with st.container(border=True):
        st.markdown("**" + current.label + "**")
        st.caption(current.description or current.aggregation.replace("_", " "))
        st.badge(check.status, icon=":material/rule:")
        for reason in check.reasons + check.requirements:
            st.caption(reason)
        with st.expander("Exact definition"):
            st.json(current.model_dump(mode="json"))
        if not current.confirmed and st.button(
            "Confirm this metric definition", key="confirm_existing_metric"
        ):
            try:
                candidate = current.model_copy(deep=True)
                candidate.confirmed = True
                add_metric(ds, candidate)
                saved("Metric definition confirmed.")
            except ValueError as exc:
                st.error(str(exc))
    with st.expander("Create a metric", expanded=False):
        operations = [
            "sum",
            "average_per_entity",
            "weighted_mean",
            "ratio",
            "count_distinct",
            "mean",
            "median",
            "snapshot_last",
            "delta",
            "circular_mean",
            "count_rows",
        ]
        aggregation = st.selectbox("Aggregation", operations, key="metric_aggregation")
        with st.form("new_metric_" + aggregation):
            label = st.text_input(
                "Metric name", max_chars=160, placeholder="For example: Sales per distinct order"
            )
            description = st.text_area(
                "Meaning / exposure / limits",
                max_chars=800,
                placeholder="Describe the value grain and the question this definition answers.",
            )
            field = (
                st.selectbox("Value field", nums, format_func=ds.label)
                if aggregation not in {"count_rows", "count_distinct", "ratio"} and nums
                else None
            )
            entity_options = [None] + [e.id for e in model.entities]
            entity = None
            if aggregation in {
                "sum",
                "mean",
                "median",
                "weighted_mean",
                "average_per_entity",
                "count_distinct",
                "snapshot_last",
                "delta",
            }:
                entity = st.selectbox(
                    "Entity / value grain",
                    entity_options,
                    format_func=lambda eid: (
                        "Recorded rows (no deduplication)" if eid is None else model.entity(eid).label
                    ),
                    help="For a sum/mean: deduplicate values constant within this entity. For average per entity: sum row amounts and divide by distinct entities. Define composite identities in Structure & time.",
                )
            weight = (
                st.selectbox("Exposure / weight field", nums, format_func=ds.label)
                if aggregation == "weighted_mean" and nums
                else None
            )
            numerator = denominator = None
            scope = "active_population"
            if aggregation == "ratio":
                mids = [m.id for m in model.metrics]
                numerator = st.selectbox(
                    "Numerator metric", mids, format_func=lambda mid: model.metric(mid).label
                )
                denominator = st.selectbox(
                    "Denominator metric", mids, format_func=lambda mid: model.metric(mid).label
                )
                scope = st.selectbox(
                    "Denominator population",
                    ["active_population", "group"],
                    format_func=lambda s: (
                        "All active rows" if s == "active_population" else "Inside each displayed group"
                    ),
                )
            allocation = (
                st.selectbox(
                    "Attribution when value entities overlap groups",
                    ["none", "full_credit", "equal"],
                    help="None blocks ambiguous entity totals. Equal allocates by distinct observed memberships; it is not causal attribution.",
                )
                if aggregation == "sum"
                else "none"
            )
            policy = st.selectbox(
                "Time policy",
                [None] + [t.id for t in model.time_policies],
                format_func=lambda tid: (
                    "Use selected timestamp policy"
                    if tid is None
                    else ds.label(next(t.field for t in model.time_policies if t.id == tid))
                ),
            )
            transform = st.selectbox(
                "Transform after aggregation",
                ["identity", "log", "sqrt", "zscore", "difference", "percent_change"],
            )
            if st.form_submit_button("Save metric", icon=":material/add:"):
                try:
                    payload = dict(
                        label=label,
                        aggregation=aggregation,
                        field=field,
                        entity=entity,
                        weight=weight,
                        numerator=numerator,
                        denominator=denominator,
                        denominator_scope=scope,
                        allocation=allocation,
                        time_policy=policy,
                        transform=transform,
                        description=description,
                        confirmed=True,
                    )
                    new = Metric.model_validate({"id": "m_" + digest(payload), **payload})
                    add_metric(ds, new)
                    saved("Reusable metric saved.")
                except ValueError as exc:
                    st.error(str(exc))
    st.subheader("Run a metric")
    time_fields = [f.id for f in ds.record.fields if f.role == Role.TIME and not f.excluded]
    time_field = st.selectbox(
        "Time axis",
        [None] + time_fields,
        format_func=lambda fid: "Compare groups / whole population" if fid is None else ds.label(fid),
        key="metric_time",
    )
    groups = st.multiselect(
        "Group by",
        dimensions(ds),
        format_func=ds.label,
        max_selections=2,
        disabled=bool(time_field),
        key="metric_groups",
    )
    period = st.selectbox(
        "Time aggregation",
        ["D", "W", "MS"],
        format_func=lambda p: {"D": "Day", "W": "Week (Monday–Sunday)", "MS": "Month"}[p],
        disabled=not time_field,
        key="metric_period",
    )
    groups = [] if time_field else groups
    readiness = decision(ds, current, groups, time_field, ctx.row_ids)
    for message in readiness.reasons + readiness.requirements:
        st.warning(message)
    if st.button(
        "Compute and add to Discover",
        type="primary",
        icon=":material/query_stats:",
        disabled=readiness.status != "allowed" or bool(ws.job_id),
        key="compute_metric",
    ):
        try:
            result, finding = analyze(ds, ctx, metric_plan(ds, ctx, current.id, groups, time_field, period))
            inv = ws.investigation or Investigation(ctx)
            inv.add_view(result, finding)
            from firstlook.challenges import challenge, eligible

            inv.challenges = [c for c in inv.challenges if c.parent_id != finding.id]
            inv.challenges += [challenge(ds, inv, finding, op) for op in eligible(ds, inv, finding)]
            ws.investigation = inv
            ws.inspect_id = finding.id
            st.switch_page("app_pages/discover.py")
        except ValueError as exc:
            st.error(str(exc))
    if readiness.warnings:
        for warning in readiness.warnings:
            st.caption(warning)

with structure_tab:
    st.subheader("Rows, entities and relationships")
    st.caption(model.grain)
    with st.expander("Define an entity or composite identity"):
        with st.form("entity_definition"):
            entity_label = st.text_input(
                "Entity name", max_chars=150, placeholder="Order line, order, customer, meter…"
            )
            entity_keys = st.multiselect(
                "Identity fields",
                [f.id for f in ds.record.fields if not f.excluded],
                format_func=ds.label,
                max_selections=3,
            )
            if st.form_submit_button("Save entity"):
                try:
                    entity = Entity(
                        id=next(
                            (e.id for e in model.entities if e.keys == entity_keys),
                            "e_" + digest(entity_keys),
                        ),
                        label=entity_label,
                        keys=entity_keys,
                        confirmed=True,
                    )
                    candidate = model.model_copy(deep=True)
                    candidate.entities = [e for e in candidate.entities if e.id != entity.id] + [entity]
                    commit_model(ds, candidate, entity.id, "entity", entity_keys)
                    saved("Entity definition saved.")
                except ValueError as exc:
                    st.error(str(exc))
    with st.form("row_and_model_grain"):
        grain = st.text_input("What does one row represent?", value=model.grain, max_chars=500)
        unique = [None] + [e.id for e in model.entities if e.unique and e.complete]
        grain_entity = st.selectbox(
            "Verified row identity",
            unique,
            index=unique.index(model.grain_entity) if model.grain_entity in unique else 0,
            format_func=lambda eid: "No declared unique identity" if eid is None else model.entity(eid).label,
        )
        group_options = [None] + [
            f.id for f in ds.record.fields if not f.excluded and 3 <= ds.frame[f.id].nunique() < len(ds.frame)
        ]
        model_group = st.selectbox(
            "Keep this entity together in predictive holdout",
            group_options,
            index=group_options.index(model.model_group) if model.model_group in group_options else 0,
            format_func=lambda fid: "No entity holdout constraint declared" if fid is None else ds.label(fid),
            help="Use customer, patient, store or other repeated identity when the task concerns unseen entities. This supersedes random row splitting.",
        )
        if st.form_submit_button("Confirm row and model grain"):
            try:
                candidate = model.model_copy(deep=True)
                candidate.grain = grain
                candidate.grain_entity = grain_entity
                candidate.grain_confirmed = True
                candidate.model_group = model_group
                commit_model(ds, candidate, "table", "grain", grain)
                saved("Row and model grain confirmed.")
            except ValueError as exc:
                st.error(str(exc))
    if model.entities:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Entity": e.label,
                        "Keys": " / ".join(ds.label(k) for k in e.keys),
                        "Distinct": e.distinct,
                        "Complete": e.complete,
                        "Unique per row": e.unique,
                        "Declared": e.confirmed,
                    }
                    for e in model.entities
                ]
            ),
            hide_index=True,
            alt="Entity identities and exact uniqueness/completeness checks",
        )
    with st.expander("Inspect membership or confirm a roll-up path"):
        fields = [f.id for f in ds.record.fields if not f.excluded]
        child = st.selectbox("Child / member", fields, key="relationship_child", format_func=ds.label)
        parent = st.selectbox(
            "Parent / grouping",
            fields,
            key="relationship_parent",
            format_func=ds.label,
            index=min(1, len(fields) - 1),
        )
        if child != parent:
            within = st.multiselect(
                "Hierarchy context",
                [f for f in fields if f not in {child, parent}],
                format_func=ds.label,
                max_selections=2,
                help="For example, City may determine State only within Country. This tests the composite context and child identity.",
            )
            rel = inspect_relationship(ds, child, parent, within)
            st.metric("Children with multiple recorded parents", rel.violating_levels)
            st.caption(
                "Exact check on this upload. A dependency is evidence, not proof of a permanent domain rule."
            )
            if rel.examples:
                st.json(rel.examples, expanded=False)
            if st.button(
                "Confirm this hierarchy", disabled=not rel.strict or not rel.complete, key="confirm_hierarchy"
            ):
                try:
                    candidate = model.model_copy(deep=True)
                    rel.confirmed = True
                    rel.relation = "hierarchy"
                    candidate.relationships = [r for r in candidate.relationships if r.id != rel.id] + [rel]
                    commit_model(ds, candidate, rel.id, "hierarchy", True)
                    saved("Scoped roll-up path confirmed.")
                except ValueError as exc:
                    st.error(str(exc))
    with st.expander("Prediction information boundary"):
        with st.form("availability_definition"):
            unavailable = st.multiselect(
                "Unavailable at prediction time",
                [f.id for f in ds.record.fields if not f.excluded],
                default=[
                    m.field
                    for m in model.meanings
                    if not m.available_at_prediction and not ds.field(m.field).excluded
                ],
                format_func=ds.label,
                help="Mark post-outcome categories as well as numeric measurements. This applies to local baselines and hosted foundation models equally.",
            )
            if st.form_submit_button("Apply predictor availability"):
                candidate = model.model_copy(deep=True)
                for meaning in candidate.meanings:
                    meaning.available_at_prediction = meaning.field not in unavailable
                commit_model(ds, candidate, "table", "prediction_availability", unavailable)
                saved("Predictor information boundary updated.")
    st.subheader("Time is an observation process.")
    st.caption(
        "An absent event day can be zero only under declared complete recording. A missing meter reading is not zero consumption."
    )
    if model.time_policies:
        tid = st.selectbox(
            "Timestamp policy",
            [t.id for t in model.time_policies],
            format_func=lambda tid: ds.label(next(t.field for t in model.time_policies if t.id == tid)),
            key="time_policy_select",
        )
        time = next(t for t in model.time_policies if t.id == tid)
        if time.observed_interval_seconds:
            st.caption(
                f"Most frequent observed interval: {time.observed_interval_seconds / 86400:,.3g} days. This does not establish the expected schedule."
            )
        with st.form("time_policy_" + tid):
            kinds = ["unknown", "event", "instant", "interval", "state", "cumulative"]
            frequencies = ["unknown", "D", "2D", "W", "MS"]
            gaps = ["preserve", "zero", "forward_fill", "interpolate"]
            time_kind = st.selectbox("Observation process", kinds, index=kinds.index(time.kind))
            frequency = st.selectbox(
                "Expected schedule", frequencies, index=frequencies.index(time.expected_frequency)
            )
            series = st.multiselect(
                "Series identity fields",
                [f.id for f in ds.record.fields if not f.excluded and f.id != time.field],
                default=time.series,
                format_func=ds.label,
                max_selections=3,
            )
            calendar = st.selectbox(
                "Calendar", ["calendar", "business"], index=0 if time.calendar == "calendar" else 1
            )
            gap = st.selectbox("Absent scheduled observation", gaps, index=gaps.index(time.gap_policy))
            coverage = st.checkbox(
                "Recording coverage is complete through the declared date", value=time.coverage_complete
            )
            complete = st.date_input(
                "Last complete date",
                value=cast(Any, pd.Timestamp(time.complete_through or ds.frame[time.field].max()).date()),
            )
            max_gap = st.number_input(
                "Maximum carry / interpolation gap (periods)",
                min_value=0,
                max_value=31,
                value=time.max_gap_periods,
            )
            if st.form_submit_button("Confirm time policy"):
                try:
                    candidate = model.model_copy(deep=True)
                    t = TimePolicy.model_validate(
                        {
                            **next(p for p in candidate.time_policies if p.id == tid).model_dump(mode="json"),
                            "kind": time_kind,
                            "expected_frequency": frequency,
                            "series": series,
                            "calendar": calendar,
                            "gap_policy": gap,
                            "coverage_complete": coverage,
                            "complete_through": str(complete) if coverage else None,
                            "max_gap_periods": max_gap,
                            "confirmed": True,
                        }
                    )
                    candidate.time_policies = [t if old.id == tid else old for old in candidate.time_policies]
                    commit_model(ds, candidate, tid, "time_policy", t.model_dump(mode="json"))
                    saved("Time policy confirmed.")
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.caption("No parsed timestamp field is available.")

with contract_tab:
    st.subheader("A portable, reviewable analytical contract.")
    st.caption(
        "No data lineage is tracked. The contract stores meanings, operational definitions, scoped evidence and explicit decisions. It never alters uploaded values."
    )
    st.code(model.revision, language=None)
    st.download_button(
        "Download semantic contract",
        export_contract(ds),
        "first-look-contract.json",
        "application/json",
        icon=":material/download:",
        key="download_contract",
    )
    uploaded = st.file_uploader(
        "Import a contract for this exact dataset", type=["json"], key="contract_upload"
    )
    if uploaded and st.button("Validate and apply contract", key="import_contract"):
        try:
            import_contract(ds, uploaded.getvalue())
            saved("Contract imported and structurally validated.")
        except ValueError as exc:
            st.error(str(exc))
    with st.expander("Assertions and evidence"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Subject": a.subject,
                        "Property": a.property,
                        "Origin": a.origin,
                        "Confirmed": a.confirmed,
                        "Method": a.method,
                    }
                    for a in model.assertions
                ]
            ),
            hide_index=True,
            alt="Semantic assertion ledger with origin and confirmation status",
        )
    with st.expander("Full contract"):
        st.json(model.model_dump(mode="json"), expanded=False)
