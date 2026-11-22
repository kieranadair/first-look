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


def page_header(title: str, subtitle: str):
    st.caption("FIRST LOOK  /  VISUAL INVESTIGATION")
    st.title(title)
    st.markdown(subtitle)
    ws = workspace()
    if ws.dataset:
        context = f"{len(ws.context().row_ids):,} active rows" if len(ws.dataset.frame) else "Saved evidence"
        st.caption(
            f"{ws.dataset.record.name}  ·  {context}  ·  {ws.dataset.record.columns} fields"
            + ("  ·  Recorded replay" if ws.replay else "")
        )
        if ws.rows is not None and not ws.replay:
            if st.button("Reset selection", icon=":material/filter_alt_off:", key="global_reset"):
                ws.rows = None
                ws.invalidate()
                st.rerun()


def render_chart(
    finding: Finding, inv: Investigation, suffix: str = "", selection: bool = False, height: int = 310
):
    result = inv.results[finding.result_id]
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
                f"{len(chosen):,} source rows selected. Applying this subset creates a new analytical context."
            )
            if st.button("Apply selected rows", key="apply_" + key, icon=":material/filter_alt:"):
                ws.rows = chosen
                ws.invalidate()
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
            st.caption(finding.family.replace("_", " ").upper())
            altered = any(c.parent_id == finding.id and c.status == "changed" for c in inv.challenges)
            if altered:
                st.badge("Changes under scrutiny", color="orange", icon=":material/compare_arrows:")
            elif finding.claim_type == "model-derived":
                st.badge("Held-out diagnostic", color="blue")
        st.subheader(finding.title)
        st.markdown(finding.observation)
        render_chart(finding, inv, height=360 if lead else 290)
        st.caption(
            f"{result.support:,} supporting rows  ·  {result.missing:,} missing"
            + ("  ·  Sampled" if result.metadata.get("sampled") else "")
        )
        with st.container(horizontal=True, gap="xsmall"):
            if st.button("Inspect", key="inspect_" + finding.id, icon=":material/open_in_full:"):
                ws.inspect_id = finding.id
                st.rerun()
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


def evidence_inspector(finding: Finding, inv: Investigation):
    result = inv.results[finding.result_id]
    st.caption("WHY THIS VIEW")
    st.markdown(f"**Question:** {finding.title}")
    st.caption("Statistics, chart and exported values share this result artifact.")
    if result.metadata.get("definition"):
        with st.container(border=True):
            st.markdown("**Analytical definition**")
            definition = result.metadata["definition"]
            st.caption(definition.get("description") or definition["aggregation"].replace("_", " "))
            st.caption(
                "Value grain: "
                + (definition.get("entity") or "recorded rows")
                + " · denominator scope: "
                + definition.get("denominator_scope", "active_population")
            )
            st.caption(
                "Transformation stage: after aggregation · contract " + result.metadata["semantic_revision"]
            )
            st.json(definition, expanded=False)
    for rule in rule_details(finding.chart.rules):
        st.caption(f"{rule['id']} · {rule['name']}. {rule['requirement']}")
    with st.expander("Research behind these constraints"):
        for rule in rule_details(finding.chart.rules):
            st.markdown(f"[{rule['name']}]({rule['source']}) · {rule['evidence']}")
        st.caption(
            "These sources motivate conditional design patterns. They do not validate a universal chart selector or this app’s productivity."
        )
    st.dataframe(
        result.frame().drop(columns=["row_ids"], errors="ignore").head(200),
        hide_index=True,
        alt="Computed evidence behind the current finding",
    )
    with st.expander("Contract and provenance"):
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
    for limitation in finding.limitations:
        st.caption(limitation)
