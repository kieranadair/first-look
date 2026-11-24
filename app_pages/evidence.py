import streamlit as st

from firstlook.evidence import brief, export_bundle, import_bundle, recompute
from firstlook.contracts import digest
from firstlook.ui.components import page_header, comparison_board
from firstlook.ui.runtime import workspace

ws = workspace()
page_header(
    "Evidence",
    "Keep observations, checks and your interpretation together. Export the investigation when you are ready.",
    compact=True,
)
with st.popover("Open a saved investigation", icon=":material/folder_open:"):
    bundle = st.file_uploader("Investigation bundle", type=["zip"], key="bundle_upload")
    if bundle is not None and st.button("Open recorded evidence", key="import_bundle"):
        try:
            imported = import_bundle(bundle.getvalue())
            st.session_state.workspace = imported
            st.session_state.external_ok = False
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(str(exc))

# Capture the previous editor before switching the selected pin or content view.
for item in ws.pins:
    note_key = "note_" + item["finding"]["id"]
    if note_key in st.session_state:
        item["note"] = st.session_state[note_key]

downloads = st.container(border=True)
saved_view = (
    st.segmented_control(
        "Saved evidence",
        ["Observations", "Comparisons"],
        default="Observations" if ws.pins or not ws.comparisons else "Comparisons",
        key="evidence_view",
    )
    if ws.comparisons
    else "Observations"
) or "Observations"
if saved_view == "Comparisons":
    st.caption("Each board retains its own populations, definitions and compatible display.")
    chosen = st.selectbox(
        "Comparison board",
        [b.id for b in ws.comparisons],
        format_func=lambda i: next(
            f"{b.spec.operation} · {len(b.spec.selection.rows):,} selected / {len(b.spec.reference_rows):,} reference rows"
            for b in ws.comparisons
            if b.id == i
        ),
        key="evidence_comparison",
    )
    comparison_board(next(b for b in ws.comparisons if b.id == chosen), "saved")
if ws.investigation is None:
    if ws.pins or ws.comparisons:
        st.info(
            "The current analytical definition changed. Your earlier evidence retains its original definitions. Run a new investigation to prepare a combined portable bundle."
        )
        if saved_view == "Observations":
            for item in ws.pins:
                with st.container(border=True):
                    st.markdown("**" + item["finding"]["title"] + "**")
                    st.markdown(item["finding"]["observation"])
                    if item.get("note"):
                        st.caption("Your interpretation: " + item["note"])
                    st.caption(
                        "Preserved from an earlier analytical context: " + item["result"]["plan"]["context"]
                    )
                    with st.expander("Original analytical definition"):
                        st.json(item.get("semantic_contract"), expanded=False)
        with downloads:
            st.download_button(
                "Download preserved brief",
                brief(ws),
                "first-look-preserved-brief.md",
                "text/markdown",
                icon=":material/download:",
            )
        st.page_link("app_pages/explore.py", label="Build a new overview", icon=":material/explore:")
    else:
        with downloads:
            st.caption("Pin an observation in Findings or Challenge to start an evidence brief.")
            st.page_link(
                "app_pages/understand.py" if ws.dataset is None else "app_pages/explore.py",
                label="Open a dataset" if ws.dataset is None else "Explore the dataset",
                icon=":material/explore:",
            )
    st.stop()
st.caption(
    f"{len(ws.pins)} pinned observations · {len(ws.comparisons)} saved comparisons · {len(ws.investigation.challenges)} recorded checks"
)
if ws.text_runs or ws.investigation.judgments:
    st.caption(
        f"{len(ws.text_runs)} frozen text runs and {len(ws.investigation.judgments)} typed judgment batches also travel with this investigation. Recorded inputs can contain source text even when the original table is omitted."
    )
    st.page_link("app_pages/judgments.py", label="Inspect model judgments", icon=":material/fact_check:")
if not ws.pins and saved_view == "Observations":
    st.markdown("### Start an evidence brief.")
    st.caption("Use Pin on an observation. Its computed values and completed checks travel with it.")
    if st.button("Pin the leading observation", icon=":material/bookmark:"):
        from firstlook.state import pin

        if ws.investigation.findings:
            pin(ws, ws.investigation.findings[0].id)
            st.rerun()
if ws.pins and saved_view == "Observations":
    pin_id = st.selectbox(
        "Pinned observation · brief order",
        [item["finding"]["id"] for item in ws.pins],
        format_func=lambda value: next(
            f"{i + 1:02} · {item['finding']['title']}"
            for i, item in enumerate(ws.pins)
            if item["finding"]["id"] == value
        ),
        key="evidence_pin",
    )
    i = next(i for i, item in enumerate(ws.pins) if item["finding"]["id"] == pin_id)
    item = ws.pins[i]
    f = item["finding"]
    with st.container(border=True):
        st.caption(f"Observation {i + 1} of {len(ws.pins)} · {f['claim_type']}")
        st.subheader(f["title"])
        st.markdown(f["observation"])
        if item["result"]["plan"]["context"] != ws.investigation.context.id:
            st.caption(
                "Preserved from an earlier analytical context; the original values and assumptions travel with this pin."
            )
        related = {c["id"]: c for c in item["challenges"]}
        related.update(
            {c.id: c.model_dump(mode="json") for c in ws.investigation.challenges if c.parent_id == f["id"]}
        )
        for c in related.values():
            st.caption(c["status"].replace("_", " ").capitalize() + ": " + c["summary"])
        note = st.text_area(
            "Your interpretation or next question",
            value=item.get("note", ""),
            key="note_" + f["id"],
            max_chars=4000,
            height=110,
            placeholder="What does this suggest? What should you check next?",
        )
        item["note"] = note
        with st.container(horizontal=True):
            if st.button("Move up", key="up_" + f["id"], disabled=i == 0, icon=":material/arrow_upward:"):
                ws.pins[i - 1], ws.pins[i] = ws.pins[i], ws.pins[i - 1]
                st.rerun()
            if st.button("Remove", key="remove_" + f["id"], type="tertiary", icon=":material/close:"):
                ws.pins.pop(i)
                st.rerun()

with downloads:
    st.markdown("**Take the investigation with you**")
    st.caption(
        "A portable bundle preserves definitions, results and checks. A readable brief includes your notes."
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        include = st.checkbox(
            "Include the original dataset",
            value=False,
            key="include_raw",
            disabled=ws.dataset is None or ws.dataset.frame.empty,
            help="Saved result tables can still contain private data when this is off. API keys are always excluded.",
        )
        prepare = st.button(
            "Prepare downloads", type="primary", icon=":material/inventory_2:", key="prepare_export"
        )
export_state = digest(
    [
        ws.investigation.context.id,
        ws.pins,
        include,
        [c.model_dump(mode="json") for c in ws.investigation.challenges],
        ws.investigation.terra,
        ws.model.id if ws.model else None,
        [f.id for f in ws.investigation.findings],
        [d.model_dump(mode="json") for d in ws.investigation.decisions],
        [b.model_dump(mode="json") for b in ws.comparisons],
        ws.comparison.model_dump(mode="json") if ws.comparison else None,
        ws.investigation.coverage,
        [r.model_dump(mode="json") for r in ws.investigation.judgments],
        ws.investigation.goal,
        ws.investigation.recommendations,
        ws.investigation.question_history,
        ws.question_review,
        ws.text_proposal,
        ws.text_runs,
        ws.note_review,
        ws.semantic_scenarios,
    ]
)
if prepare:
    try:
        blob = export_bundle(ws, include)
        st.session_state.prepared_bundle = blob
        st.session_state.prepared_brief = brief(ws)
        st.session_state.prepared_context = export_state
    except ValueError as exc:
        st.error(str(exc))
if st.session_state.get("prepared_bundle") and st.session_state.get("prepared_context") == export_state:
    with downloads.container(horizontal=True):
        st.download_button(
            "Download investigation",
            st.session_state.prepared_bundle,
            "first-look-investigation.zip",
            "application/zip",
            icon=":material/download:",
            key="download_bundle",
        )
        st.download_button(
            "Download readable brief",
            st.session_state.prepared_brief,
            "first-look-brief.md",
            "text/markdown",
            icon=":material/description:",
            key="download_brief",
        )
if ws.replay:
    st.caption("Replay mode: provenance is recorded information. Checksums detect changes, not authorship.")
    if ws.dataset is not None and not ws.dataset.frame.empty:
        if st.button("Recompute deterministic evidence", key="recompute"):
            try:
                checks = recompute(ws)
                st.dataframe(checks, hide_index=True, alt="Deterministic replay comparison results")
            except ValueError as exc:
                st.error(str(exc))
if ws.dataset and ws.dataset.record.semantic_model:
    with st.expander("Recorded semantic contract"):
        st.caption(
            "Scope: exact uploaded table. Recorded declarations and computed evidence do not establish authorship or universal domain truth."
        )
        st.json(ws.dataset.record.semantic_model.model_dump(mode="json"), expanded=False)
with st.expander("Methods and provenance"):
    st.mermaid_chart(
        "flowchart LR\n A[Table and semantics] --> B[Eligible plans]\n B --> C[Computed findings]\n C --> D[Challenges]\n C --> E[Model diagnostics]\n D --> F[Evidence]\n E --> F",
        alt="Evidence comes from the table, eligible plans, computed findings and checks",
    )
    st.caption(
        "Quantiles use linear interpolation. Correlations use paired finite rows. Group support and omitted values are explicit. No selected-winner significance or causal claims are generated."
    )
    st.json(
        {
            "context": ws.investigation.context.model_dump(mode="json"),
            "decisions": [d.model_dump(mode="json") for d in ws.investigation.decisions],
            "terra_status": ws.investigation.terra.get("status", "not run"),
        },
        expanded=False,
    )
