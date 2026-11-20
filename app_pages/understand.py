import hashlib

import streamlit as st

from firstlook.contracts import Role, digest
from firstlook.discovery import analyze, plan_for
from firstlook.examples import CATALOG, load_example
from firstlook.ingest import InputError, load_table
from firstlook.modeling import eligible_targets
from firstlook.profiling import profile
from firstlook.semantics import apply_semantics, semantic_table
from firstlook.ui.components import chart_view, page_header
from firstlook.ui.runtime import manager, start_analysis, start_semantic_review, settings, workspace

ws = workspace()
page_header("A clearer first look.", "Understand what you have. Find what deserves a second look.")

with st.container(border=True):
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
        }
        if (
            ws.dataset is None
            or fingerprint != ws.dataset.record.fingerprint
            or digest(parser) != digest(ws.dataset.record.parser)
        ):
            try:
                ds = load_table(
                    raw,
                    uploaded.name,
                    delimiter,
                    encoding,
                    [""] + [v.strip() for v in missing.split(",") if v.strip()],
                )
                if ws.job_id:
                    manager().cancel(ws.owner, ws.job_id)
                ws.load(ds)
                st.session_state.external_ok = False
                st.rerun()
            except (InputError, ValueError) as exc:
                st.error(str(exc))

if ws.dataset is None:
    st.space("small")
    st.subheader("Start with a question, not a blank page.")
    st.caption("These small datasets make the workflow tangible. Every calculation runs on the actual data.")
    grid = st.grid(3, min_column_width=260, gap="small")
    for key in ["reversal", "penguins", "nonlinear"]:
        title, description, icon = CATALOG[key]
        with grid.cell():
            with st.container(border=True, height="stretch"):
                st.markdown(f":material/{icon}:")
                st.subheader(title)
                st.markdown(description)
                st.space("stretch")
                if st.button("Explore example", key="example_" + key, width="stretch"):
                    ws.load(load_example(key))
                    st.session_state.external_ok = False
                    st.rerun()
    with st.expander("More examples"):
        for key in ["bike", "null"]:
            if st.button(CATALOG[key][0], key="example_" + key, icon=f":material/{CATALOG[key][2]}:"):
                ws.load(load_example(key))
                st.session_state.external_ok = False
                st.rerun()
    st.space("medium")
    for cell, (title, body) in zip(
        st.columns(3),
        [
            ("Find", "A focused set of questions, grounded in your table."),
            ("Challenge", "Check groups, extremes and the summaries behind the picture."),
            ("Preserve", "Take the calculations, assumptions and evidence with you."),
        ],
    ):
        cell.markdown("**" + title + "**")
        cell.caption(body)
    st.stop()

ds = ws.dataset
if ws.replay:
    st.info(
        "This is recorded evidence. Open Discover or Evidence to inspect it. Upload a new dataset to begin a fresh investigation."
    )
    st.stop()
p = ws.profile
grid = st.grid(4, min_column_width=170)
grid.metric("Recorded rows", f"{p['rows']:,}")
grid.metric("Fields", p["columns"])
grid.metric("Missing cells", f"{p['missing'] / max(p['cells'], 1):.1%}")
grid.metric("Duplicate rows", f"{p['duplicates']:,}")
st.caption(ds.record.source)
with st.expander("What does this table represent?"):
    with st.form("dataset_context_form"):
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

st.subheader("Give the fields their meaning.")
st.caption(
    "These roles are proposals. Correct identifiers, category order and units before interpreting an analysis."
)
with st.form("semantics_form"):
    edited = st.data_editor(
        semantic_table(ds),
        hide_index=True,
        key="semantics_" + ws.context().semantics,
        disabled=["field", "name"],
        num_rows="fixed",
        column_config={
            "field": None,
            "name": st.column_config.TextColumn("Field"),
            "role": st.column_config.SelectboxColumn(
                "Analytical role", options=[r.value for r in Role], required=True
            ),
            "unit": st.column_config.TextColumn("Unit"),
            "order": st.column_config.TextColumn("Order", help="For ordinal fields, separate levels with |"),
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

with st.expander("Inspect a field"):
    fid = st.selectbox("Field", [f.id for f in ds.record.fields], format_func=ds.label, key="profile_field")
    f = ds.field(fid)
    st.caption(f.evidence)
    field_profile = p["fields"][fid]
    st.json(field_profile, expanded=False)
    try:
        op = "frequency"
        if f.role == Role.MEASURE:
            shape = st.segmented_control(
                "Distribution view", ["Histogram", "Cumulative"], default="Histogram", key="distribution_view"
            )
            op = "ecdf" if shape == "Cumulative" else "distribution"
        result, finding = analyze(ds, ws.context(), plan_for(ws.context(), op, [fid], "Inspect " + f.name))
        chart_view(finding.chart, result, "field_inspector", height=260)
    except ValueError:
        st.dataframe(
            ds.frame[[fid]].head(50).rename(columns={fid: f.name}),
            hide_index=True,
            alt="First recorded values for the selected field",
        )

st.subheader("Set the direction.")
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
    help="Jev receives metadata and computed summaries. Terra receives field summaries, bounded plotted values and chart images. TabPFN receives the permitted training/test values. Nothing is sent until you request connected work.",
)
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
st.caption(
    "Local investigation needs no keys. Hosted models use the owner’s configured providers; original data is never repaired automatically."
)
if st.button(
    "Investigate this dataset", type="primary", icon=":material/query_stats:", disabled=bool(ws.job_id)
):
    try:
        start_analysis(ws)
        st.switch_page("app_pages/discover.py")
    except ValueError as exc:
        st.error(str(exc))
