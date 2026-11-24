"""A compact prepared overview and a focused review workbench, using native Streamlit."""

import json

import pandas as pd
import streamlit as st

from firstlook.contracts import digest
from firstlook.preparation import (
    build_preparation,
    candidate_bundle,
    change_state,
    preparation_readiness,
    selection_closure,
)
from firstlook.preparation_connected import preparation_sources
from firstlook.preparation_contracts import PreparationDraft
from firstlook.semantic.model import get_model
from firstlook.ui.runtime import apply_prepared_bundle, settings, start_preparation


def current_draft(ws):
    scope = digest([ws.dataset.record.fingerprint, ws.dataset.record.parser, ws.preparation_generation])
    if st.session_state.get("preparation_ui_scope") != scope:
        for key in [
            "preparation_goal",
            "preparation_notes",
            "preparation_context_connected",
            "preparation_clear_dictionary",
            "preparation_start_group",
        ]:
            st.session_state.pop(key, None)
        st.session_state.preparation_ui_scope = scope
    if not ws.preparation:
        ws.preparation = build_preparation(ws.dataset).model_dump(mode="json")
    return PreparationDraft.model_validate(ws.preparation)


def cached_readiness(ws, goal):
    context = ws.context()
    key = digest([context.id, goal])
    if ws.preparation_readiness.get("key") != key:
        ws.preparation_readiness = {
            "key": key,
            "value": preparation_readiness(ws.dataset, goal, context.row_ids),
        }
    return ws.preparation_readiness["value"]


def _automatic_changed(ws, key):
    ws.automatic_preparation = bool(st.session_state[key])
    if ws.automatic_preparation:
        st.session_state.external_ok = True


def preparation_overview(ws):
    draft = current_draft(ws)
    ready = cached_readiness(ws, draft.goal)
    with st.container(border=True):
        left, right = st.columns([1.65, 1], gap="medium")
        with left:
            st.markdown("**Your analytical preparation**")
            st.caption(draft.summary)
            st.caption(
                f"{len(ready['ready'])} metric definitions can run now · {len([c for c in draft.changes if c.id not in draft.applied])} proposed definitions · deeper meanings can be refined as you explore."
            )
            st.page_link(
                "app_pages/preparation.py",
                label="Review the prepared understanding",
                icon=":material/auto_awesome:",
            )
        with right:
            cfg = settings()
            key = "automatic_preparation_" + digest(
                [draft.dataset, draft.parsing_scope, ws.preparation_generation]
            )
            st.checkbox(
                "Automatically prepare with connected models",
                key=key,
                value=ws.automatic_preparation,
                on_change=_automatic_changed,
                args=(ws, key),
                disabled=not (cfg.available("terra") or cfg.available("jev")),
                help="Enables external analysis for this dataset. Terra receives bounded summaries, category/identifier examples, selected source witnesses and supplied notes. Jev reviews supplied definitions and passages. Free-text column values are omitted. One automatic request; further requests are explicit.",
                persist_state="session",
            )
            st.caption(
                "Local preparation is automatic. Connected preparation runs once in the background after you enable it; it prepares suggestions for review."
            )
            if (
                ws.automatic_preparation
                and not ws.preparation_requests
                and not ws.job_id
                and st.session_state.get("external_ok")
            ):
                try:
                    start_preparation(ws)
                    st.rerun()
                except ValueError as exc:
                    st.warning(str(exc))


def review_bundle(ws):
    draft = current_draft(ws)
    ds = ws.dataset
    ready = cached_readiness(ws, draft.goal)
    st.caption(
        ready["status"]
        + ". Review only the definitions needed for your next question. Unrelated time and prediction settings can wait."
    )
    if draft.goal:
        st.markdown("**Working question:** " + draft.goal)
    st.markdown(draft.summary)
    if ws.preparation_undo and ws.dataset.context().semantics == ws.preparation_undo["after"]:
        from firstlook.ui.runtime import undo_preparation

        if st.button("Undo the last confirmed bundle", key="undo_preparation", icon=":material/undo:"):
            undo_preparation(ws)
            st.rerun()
    for error in draft.errors:
        st.warning(error)
    main, aside = st.columns([1.45, 1], gap="medium")
    with main:
        st.subheader("Review related definitions together")
        st.caption(
            "Checked rows are proposals you are choosing to confirm. Required component definitions are listed below before you apply the bundle."
        )
        all_changes = st.toggle("Show all proposals", key="preparation_all", value=False)
        candidates = [c for c in draft.changes if c.id not in draft.applied and (all_changes or c.suggested)]
        if not candidates:
            candidates = [c for c in draft.changes if c.id not in draft.applied][:16]
        if candidates:
            table = pd.DataFrame(
                [
                    {
                        "Use": bool(c.suggested and change_state(ds, draft, c) == "ready"),
                        "id": c.id,
                        "Definition": c.label,
                        "Kind": c.kind,
                        "Source": c.origin,
                        "State": change_state(ds, draft, c),
                    }
                    for c in candidates
                ]
            )
            edited = st.data_editor(
                table,
                hide_index=True,
                height=340,
                key="prepared_definitions_"
                + digest([draft.model_dump(mode="json"), ds.context().semantics, all_changes]),
                disabled=["id", "Definition", "Kind", "Source", "State"],
                column_config={
                    "id": None,
                    "Use": st.column_config.CheckboxColumn(width="small"),
                    "Definition": st.column_config.TextColumn(width="large"),
                },
                alt="Proposed analytical definitions with explicit selection and current applicability",
            )
            ids = list(edited.loc[edited.Use, "id"])
            chosen = selection_closure(draft, ids) if ids else []
            added = [c for c in chosen if c.id not in ids]
            if added:
                st.caption(
                    "Required components included in this review: " + "; ".join(c.label for c in added)
                )
            if chosen:
                st.caption(
                    f"Confirming {len(chosen)} definitions updates the contract once. Review their reasons and source evidence alongside this table."
                )
            if st.button(
                "Confirm selected definitions",
                type="primary",
                icon=":material/done_all:",
                disabled=not chosen or ws.replay,
                key="apply_prepared_bundle",
            ):
                try:
                    apply_prepared_bundle(ws, ids)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if st.button("Check the selected bundle", disabled=not chosen, key="check_prepared_bundle"):
                try:
                    candidate, _ = candidate_bundle(ds, draft, ids)
                    check = preparation_readiness(candidate, draft.goal, ws.context().row_ids)
                    st.success(
                        f"This bundle is valid. {len(check['ready'])} metric definitions would be eligible under its reviewed meanings."
                    )
                except ValueError as exc:
                    st.error(str(exc))
        else:
            st.success(
                "The current draft has no unapplied definitions. You can explore or add context for a more specific question."
            )
        if st.button("Refresh the local draft", key="refresh_preparation", disabled=bool(ws.job_id)):
            sources = preparation_sources(
                ws.preparation_inputs.get("notes", ""), ws.preparation_inputs.get("dictionary", "")
            )
            ws.preparation = build_preparation(ds, ws.preparation_inputs.get("goal", ""), sources).model_dump(
                mode="json"
            )
            st.rerun()
        st.caption(
            "Refresh recomputes proposals around your current declarations. It makes no provider call."
        )
    with aside:
        st.subheader("Evidence for the decision")
        if draft.changes:
            selected = st.selectbox(
                "Inspect a definition",
                [c.id for c in draft.changes],
                format_func=lambda v: next(c.label for c in draft.changes if c.id == v),
                key="prepared_detail_" + digest([draft.dataset, [c.id for c in draft.changes]]),
            )
            change = next(c for c in draft.changes if c.id == selected)
            st.markdown("**" + change.label + "**")
            st.caption(change.reason)
            if change.kind == "quantity":
                st.caption(
                    "Unit: "
                    + str(change.payload.get("unit") or "unspecified")
                    + " · Currency: "
                    + str(change.payload.get("currency") or "unspecified")
                    + " · Basis: "
                    + str(change.payload.get("basis") or "unspecified")
                )
            elif change.kind in {"task", "time", "availability"}:
                st.dataframe(
                    _declaration_details(ds, draft, change),
                    hide_index=True,
                    alt="Proposed analytical task or recording rule in readable terms",
                )
            elif change.kind == "metric":
                definition = {
                    k: v
                    for k, v in change.payload.items()
                    if k
                    in {
                        "aggregation",
                        "field",
                        "entity",
                        "weight",
                        "numerator",
                        "denominator",
                        "denominator_scope",
                        "allocation",
                        "time_policy",
                        "transform",
                    }
                    and v is not None
                }
                st.dataframe(
                    [
                        {"Property": k.replace("_", " "), "Definition": _reference_label(ds, draft, k, v)}
                        for k, v in definition.items()
                    ],
                    hide_index=True,
                    alt="Explicit estimator, value grain and denominator in the proposed metric",
                )
            st.badge(change_state(ds, draft, change))
            if change.issue:
                st.warning(change.issue)
            st.caption(change.review)
            for quote in change.evidence:
                st.markdown("> " + quote.quote.replace("\n", "\n> "))
                st.caption("Supplied " + quote.source)
            relevant = [w for w in draft.evidence if change.subject in w.get("fields", [])]
            if relevant:
                _render_witness(ds, relevant[0])
            with st.popover("Exact proposed definition", icon=":material/data_object:"):
                st.json(change.payload)
        st.page_link(
            "app_pages/meaning.py", label="Open the detailed meaning editor", icon=":material/schema:"
        )
    st.subheader("Questions that change the analysis")
    st.caption(
        "Priorities use task relevance, metric dependencies and computed differences between explicit interpretations. They are engineering priorities, not measured information gain."
    )
    questions = [q for q in draft.decisions if q["id"] not in draft.deferred]
    if questions:
        selection = st.selectbox(
            "Next useful clarification",
            [str(q["id"]) for q in questions],
            format_func=lambda v: str(next(q["question"] for q in questions if q["id"] == v)),
            key="preparation_decision_" + digest([draft.dataset, [q["id"] for q in questions]]),
        )
        q = next(q for q in questions if q["id"] == selection)
        qleft, qright = st.columns([1, 1.4], gap="medium")
        with qleft:
            st.markdown("**" + str(q["question"]) + "**")
            st.caption(str(q["reason"]))
            st.caption(
                "Explain the answer in Context & documents to prepare related changes, or use Meaning for a direct declaration."
            )
            if q.get("entity"):
                from firstlook.preparation import prepare_grain_answer

                for once, label in [
                    (False, "Confirm additive amount on each row"),
                    (True, "Confirm additive amount once per identifier"),
                ]:
                    if st.button(label, key="answer_grain_" + str(once)):
                        try:
                            prepared, mid = prepare_grain_answer(ds, draft, str(q["id"]), once)
                            ws.preparation = prepared.model_dump(mode="json")
                            apply_prepared_bundle(ws, [mid])
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
            if st.button("Not needed for my next question", key="defer_preparation_decision"):
                draft.deferred = (draft.deferred + [str(q["id"])])[-24:]
                ws.preparation = draft.model_dump(mode="json")
                st.rerun()
        with qright:
            witness = next((w for w in draft.evidence if w["id"] == q.get("witness")), None)
            if witness:
                _render_witness(ds, witness)
            else:
                st.caption(
                    "This question affects reusable analytical meaning. It does not prevent exploration of the recorded values."
                )
    else:
        st.caption(
            "No further clarification is prioritized for this draft. Deferred and unrelated meanings remain editable."
        )
    st.subheader("A useful next view")
    from firstlook.ui.runtime import start_analysis, start_view

    if ready["recommended"]:
        options = [r["id"] for r in ready["recommended"]]
        metric = st.selectbox(
            "Prepared metric",
            options,
            format_func=lambda mid: get_model(ds).metric(mid).label,
            key="preparation_start_metric_" + digest(options),
        )
        groups = [
            f.id
            for f in ds.record.fields
            if f.role.value in {"category", "ordinal", "boolean"}
            and not f.excluded
            and ds.frame[f.id].nunique() <= 30
        ]
        group = st.selectbox(
            "Compare across",
            [None] + groups,
            format_func=lambda v: "Whole recorded population" if v is None else ds.label(v),
            key="preparation_start_group",
        )
        from firstlook.semantic.policy import decision

        time_field = next(r["time_field"] for r in ready["recommended"] if r["id"] == metric)
        permission = decision(
            ds, get_model(ds).metric(metric), [group] if group else [], time_field, rows=ws.context().row_ids
        )
        if permission.status != "allowed":
            st.warning(" ".join(permission.reasons + permission.requirements))
            st.page_link(
                "app_pages/meaning.py", label="Review the required definition", icon=":material/schema:"
            )
        if st.button(
            "Open this prepared view",
            key="open_prepared_view",
            disabled=bool(ws.job_id) or permission.status != "allowed",
        ):
            try:
                from firstlook.semantic.planner import metric_fields

                params = {"metric": metric, "group_by": [group] if group else []}
                if time_field:
                    params["time_field"] = time_field

                start_view(
                    ws,
                    "metric",
                    list(
                        dict.fromkeys(
                            metric_fields(ds, get_model(ds).metric(metric))
                            + ([group] if group else [])
                            + ([time_field] if time_field else [])
                        )
                    ),
                    params,
                    "Prepared metric: " + get_model(ds).metric(metric).label,
                )
                st.switch_page("app_pages/explore.py")
            except ValueError as exc:
                st.error(str(exc))
    if st.button(
        "Explore the dataset broadly",
        key="preparation_explore",
        disabled=bool(ws.job_id) and ws.job_kind != "preparation",
    ):
        start_analysis(ws)
        st.switch_page("app_pages/explore.py")


def _render_witness(ds, witness):
    st.caption(str(witness["description"]))
    if "row_sum" in witness:
        st.markdown("**Hypothetical additive interpretations**")
        grid = st.grid(2, min_column_width=150)
        grid.metric("Every recorded row", f"{float(witness['row_sum']):,.4g}")
        grid.metric("Once per identifier", f"{float(witness['once_per_entity_sum']):,.4g}")
        st.caption(
            f"{witness['valid_rows']} complete records · {witness['omitted_rows']} omitted for missing identity/value. These calculations do not establish which interpretation is correct."
        )
    rows = witness.get("rows", [])
    if rows:
        names = [f.name for f in ds.record.fields]
        table = pd.DataFrame(rows).rename(
            columns={
                f.id: f.name + (f" (column {f.position + 1})" if names.count(f.name) > 1 else "")
                for f in ds.record.fields
            }
        )
        table["source_row"] = table["source_row"] + 1
        table = table.rename(columns={"source_row": "Source record"})
        st.dataframe(table, hide_index=True, alt="Exact source examples supporting a semantic clarification")


def _reference_label(ds, draft, key, value):
    if key in {"field", "weight", "target", "anchor_field", "outcome_known_field", "timestamp"}:
        return ds.label(value) if value in ds.frame else str(value or "Not specified")
    if key in {"entity", "numerator", "denominator", "time_policy"}:
        kind = {"entity": "entity", "numerator": "metric", "denominator": "metric", "time_policy": "time"}[
            key
        ]
        proposal = next((c for c in draft.changes if c.kind == kind and c.subject == value), None)
        if proposal:
            return proposal.label
        model = get_model(ds)
        if kind == "entity":
            return model.entity(value).label
        if kind == "metric":
            return model.metric(value).label
        policy = next((p for p in model.time_policies if p.id == value), None)
        return ds.label(policy.field) if policy else "Not specified"
    return str(value).replace("_", " ")


def _declaration_details(ds, draft, change):
    p = change.payload
    keys = {
        "task": [
            "question",
            "purpose",
            "unit",
            "population",
            "target",
            "decision_time",
            "anchor_field",
            "outcome_known_field",
            "horizon_days",
            "complete_through",
            "primary_metric",
        ],
        "time": [
            "field",
            "kind",
            "expected_frequency",
            "gap_policy",
            "coverage_complete",
            "complete_through",
            "max_gap_periods",
            "calendar",
        ],
        "availability": [
            "field",
            "status",
            "timestamp",
            "lag_hours",
            "mutable",
            "history_available",
            "timestamp_role",
        ],
    }[change.kind]
    return [
        {
            "Definition": key.replace("_", " ").capitalize(),
            "Proposed meaning": _reference_label(ds, draft, key, p.get(key)),
        }
        for key in keys
        if p.get(key) is not None and p.get(key) != ""
    ]


def context_input(ws):
    inputs = ws.preparation_inputs
    st.subheader("Explain once. Prepare related changes together.")
    st.caption(
        "A short explanation can establish row meaning, value grain and several metric definitions at once. A dictionary is optional. Source wording is retained with proposals for review."
    )
    with st.form("preparation_context_form"):
        goal = st.text_input(
            "What would you like to understand?",
            value=inputs.get("goal", ""),
            max_chars=1000,
            placeholder="Optional: compare profitability across customer segments",
            key="preparation_goal",
        )
        notes = st.text_area(
            "What should the app know about how this table was recorded?",
            value=inputs.get("notes", ""),
            max_chars=6000,
            height=145,
            placeholder="Each row is an order line. Sales belongs to the line. Shipping cost is repeated on every line of an order.",
            key="preparation_notes",
        )
        document = st.file_uploader(
            "Optional dictionary or collection notes",
            type=["md", "txt", "csv", "json"],
            key="preparation_dictionary_" + str(ws.preparation_generation),
            help="Plain UTF-8 text, up to 12,000 characters. Use definitions relevant to this table; no external browsing is performed.",
        )
        clear_document = (
            st.checkbox("Remove the previously supplied dictionary", key="preparation_clear_dictionary")
            if inputs.get("dictionary")
            else False
        )
        connected = st.checkbox(
            "Use configured models to interpret this context",
            value=bool(st.session_state.get("external_ok")),
            key="preparation_context_connected",
            help="Sends this supplied context, bounded summaries and selected source examples to Terra, with narrow source-support questions to Jev. The owner's keys stay on the server.",
        )
        submitted = st.form_submit_button(
            "Prepare this understanding",
            type="primary",
            disabled=bool(ws.job_id),
            icon=":material/auto_awesome:",
        )
    if submitted:
        try:
            dictionary = "" if clear_document else inputs.get("dictionary", "")
            if document is not None:
                if document.size > 48000:
                    raise ValueError("Use a dictionary of at most 12,000 UTF-8 characters.")
                dictionary = document.getvalue().decode("utf-8-sig")
            sources = preparation_sources(notes, dictionary)
            ws.preparation_inputs = {"goal": goal, "notes": notes, "dictionary": dictionary}
            ws.preparation = build_preparation(ws.dataset, goal, sources).model_dump(mode="json")
            if connected:
                st.session_state.external_ok = True
                start_preparation(ws)
            else:
                ws.message = "Local preparation refreshed. Supplied wording is retained; connected interpretation can be requested when useful."
            st.rerun()
        except (ValueError, UnicodeDecodeError) as exc:
            st.error(str(exc))
    st.caption(
        f"{len(ws.preparation_requests)} / 3 connected requests used for this upload. Reruns and local review do not make new requests."
    )
    if inputs.get("dictionary"):
        st.caption(f"Dictionary retained: {len(inputs['dictionary']):,} characters.")


def template_controls(ws):
    from firstlook.preparation_templates import export_template, import_template

    st.subheader("Reuse approved definitions on the next export")
    st.caption(
        "Templates contain field names, definitions and metric recipes. They omit source rows, provider transcripts, completeness and prediction-availability attestations. Importing creates a reviewable draft and recomputes structural evidence."
    )
    left, right = st.columns(2, gap="medium")
    with left:
        name = st.text_input(
            "Template name",
            value="Reusable analytical definitions",
            max_chars=150,
            key="preparation_template_name",
        )
        st.download_button(
            "Download approved definitions",
            data=export_template(ws.dataset, name or "Analytical definitions"),
            file_name="first-look-meanings.json",
            mime="application/json",
            key="download_semantic_template",
            icon=":material/download:",
        )
        if st.button(
            "Remember these definitions for matching uploads in this session",
            key="remember_semantic_template",
        ):
            data = export_template(ws.dataset, name or "Analytical definitions")
            ws.preparation_templates = (ws.preparation_templates + [{"name": name, "data": data}])[-3:]
            st.success(
                "Remembered in this session. Future matching uploads receive a reviewed-definition draft; nothing is confirmed automatically. Download the template to keep it across restarts."
            )
    with right:
        uploaded = st.file_uploader(
            "Load a semantic template", type=["json"], key="preparation_template_upload"
        )
        if st.button(
            "Prepare reused definitions",
            disabled=uploaded is None or bool(ws.job_id),
            key="load_semantic_template",
        ):
            try:
                if uploaded is None:
                    raise ValueError("Select a semantic template first.")
                ws.preparation = import_template(
                    ws.dataset, uploaded.getvalue(), ws.preparation_inputs.get("goal", "")
                ).model_dump(mode="json")
                ws.message = (
                    "Template checked against this upload. Review the proposed definitions before confirming."
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    draft = current_draft(ws)
    if draft.telemetry.get("template"):
        st.json(draft.telemetry["template"])
    st.subheader("Preparation record")
    st.caption(
        "The record can contain supplied notes, source examples and provider inputs. Review it before sharing. It is also included in investigation evidence exports."
    )
    record = {"draft": ws.preparation, "requests": ws.preparation_history}
    st.download_button(
        "Download preparation record",
        data=json.dumps(record, indent=2, allow_nan=False).encode(),
        file_name="first-look-preparation.json",
        mime="application/json",
        key="download_preparation_record",
    )
    st.caption(
        "Policy "
        + draft.policy
        + f" · {len(draft.applied)} changes applied from this draft · {draft.telemetry.get('rows_checked', 0)} source rows examined locally."
    )
    if st.toggle("Inspect the recorded preparation", key="inspect_preparation_record"):
        st.json(record)
