"""A quick first pass, with field evidence beside the meanings it informs."""

import hashlib
from typing import Any, cast

import streamlit as st

from firstlook.contracts import Role, digest
from firstlook.discovery import analyze, plan_for
from firstlook.examples import CATALOG, load_example
from firstlook.ingest import InputError, load_table
from firstlook.modeling import eligible_targets
from firstlook.profiling import profile
from firstlook.semantic.model import get_model
from firstlook.semantics import apply_semantics, semantic_table
from firstlook.ui.components import chart_view, page_header
from firstlook.ui.preparation import preparation_overview
from firstlook.ui.runtime import manager, start_analysis, start_semantic_review, settings, workspace

ws = workspace()
page_header(
    "Understand" if ws.dataset else "A clearer first look.",
    "Review your table, then start a local investigation. Refine its business meaning as you explore."
    if ws.dataset
    else "Explore a table. Question the patterns. Keep the evidence.",
    compact=ws.dataset is not None,
)


def open_dataset():
    uploaded = st.file_uploader(
        "Open your dataset",
        type=["csv", "parquet"],
        key="data_upload",
        help="One table · up to 25 MiB · 50,000 rows · 80 fields",
    )
    with st.expander("CSV parsing options"):
        delimiter = st.selectbox("Delimiter", [",", ";", "\t", "|"], key="delimiter")
        encoding = st.selectbox("Encoding", ["utf-8-sig", "utf-8", "latin-1"], key="encoding")
        missing = st.text_input(
            "Additional missing tokens, separated by commas",
            key="missing_tokens",
            help="Empty cells are missing by default. Literal NA is preserved unless you add it.",
        )
    if uploaded is not None:
        raw = uploaded.getvalue()
        fingerprint = hashlib.sha256(raw).hexdigest()
        parser = {
            "delimiter": delimiter,
            "encoding": encoding,
            "missing_tokens": [""] + [v.strip() for v in missing.split(",") if v.strip()],
            "inference_version": 2,
        }
        if (
            ws.dataset is None
            or fingerprint != ws.dataset.record.fingerprint
            or digest(parser) != digest(ws.dataset.record.parser)
        ):
            try:
                ds = load_table(raw, uploaded.name, delimiter, encoding, parser["missing_tokens"])
                if ws.job_id:
                    manager().cancel(ws.owner, ws.job_id)
                ws.load(ds)
                st.session_state.external_ok = False
                st.rerun()
            except (InputError, ValueError) as exc:
                st.error(str(exc))


if ws.dataset is None:
    with st.container(horizontal=True, gap="small"):
        st.badge("1 · Open a table", color="blue")
        st.badge("2 · Explore and challenge", color="gray")
        st.badge("3 · Preserve the evidence", color="gray")
    opening = st.grid(2, min_column_width=310, gap="small")
    with opening.cell():
        with st.container(border=True, height="stretch"):
            st.subheader("Bring your own question")
            st.caption("CSV or Parquet · local analysis works without keys.")
            open_dataset()
    with opening.cell():
        with st.container(border=True, height="stretch"):
            st.caption("Guided example · analytical meaning")
            st.subheader("Orders aren’t rows.")
            st.markdown(
                "Explore sales, repeated order totals and time gaps. See why definitions change the question you can answer."
            )
            st.space("stretch")
            if st.button(
                "Explore semantic example",
                key="example_semantic",
                type="primary",
                icon=":material/arrow_forward:",
                width="stretch",
            ):
                ws.load(load_example("semantic"))
                st.session_state.external_ok = False
                st.rerun()
    st.subheader("Or follow a different thread")
    grid = st.grid(3, min_column_width=220, gap="small")
    for key in ["reversal", "penguins", "nonlinear"]:
        title, description, icon = CATALOG[key]
        with grid.cell():
            with st.container(border=True, height="stretch"):
                st.markdown(f"**:material/{icon}: {title}**")
                st.caption(description)
                st.space("stretch")
                if st.button("Explore example", key="example_" + key, width="stretch"):
                    ws.load(load_example(key))
                    st.session_state.external_ok = False
                    st.rerun()
    with st.popover("More examples", icon=":material/more_horiz:"):
        for key in ["bike", "null", "text", "events"]:
            if st.button(CATALOG[key][0], key="example_" + key, icon=f":material/{CATALOG[key][2]}:"):
                ws.load(load_example(key))
                st.session_state.external_ok = False
                st.rerun()
    st.caption(
        "Python computes and validates the evidence. Connected models are optional, and only run when requested with dataset permission."
    )
    st.stop()

ds = ws.dataset
if ws.replay:
    st.info(
        "This is recorded evidence. Open Findings or Evidence to inspect it, or change datasets to begin again."
    )
    st.page_link("app_pages/evidence.py", label="Open recorded evidence", icon=":material/bookmarks:")
    with st.popover("Change dataset", icon=":material/upload_file:"):
        open_dataset()
    st.stop()
p = ws.profile
semantic_model = get_model(ds)
# Reserve the action row before rendering settings, then handle it after their state is current.
actions = st.container(horizontal=True, vertical_alignment="center", gap="small")
with actions:
    investigate = st.button(
        "Investigate this dataset",
        type="primary",
        icon=":material/query_stats:",
        disabled=bool(ws.job_id) and ws.job_kind != "preparation",
    )
    with st.popover("Investigation settings", icon=":material/tune:"):
        targets = eligible_targets(ds)
        focus = st.selectbox(
            "Focus field",
            [None] + targets,
            format_func=lambda f: "Explore broadly" if f is None else ds.label(f),
            key="focus_" + ds.record.fingerprint,
            persist_state="session",
        )
        if focus != ws.focus:
            ws.focus = focus
            ws.invalidate()
        assumption = st.selectbox(
            "Sampling assumption",
            ["unknown", "exchangeable"],
            format_func=lambda v: (
                "Unknown — keep resampling checks off"
                if v == "unknown"
                else "Rows are exchangeable — enable diagnostic row resampling"
            ),
            key="assumption_" + ds.record.fingerprint,
            persist_state="session",
        )
        if assumption != ws.assumption:
            ws.assumption = assumption
            ws.invalidate()
        st.checkbox(
            "Allow external analysis for this dataset",
            key="external_ok",
            persist_state="session",
            help="Jev receives metadata and computed summaries. Terra receives field summaries, bounded plotted values and chart images. TabPFN receives the permitted training/test values. Nothing is sent until you request connected work.",
        )
        st.caption(
            "This page starts a local investigation. Request connected work explicitly in Findings or Models; it uses the owner's configured providers."
        )
    with st.popover("Change dataset", icon=":material/upload_file:"):
        st.caption(
            "Opening another table starts a new working investigation. Export important evidence first."
        )
        open_dataset()
if investigate:
    try:
        start_analysis(ws)
        st.switch_page("app_pages/explore.py")
    except ValueError as exc:
        st.error(str(exc))
st.caption(
    ("Focus: " + ds.label(ws.focus) if ws.focus else "Broad exploration")
    + " · Local investigation · External analysis "
    + ("permitted when requested" if st.session_state.get("external_ok") else "off")
)
grid = st.grid(4, min_column_width=130, gap="small")
grid.metric("Recorded rows", f"{p['rows']:,}")
grid.metric("Fields", p["columns"])
grid.metric("Missing cells", f"{p['missing'] / max(p['cells'], 1):.1%}")
grid.metric("Duplicate rows", f"{p['duplicates']:,}")

preparation_overview(ws)

with st.container(horizontal=True, vertical_alignment="center", gap="small"):
    st.caption(
        "**One row represents:** "
        + (
            semantic_model.grain
            if semantic_model.grain_confirmed
            else ds.record.description or "Not yet described. Add collection context when you know it."
        )
    )
    with st.popover("Edit context", icon=":material/edit_note:"):
        with st.form("dataset_context_form", border=False):
            description = st.text_area(
                "Dataset context",
                value=ds.record.description,
                max_chars=2000,
                help="Describe what one row means, when it was collected, and any limits on interpretation.",
            )
            if st.form_submit_button("Apply dataset context") and description != ds.record.description:
                ds.record.description = description
                ws.invalidate()
                st.rerun()

st.subheader("Review the fields against their evidence")
with st.popover(
    "Inspect literal source values", icon=":material/manage_search:", on_change="rerun"
) as source_inspector:
    if source_inspector.open:
        from firstlook.source_inspection import inspection_rows

        st.caption(
            "All source rows before parsing. Marker and placeholder candidates are not automatically declared missing. Identifier strings and large integer strings are protected by inference recipe 2."
        )
        st.dataframe(
            inspection_rows(ds),
            hide_index=True,
            alt="Literal marker candidates and conversion evidence for every source field",
        )
        inspect_source_field = st.selectbox(
            "Source evidence field",
            [f.id for f in ds.record.fields],
            format_func=ds.label,
            key="source_evidence_field",
        )
        st.json(
            cast(Any, ds.record.source_profile.get("fields", {})).get(inspect_source_field, {}), expanded=True
        )
st.caption(
    "Correct roles and units on the left; inspect recorded values on the right. Proposed roles remain unconfirmed until you apply them."
)
roles, evidence = st.columns([1.35, 1], gap="medium")
with roles:
    with st.form("semantics_form", border=False):
        edited = st.data_editor(
            semantic_table(ds),
            hide_index=True,
            key="semantics_" + ws.context().semantics,
            disabled=["field", "name"],
            num_rows="fixed",
            height=320,
            column_order=["name", "role", "unit", "confirmed", "exclude", "order"],
            column_config={
                "field": None,
                "name": st.column_config.TextColumn("Field"),
                "role": st.column_config.SelectboxColumn(
                    "Analytical role", options=[r.value for r in Role], required=True
                ),
                "unit": st.column_config.TextColumn("Unit"),
                "order": st.column_config.TextColumn(
                    "Order", help="For ordinal fields, separate levels with |"
                ),
                "exclude": st.column_config.CheckboxColumn("Exclude"),
                "confirmed": st.column_config.CheckboxColumn("Confirmed"),
            },
            alt="Editable analytical roles and units for source fields",
        )
        if st.form_submit_button("Apply field meanings", icon=":material/check:"):
            try:
                changed = apply_semantics(ds, edited)
                if changed:
                    ws.invalidate()
                    ws.profile = profile(ds)
                    st.toast(f"Updated {len(changed)} fields. Dependent analyses will be recomputed.")
                    st.rerun()
                else:
                    st.caption("No field meanings changed.")
            except ValueError as exc:
                st.error(str(exc))
    st.caption(
        "Use the table's column controls or horizontal scroll for confirmation, exclusions and category order."
    )
with evidence:
    field_ids = [f.id for f in ds.record.fields]
    default_field = next((f.id for f in ds.record.fields if f.role == Role.MEASURE), field_ids[0])
    fid = st.selectbox(
        "Inspect a field",
        field_ids,
        index=field_ids.index(default_field),
        format_func=ds.label,
        key="profile_field",
    )
    f = ds.field(fid)
    field_profile = p["fields"][fid]
    st.caption(
        f"{field_profile['distinct']:,} distinct · {field_profile['count']:,} recorded · {field_profile['missing']:,} missing"
    )
    try:
        op = "frequency"
        if f.role == Role.MEASURE:
            shape = st.segmented_control(
                "Distribution view", ["Histogram", "Cumulative"], default="Histogram", key="distribution_view"
            )
            op = "ecdf" if shape == "Cumulative" else "distribution"
        result, finding = analyze(ds, ws.context(), plan_for(ws.context(), op, [fid], "Inspect " + f.name))
        chart_view(finding.chart, result, "field_inspector", height=240)
    except ValueError:
        st.dataframe(
            ds.frame[[fid]].head(50).rename(columns={fid: f.name}),
            hide_index=True,
            height=240,
            alt="First recorded values for the selected field",
        )
    st.caption(f.evidence)
    with st.expander("Detailed field profile"):
        st.json(field_profile, expanded=False)

with st.container(border=True):
    st.markdown("**Ready to ask business questions?**")
    st.caption(
        f"{len(semantic_model.clarifications)} open decisions · {len(semantic_model.metrics)} metric definitions · {len(semantic_model.relationships)} observed relationships. Meaning defines what can be totalled, averaged or compared."
    )
    st.page_link("app_pages/meaning.py", label="Review analytical meaning", icon=":material/schema:")

with st.expander("Optional second opinion on field meanings"):
    st.caption(
        "Terra can suggest roles and useful clarification questions from field summaries. Suggestions remain hypotheses until you choose and apply them. Units are preserved."
    )
    if st.button(
        "Review field meanings with Terra",
        key="review_semantics",
        disabled=not settings().available("terra")
        or not st.session_state.get("external_ok")
        or bool(ws.job_id)
        or bool(ws.semantic_review_count),
    ):
        try:
            start_semantic_review(ws)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if ws.semantic_review:
        review = ws.semantic_review
        st.caption("Unconfirmed model interpretation: " + review.get("dataset_note", ""))
        for item in review["suggestions"]:
            st.markdown(f"**{ds.label(item['field_id'])} → {item['role']}**")
            st.caption(
                item["reason"] + (" Question: " + item["clarification"] if item["clarification"] else "")
            )
            if not item["valid"]:
                st.caption("Ineligible: " + item["validation"])
        valid = {s["field_id"]: s for s in review["suggestions"] if s["valid"]}
        chosen = st.multiselect(
            "Suggestions to apply", list(valid), format_func=ds.label, key="semantic_suggestions"
        )
        current = review["context"] == ws.context().id
        if not current:
            st.caption("This review belongs to earlier field meanings and is retained as provenance.")
        if st.button(
            "Apply selected role suggestions",
            disabled=not chosen or not current,
            key="apply_semantic_suggestions",
        ):
            table = semantic_table(ds)
            for fid in chosen:
                table.loc[table.field == fid, "role"] = valid[fid]["role"]
                if valid[fid]["role"] == "ordinal":
                    table.loc[table.field == fid, "order"] = " | ".join(valid[fid]["ordered_levels"])
            try:
                apply_semantics(ds, table)
                ws.invalidate()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

st.caption(ds.record.source)
