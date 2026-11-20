import streamlit as st
from typing import Any, cast

from firstlook.challenges import LABELS, challenge, eligible
from firstlook.semantics import dimensions
from firstlook.state import pin
from firstlook.ui.components import STATUS, chart_view, page_header, render_chart
from firstlook.ui.runtime import workspace

ws = workspace()
page_header(
    "Give a finding a second look.",
    "A useful observation becomes more useful when you know what could change it.",
)
if ws.investigation is None:
    st.info("Run an investigation in Discover before choosing a finding to challenge.")
    st.stop()
inv, ds = ws.investigation, ws.dataset
assert ds is not None
ids = [f.id for f in inv.findings]
key = "challenge_parent_" + inv.context.id
if ws.challenge_id in ids and st.session_state.get(key) != ws.challenge_id:
    st.session_state[key] = ws.challenge_id
selected = st.selectbox(
    "Observation", ids, key=key, format_func=lambda i: next(f.title for f in inv.findings if f.id == i)
)
ws.challenge_id = selected
finding = next(f for f in inv.findings if f.id == selected)
ops = eligible(ds, inv, finding) if not ws.replay else []
if ops:
    with st.container(horizontal=True, vertical_alignment="bottom"):
        operation = st.selectbox(
            "Next check",
            ops,
            format_func=lambda op: LABELS.get(op, op.replace("_", " ")),
            key="check_operation",
        )
        group = None
        if operation in {"subgroup", "missingness"}:
            options = dimensions(ds)
            group = st.selectbox("Recorded group", options, format_func=ds.label, key="check_group")
        if st.button(
            "Run this check", type="primary", icon=":material/compare_arrows:", disabled=bool(ws.job_id)
        ):
            check = challenge(ds, inv, finding, operation, group)
            inv.challenges = [c for c in inv.challenges if c.id != check.id] + [check]
            st.rerun()
else:
    st.caption(
        "The supported checks for this observation are recorded below."
        if ws.replay
        else "No further check in the current catalog meets this view’s prerequisites."
    )

checks = [c for c in inv.challenges if c.parent_id == selected]
if checks:
    check_ids = [c.id for c in checks]
    active = st.selectbox(
        "Completed check",
        check_ids,
        key="completed_check_" + selected,
        format_func=lambda i: next(
            LABELS.get(c.operation, c.operation) + " · " + STATUS[c.status][0] for c in checks if c.id == i
        ),
    )
    current = next(c for c in checks if c.id == active)
    label, color = STATUS[current.status]
    st.badge(label, color=cast(Any, color))
    st.markdown(current.summary)
    grid = st.grid(2, min_column_width=420, gap="small")
    with grid.cell():
        with st.container(border=True):
            st.caption("ORIGINAL EVIDENCE")
            st.subheader(finding.title)
            render_chart(finding, inv, suffix="challenge_original", height=360)
            st.caption(finding.observation)
    with grid.cell():
        with st.container(border=True):
            st.caption("UNDER THIS CHECK")
            st.subheader(LABELS.get(current.operation, current.operation.replace("_", " ")))
            if current.result and current.chart:
                chart_view(current.chart, current.result, "challenge_alternative_" + current.id, height=360)
                st.caption(
                    f"{current.result.support:,} supporting observations · {current.result.missing:,} missing"
                )
            else:
                st.info(current.summary)
    with st.expander("Check quantities and assumptions"):
        if current.result:
            st.json(current.result.metrics)
            st.dataframe(
                current.result.frame().drop(columns=["row_ids"], errors="ignore").head(100),
                hide_index=True,
                alt="Computed quantities from the selected challenge",
            )
        st.caption(
            "Changed/similar labels apply only to this declared check. They do not prove an interpretation true."
        )
else:
    st.markdown(finding.observation)
    render_chart(finding, inv, suffix="unchallenged", height=380)
    st.caption("Choose an applicable check above to compare it with the original.")
if st.button("Pin observation with its checks", icon=":material/bookmark:", key="pin_challenged"):
    pin(ws, finding.id)
    st.toast("Observation and checks are in Evidence.")
