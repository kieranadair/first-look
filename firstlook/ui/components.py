"""A small consistent visual language for views, evidence and interactions."""

from __future__ import annotations

import streamlit as st
from typing import Any, cast

from firstlook.contracts import Finding
from firstlook.discovery import Investigation
from firstlook.methods import rule_details
from firstlook.state import pin
from firstlook.ui.runtime import workspace
from firstlook.visualization.compiler import compile_chart, selected_rows
from firstlook.visualization.layout import chart_dimensions

STATUS = {
    "changed": ("Changed under this check", "orange"),
    "similar": ("Similar under this check", "blue"),
    "insufficient": ("Insufficient support", "gray"),
    "not_checked": ("Diagnostic view", "gray"),
}


def page_header(title: str, subtitle: str, compact: bool = True):
    if compact:
        st.header(title)
        st.caption(subtitle)
    else:
        st.caption("First Look · visual investigation")
        st.title(title)
        st.markdown(subtitle)
    ws = workspace()
    if ws.dataset:
        filtered = ws.rows is not None and not ws.replay
        context = (
            (
                f"{len(ws.context().row_ids):,} of {ws.dataset.record.rows:,} rows · filtered population"
                if filtered
                else f"{len(ws.context().row_ids):,} active rows"
            )
            if len(ws.dataset.frame)
            else "Saved evidence"
        )
        label = f"**{ws.dataset.record.name}** · {context} · {ws.dataset.record.columns} fields" + (
            " · Recorded replay" if ws.replay else ""
        )
        if not filtered:
            st.caption(label)
        else:
            row = st.container(horizontal=True, vertical_alignment="center", gap="small")
            row.caption(label)
            if row.button(
                "Return to reference" if ws.return_state else "Reset selection",
                icon=":material/filter_alt_off:",
                type="tertiary",
                key="global_reset",
            ):
                if ws.return_state:
                    ws.return_to_anchor()
                else:
                    ws.rows = None
                    ws.invalidate()
                st.rerun()


def render_chart(
    finding: Finding, inv: Investigation, suffix: str = "", selection: bool = False, height: int = 310
):
    from firstlook.exploration import display_result

    result = display_result(inv, finding.result_id)
    if selection and not workspace().replay:
        representation_controls(finding, result, suffix or finding.id, height)
    return chart_view(finding.chart, result, suffix or finding.id, selection, height)


def representation_controls(finding, result, key, height):
    """Choose a finite representation; pins retain the selected chart contract."""
    original = finding.chart
    changes = {}
    if original.template in {"histogram", "frequency_polygon"} and not any(
        "group" in row for row in result.records
    ):
        choice = (
            st.segmented_control(
                "Distribution display",
                ["Histogram", "Frequency polygon"],
                default="Frequency polygon" if original.template == "frequency_polygon" else "Histogram",
                key="representation_" + key,
            )
            or "Histogram"
        )
        changes = {"template": "frequency_polygon" if choice == "Frequency polygon" else "histogram"}
        if choice == "Frequency polygon":
            st.caption(
                "Same equal-width bins and quantity. Straight segments connect bin midpoints; this is not a smoothed density estimate."
            )
    elif result.metadata.get("partwhole_verified") and result.metadata.get("full_original_parts"):
        from firstlook.visualization.composition import amount_records, labelled_part_capacity

        parts = amount_records(result)
        capacity = labelled_part_capacity(height)
        labels = ["Cumulative share", "Ranked parts", "Treemap overview"]
        default = "Treemap overview" if len(parts) > capacity else "Ranked parts"
        if original.template == "treemap":
            default = "Treemap overview"
        elif original.template == "bar":
            default = "Ranked parts"
        choice = (
            st.segmented_control("Contribution display", labels, default=default, key="representation_" + key)
            or default
        )
        template = {"Cumulative share": "line", "Ranked parts": "bar", "Treemap overview": "treemap"}[choice]
        changes = {
            "template": template,
            "value_field": "value" if template == "line" else "amount",
            "zero_baseline": template == "bar",
            "x_label": "Original categories, ranked by contribution"
            if template == "line"
            else "Contribution amount",
            "y_label": "Cumulative share" if template == "line" else "Original category",
            "alt": (
                "Cumulative share across original categories ranked by contribution."
                if template == "line"
                else "Original nonnegative additive contribution amounts by category, encoded by "
                + (
                    "rectangle area; no spatial or colour-valued measure is implied."
                    if template == "treemap"
                    else "bar length from zero."
                )
            ),
        }
        st.caption(
            f"{len(parts)} original parts · labelled-row budget {capacity} for this panel. This is a display-fit choice, not a universal treemap threshold."
        )
    if changes and any(getattr(original, k) != v for k, v in changes.items()):
        from firstlook.contracts import digest

        finding.chart = original.model_copy(
            update={**changes, "id": digest([result.id, changes, "chart-policy-1"])}
        )


def chart_view(spec, result, key: str, selection: bool = False, height: int = 310):
    width, height = chart_dimensions(spec, result, height)
    compiled = compile_chart(spec, result, st.context.theme.type == "dark", width=width, height=height)
    selectable = selection and any(compiled.row_map.values())
    event = st.echarts_chart(
        compiled.options,
        key=f"chart_{key}_{compiled.mapping_hash}",
        height=height,
        width=width,
        on_select=cast(Any, "rerun" if selectable else "ignore"),
        alt=spec.alt,
        renderer="canvas" if len(result.records) > 1500 else "svg",
    )
    if spec.template == "box":
        st.caption(
            result.metadata.get(
                "whisker_convention",
                "Whiskers show observed minimum and maximum; boxes show the middle half. These are range boxes, not 1.5-IQR fences.",
            )
        )
    elif spec.template == "treemap":
        zero = sum(r.get("amount") == 0 for r in result.records)
        st.caption(
            f"Area encodes contribution amount. Position and colour do not encode another variable. {zero} zero-area parts remain in the exact values; small labels may be hidden. Use ranked parts or the table for precise comparisons."
        )
    if result.metadata.get("time_axis") and any(r.get("complete") is False for r in result.records):
        st.caption(
            "Some periods have incomplete or unconfirmed recording coverage. Recorded totals are not necessarily complete-period totals; missing intervals remain unknown."
        )
    ws = workspace()
    if selectable and event is not None and ws.dataset and not ws.replay:
        chosen = selected_rows(event, compiled, set(ws.context().row_ids))
        active_brush = bool(event.get("selection", {}).get("areas"))
        if chosen:
            st.caption(
                f"{len(chosen):,} displayed source members selected. Preview a cohort to compare it while retaining this reference."
            )
            with st.container(horizontal=True, gap="small"):
                if st.button("Compare selected rows", key="compare_" + key, icon=":material/compare_arrows:"):
                    from firstlook.comparison import preview

                    if (
                        result.plan.operation == "metric"
                        and result.metadata.get("definition", {}).get("aggregation") == "delta"
                    ):
                        st.warning(
                            "Counter marks depend on interval endpoints. Endpoint unions cannot define a safe cohort; select recorded rows or an entity predicate in Compare."
                        )
                    else:
                        preview(
                            ws,
                            chosen,
                            result.id,
                            compiled.mapping_hash,
                            scope=result.metadata.get("selection_semantics", "Displayed mark members only"),
                        )
                        st.switch_page("app_pages/compare.py")
                if st.button("Apply selected rows", key="apply_" + key, icon=":material/filter_alt:"):
                    from firstlook.comparison import preview

                    if (
                        result.plan.operation == "metric"
                        and result.metadata.get("definition", {}).get("aggregation") == "delta"
                    ):
                        st.warning(
                            "An endpoint-row union can create unselected counter intervals. Use a recorded-row predicate in Compare."
                        )
                    else:
                        preview(ws, chosen, result.id, compiled.mapping_hash)
                        ws.begin_filtered()
                        st.rerun()
            with st.expander("Preview selected records"):
                table = ws.dataset.frame.loc[chosen].rename(
                    columns={f.id: f.name for f in ws.dataset.record.fields}
                )
                st.dataframe(table.head(100), hide_index=True, alt="Preview of selected source records")
        elif active_brush:
            st.caption("This brush contains no supported points. No filter was applied.")
    return compiled


def finding_card(finding: Finding, inv: Investigation, lead: bool = False):
    ws = workspace()
    result = inv.results[finding.result_id]
    with st.container(border=True, height="stretch", key="card_" + finding.id):
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.caption(finding.family.replace("_", " ").capitalize())
            altered = any(c.parent_id == finding.id and c.status == "changed" for c in inv.challenges)
            if altered:
                st.badge("Changes under scrutiny", color="orange", icon=":material/compare_arrows:")
            elif finding.claim_type == "model-derived":
                st.badge("Held-out diagnostic", color="blue")
        if lead:
            st.subheader(finding.title)
        else:
            st.markdown("#### " + finding.title)
        st.markdown(finding.observation)
        render_chart(finding, inv, height=300 if lead else 280)
        st.caption(scope_caption(result))
        with st.container(horizontal=True, gap="xsmall"):
            if st.button("Inspect", key="inspect_" + finding.id, icon=":material/open_in_full:"):
                ws.inspect_id = finding.id
                ws.opened.add(finding.id)
                st.switch_page("app_pages/inspect.py")
            if st.button("Challenge", key="challenge_" + finding.id, icon=":material/compare_arrows:"):
                ws.challenge_id = finding.id
                st.switch_page("app_pages/challenge.py")
            pinned = any(p["finding"]["id"] == finding.id for p in ws.pins)
            if st.button(
                "Pinned" if pinned else "Pin",
                key="pin_" + finding.id,
                icon=":material/bookmark:",
                disabled=pinned,
            ):
                pin(ws, finding.id)
                st.toast("Finding and completed checks added to Evidence.")
                st.rerun()


def prepared_question_panel():
    from firstlook.questions import QuestionIntent
    from firstlook.question_workflow import TASKS
    from firstlook.semantic.model import get_model
    from firstlook.semantics import dimensions, measures
    from firstlook.ui.runtime import start_prepared_question

    ws = workspace()
    review = ws.question_review
    if not review or not ws.dataset or review.get("context") != ws.context().id:
        return
    with st.container(border=True):
        st.markdown("**Check the interpretation before running it**")
        st.markdown(review["question"])
        st.caption(review["method"] + " · " + review["status"])
        if review.get("provider_error"):
            st.caption(
                "Provider error: " + review["provider_error"] + " Local interpretation is shown separately."
            )
        if review.get("clarification"):
            st.info(review["clarification"])
        if review.get("executed"):
            st.caption(
                "This interpretation was executed. Its result and decision record are preserved in Judgments and Evidence."
            )
            return
        ds = ws.dataset
        intent = QuestionIntent.model_validate(review["intent"])
        options = list(TASKS)
        operation = st.selectbox(
            "Analytical task",
            options,
            index=options.index(intent.operation) if intent.operation in options else 0,
            format_func=lambda k: k.replace("_", " ").capitalize(),
            key="intent_task_" + review["id"],
        )
        st.caption(TASKS[operation])
        nums, cats = measures(ds), dimensions(ds)
        times = [f.id for f in ds.record.fields if f.role.value == "timestamp" and not f.excluded]

        def field(label, allowed, position, name):
            if not allowed:
                st.caption("No eligible field for " + label.lower())
                return None
            chosen = (
                intent.fields[position]
                if len(intent.fields) > position and intent.fields[position] in allowed
                else allowed[0]
            )
            return st.selectbox(
                label,
                allowed,
                index=allowed.index(chosen),
                format_func=ds.label,
                key="intent_" + name + "_" + review["id"],
            )

        fields, metric_id, group_by, time_field, within = [], None, [], None, None
        first, second = st.columns(2, gap="small")
        if operation in {"relationship", "group_shape", "category_relationship", "time"}:
            left = nums if operation == "relationship" else times if operation == "time" else cats
            right = cats if operation == "category_relationship" else nums
            with first:
                a = field("First field", left, 0, "first")
            with second:
                b = field("Second field", right, 1, "second")
            fields = [a, b] if a and b else []
            if operation == "relationship":
                groups = [None] + cats
                default = review.get("group_field")
                within = st.selectbox(
                    "Optional within-group check",
                    groups,
                    index=groups.index(default) if default in groups else 0,
                    format_func=lambda v: ds.label(v) if v else "Pooled relationship only",
                    key="intent_within_" + review["id"],
                )
        elif operation in {"distribution", "frequency"}:
            chosen = field("Field", nums if operation == "distribution" else cats, 0, "single")
            fields = [chosen] if chosen else []
        elif operation == "metric":
            model = get_model(ds)
            ids = [m.id for m in model.metrics]
            metric_id = st.selectbox(
                "Existing metric definition",
                ids,
                index=ids.index(intent.metric_id) if intent.metric_id in ids else 0,
                format_func=lambda v: model.metric(v).label,
                key="intent_metric_" + review["id"],
            )
            group_by = st.multiselect(
                "Group by",
                cats,
                default=[v for v in intent.group_by if v in cats],
                max_selections=2,
                format_func=ds.label,
                key="intent_groups_" + review["id"],
            )
            time_field = st.selectbox(
                "Timestamp",
                [None] + times,
                format_func=lambda v: ds.label(v) if v else "No time aggregation",
                key="intent_time_" + review["id"],
            )
        period = intent.period
        if operation == "metric" and time_field:
            period = (
                st.segmented_control(
                    "Period", ["D", "W", "MS"], default=intent.period, key="intent_period_" + review["id"]
                )
                or intent.period
            )
        st.caption(
            "Your confirmation selects a descriptive analysis. Python rechecks its semantic permissions; causes, gap filling and metric meanings are not inferred."
        )
        if st.button(
            "Run this interpretation",
            type="primary",
            disabled=bool(ws.job_id) or ws.replay,
            key="execute_intent_" + review["id"],
        ):
            try:
                corrected = QuestionIntent.model_validate(
                    {
                        "operation": operation,
                        "fields": fields,
                        "metric_id": metric_id,
                        "group_by": group_by,
                        "time_field": time_field,
                        "period": period,
                    }
                )
                start_prepared_question(ws, review, corrected.model_dump(mode="json"), within)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def claim_review_panel(audit, key):
    if not audit:
        return
    st.caption(
        "Claim review · Python checks references and rejects generated numerical/causal assertions. Jev's semantic review is a model signal."
    )
    st.dataframe(
        [
            {"Claim": c["text"], "Status": c["status"].replace("_", " "), "Reason": c["reason"]}
            for c in audit["claims"]
        ],
        hide_index=True,
        alt="Claim support and population-scope review",
    )
    if audit.get("provider_note"):
        st.caption("Review provider: " + audit["provider_note"])
    st.page_link(
        "app_pages/judgments.py",
        label="Inspect judgment definitions and records",
        icon=":material/fact_check:",
    )


def evidence_inspector(finding: Finding, inv: Investigation, compact: bool = False):
    result = inv.results[finding.result_id]
    st.markdown("**Reading this evidence**")
    st.caption(scope_caption(result))
    if not compact:
        st.markdown(f"**Question:** {finding.title}")
    if result.metadata.get("definition"):
        with st.container(gap="xsmall"):
            st.markdown("**Analytical definition**")
            definition = result.metadata["definition"]
            st.caption(definition.get("description") or definition["aggregation"].replace("_", " "))
            dataset = workspace().dataset
            model = dataset.record.semantic_model if dataset else None
            grain = "Declared entity" if definition.get("entity") else "Recorded rows"
            if model:
                grain = next(
                    (entity.label for entity in model.entities if entity.id == definition.get("entity")),
                    grain,
                )
            st.caption(
                f"Value grain: {grain} · Denominator scope: "
                + ("each group" if definition.get("denominator_scope") == "group" else "current population")
            )
            st.caption("Transformations apply after aggregation.")
    for limitation in dict.fromkeys([*finding.limitations, *result.warnings]):
        st.caption(limitation)
    with st.expander("Chart safeguards and research"):
        from firstlook.visualization.guidance import chart_rule_ids

        for rule in rule_details(chart_rule_ids(finding.chart, result)):
            st.caption(rule["requirement"])
            st.markdown(f"[{rule['name']}]({rule['source']}) · {rule['evidence']}")
        st.caption(
            "These sources motivate conditional design patterns. They do not validate a universal chart selector or this app’s productivity."
        )
    values = st.expander("Exact computed values") if compact else st.container()
    with values:
        st.caption("Statistics, chart and exported values share this result. Showing up to 200 records.")
        st.dataframe(
            result.frame().drop(columns=["row_ids", "row_id"], errors="ignore").head(200),
            hide_index=True,
            height=230,
            alt="Computed evidence behind the current finding",
        )
    with st.expander("Contract and execution details"):
        st.json(
            {
                "plan": result.plan.model_dump(mode="json"),
                "chart": finding.chart.model_dump(mode="json"),
                "support": result.support,
                "metrics": result.metrics,
                "warnings": result.warnings,
                "semantic_metadata": result.metadata,
            }
        )


def workflow_note(step: str, purpose: str, action: str):
    """Short, visible orientation; never hides essential interpretation in an expander."""
    with st.container(gap="xsmall"):
        st.markdown(f"**{step} · {purpose}**")
        st.caption(action)


def scope_caption(result):
    scope = result.metadata.get("analysis_scope", {})
    text = f"{result.support:,} supporting rows · {result.missing:,} missing"
    if scope:
        text += f" · {scope['statistical_rows']:,} statistical rows / {scope['displayed_marks']:,} displayed marks"
    if result.metadata.get("ecdf_error") is not None:
        text += f" · max cumulative display error {result.metadata['ecdf_error']:.4g}"
    return text


def comparison_board(bundle, key="comparison"):
    entity_note = (
        f"{bundle.spec.entity_overlap:,} overlapping entities"
        if bundle.spec.entity_overlap is not None
        else "entity overlap not evaluated"
    )
    st.caption(
        f"Reference: {bundle.spec.reference.replace('_', ' ')} · Denominators: {bundle.spec.denominator.replace('_', ' ')} · Selection: {bundle.spec.selection.policy.replace('_', ' ')}"
    )
    st.caption(f"{bundle.spec.row_overlap:,} overlapping rows · {entity_note}")
    cumulative = bundle.spec.operation == "ecdf"
    grid = st.grid(3 if cumulative else 2, min_column_width=260 if cumulative else 350, gap="small")
    for view in bundle.views:
        with grid.cell():
            with st.container(border=True, height="stretch"):
                st.markdown(f"**{view.role} · {len(view.context.row_ids):,} population rows**")
                st.caption(scope_caption(view.result))
                chart_view(
                    view.finding.chart,
                    view.result,
                    f"{key}_{view.role}_{bundle.id}",
                    height=280 if cumulative else 300,
                )
                definition = view.result.metadata.get("definition")
                if definition:
                    st.caption(
                        definition.get("description")
                        or definition["label"] + " · " + definition["aggregation"].replace("_", " ")
                    )
                    st.caption(
                        f"Denominator population: {view.result.metadata.get('denominator_population_rows', len(view.context.row_ids)):,} rows. Membership and valid contributors can differ."
                    )
    if cumulative and bundle.summary:
        with grid.cell():
            with st.container(border=True, height="stretch"):
                st.markdown("**Differences across the distribution**")
                st.caption(
                    "Selected minus reference at matched quantiles. Full source values and the linear quantile estimator; no significance claim."
                )
                from firstlook.visualization.quantiles import quantile_deviation

                contrast, contrast_chart = quantile_deviation(bundle.views[0].result, bundle.summary)
                contrast.metadata.update(
                    source_contexts=[v.context.id for v in bundle.views],
                    source_results=[v.result.id for v in bundle.views],
                )
                chart_view(contrast_chart, contrast, f"{key}_quantiles_{bundle.id}", height=280)
                st.caption(
                    "Above zero: selected quantile higher. Below zero: reference quantile higher. Only the saved percentiles are shown, in the source measure's units."
                )
                with st.expander("Exact matched quantiles"):
                    st.dataframe(
                        bundle.summary,
                        hide_index=True,
                        alt="Exact full-source matched quantiles and differences",
                    )
    elif bundle.summary:
        st.dataframe(
            bundle.summary,
            hide_index=True,
            height=min(240, 38 + 35 * len(bundle.summary)),
            alt="Exact comparison differences and support; no significance claim",
        )
    for message in bundle.exclusions:
        st.caption(message)
    ws = workspace()
    if bundle.spec.operation == "ecdf" and ws.dataset is not None and not ws.dataset.frame.empty:
        from firstlook.numerics import threshold_probability

        with st.form("threshold_" + key + bundle.id, border=False):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                threshold = st.number_input(
                    "Exact at-or-below threshold",
                    value=float(bundle.summary[len(bundle.summary) // 2]["selected"]),
                    key="threshold_value_" + key + bundle.id,
                )
                query = st.form_submit_button("Query source values")
            if query:
                from firstlook.comparison import dataset_for_bundle

                source = dataset_for_bundle(bundle, ws.dataset)
                st.dataframe(
                    [
                        {
                            "Population": v.role,
                            **threshold_probability(
                                source.frame.loc[v.context.row_ids, bundle.spec.measure].dropna(),
                                threshold,
                            ),
                        }
                        for v in bundle.views
                    ],
                    hide_index=True,
                    alt="Exact source cumulative probabilities, independent of display compression",
                )
    if bundle.model_slice:
        st.markdown("**Recorded held-out model evidence**")
        st.caption(bundle.model_slice["interpretation"])
        st.dataframe(
            [
                {k: v for k, v in bundle.model_slice[role].items() if k != "row_ids"} | {"Population": role}
                for role in ["Selected", "Reference"]
            ],
            hide_index=True,
            alt="Error summaries for the original held-out memberships",
        )
    if bundle.interpretation.get("synthesis"):
        st.markdown("**Terra’s proposed interpretation**")
        st.markdown(bundle.interpretation["synthesis"]["interpretation"])
        claim_review_panel(bundle.interpretation.get("claim_review"), key)
        for question in bundle.interpretation["synthesis"].get("next_questions", []):
            st.caption("Next question: " + question)
    elif bundle.interpretation.get("note"):
        st.caption(bundle.interpretation["note"])
    for check in bundle.checks:
        st.caption(check.operation.replace("_", " ") + " · " + check.status + ": " + check.summary)
