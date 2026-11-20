import streamlit as st

from firstlook.evidence import brief, export_bundle, import_bundle, recompute
from firstlook.contracts import digest
from firstlook.ui.components import page_header
from firstlook.ui.runtime import workspace

ws = workspace()
page_header(
    "Keep the evidence together.",
    "Useful observations, changed interpretations, open questions—and the path that produced them.",
)
with st.expander("Open a saved investigation"):
    bundle = st.file_uploader("Investigation bundle", type=["zip"], key="bundle_upload")
    if bundle is not None and st.button("Open recorded evidence", key="import_bundle"):
        try:
            imported = import_bundle(bundle.getvalue())
            st.session_state.workspace = imported
            st.session_state.external_ok = False
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(str(exc))
if ws.investigation is None:
    st.info("Pin observations from Discover or Challenge. You can also open a saved bundle above.")
    st.stop()
st.caption(f"{len(ws.pins)} PINNED OBSERVATIONS  ·  {len(ws.investigation.challenges)} RECORDED CHECKS")
if not ws.pins:
    st.markdown("### Start an evidence brief.")
    st.caption("Use Pin on an observation. Its computed values and completed checks travel with it.")
    if st.button("Pin the leading observation", icon=":material/bookmark:"):
        from firstlook.state import pin

        if ws.investigation.findings:
            pin(ws, ws.investigation.findings[0].id)
            st.rerun()
for i, item in enumerate(ws.pins):
    f = item["finding"]
    with st.container(border=True):
        st.caption(f"EVIDENCE {i + 1:02}  ·  {f['claim_type'].upper()}")
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
        )
        item["note"] = note
        with st.container(horizontal=True):
            if st.button("Move up", key="up_" + f["id"], disabled=i == 0):
                ws.pins[i - 1], ws.pins[i] = ws.pins[i], ws.pins[i - 1]
                st.rerun()
            if st.button("Remove", key="remove_" + f["id"]):
                ws.pins.pop(i)
                st.rerun()

st.subheader("Take the investigation with you.")
include = st.checkbox(
    "Include the original dataset",
    value=False,
    key="include_raw",
    disabled=ws.dataset is None or ws.dataset.frame.empty,
    help="Saved result tables can still contain private data when this is off.",
)
st.caption(
    "The bundle includes contexts, calculations, chart contracts, challenges and recorded model decisions. API keys are excluded. Stored results can be inspected without another API call."
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
    ]
)
if st.button("Prepare downloads", type="primary", icon=":material/inventory_2:", key="prepare_export"):
    try:
        blob = export_bundle(ws, include)
        st.session_state.prepared_bundle = blob
        st.session_state.prepared_brief = brief(ws)
        st.session_state.prepared_context = export_state
    except ValueError as exc:
        st.error(str(exc))
if st.session_state.get("prepared_bundle") and st.session_state.get("prepared_context") == export_state:
    with st.container(horizontal=True):
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
