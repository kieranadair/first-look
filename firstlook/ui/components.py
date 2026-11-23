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
    return chart_view(finding.chart, result, suffix or finding.id, selection, height)


def chart_view(spec, result, key: str, selection: bool = False, height: int = 310):
    compiled = compile_chart(spec, result, st.context.theme.type == "dark")
    selectable = selection and any(compiled.row_map.values())
    event = st.echarts_chart(
        compiled.options,
        key=f"chart_{key}_{compiled.mapping_hash}",
        height=height,
        on_select=cast(Any, "rerun" if selectable else "ignore"),
        alt=spec.alt,
        renderer="canvas" if len(result.records) > 1500 else "svg",
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
        for rule in rule_details(finding.chart.rules):
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
                st.dataframe(
                    bundle.summary,
                    hide_index=True,
                    height=218,
                    column_config={
                        "quantile": st.column_config.NumberColumn("q", format="%.2f"),
                        "selected": st.column_config.NumberColumn("Selected", format="%.3g"),
                        "reference": st.column_config.NumberColumn("Reference", format="%.3g"),
                        "difference": st.column_config.NumberColumn("Difference", format="%.3g"),
                    },
                    alt="Source quantile differences beside both cumulative curves",
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
        for question in bundle.interpretation["synthesis"].get("next_questions", []):
            st.caption("Next question: " + question)
    elif bundle.interpretation.get("note"):
        st.caption(bundle.interpretation["note"])
    for check in bundle.checks:
        st.caption(check.operation.replace("_", " ") + " · " + check.status + ": " + check.summary)
