"""Inspect model judgments, explicit code policies and reproducible evaluation cases."""

import json

import pandas as pd
import streamlit as st

from firstlook.judgment_catalog import built_in_definitions
from firstlook.judgment_lab import recorded_judgments, compare_records, evaluate_cases
from firstlook.judgments import POLICY_VERSION
from firstlook.ui.components import page_header
from firstlook.ui.runtime import workspace, settings, start_ranking

ws, cfg = workspace(), settings()
page_header("Judgments", "See what was asked, what the model answered and which Python policy acted on it.")
st.caption(
    f"Policy {POLICY_VERSION} · Judgment probabilities are not p-values, effect sizes or proof that a chart is valid."
)
mode = (
    st.segmented_control(
        "Judgment workspace",
        ["Recorded decisions", "Recommendations", "Question library", "Evaluation cases"],
        default="Recorded decisions",
        key="judgments_mode",
    )
    or "Recorded decisions"
)
if mode == "Question library":
    definitions = built_in_definitions()
    st.dataframe(
        [
            {
                "Question": s.id,
                "Type": s.kind,
                "Purpose": s.purpose,
                "Wording": s.question,
                "Version": s.version,
            }
            for s in definitions
        ],
        hide_index=True,
        alt="Versioned built-in atomic judgment definitions",
    )
    selected = st.selectbox("Inspect a definition", [s.id for s in definitions], key="library_spec")
    spec = next(s for s in definitions if s.id == selected)
    st.markdown("**" + spec.question + "**")
    st.json(spec.model_dump(mode="json"), expanded=True)
    st.caption(
        "Text feature questions are supplied or reviewed by the analyst and frozen separately with each run. Scores are anchored rubric rankings; unresolved bands and routing remain explicit Python policies."
    )
    st.download_button(
        "Download question definitions",
        json.dumps([s.model_dump(mode="json") for s in definitions], indent=2),
        "first-look-judgment-definitions.json",
        "application/json",
    )
    st.stop()
if mode == "Evaluation cases":
    st.markdown("**Start with an explicit baseline**")
    report = evaluate_cases()
    st.caption(report["mode"])
    st.dataframe(
        report["cases"],
        hide_index=True,
        alt="Developer-labelled routing cases and observed deterministic outcomes",
    )
    st.caption(
        f"Observed case accuracy {report['accuracy']:.0%} · routing coverage {report['coverage']:.0%}. {report['limits']}"
    )
    st.download_button(
        "Download baseline case report",
        json.dumps(report, indent=2),
        "first-look-routing-baseline.json",
        "application/json",
    )
    st.caption(
        "Optional owner-authorised live evaluation uses scripts.evaluate_judgments. It sends only bundled metadata and synthetic questions. This page makes no paid calls."
    )
    st.stop()
if mode == "Recommendations" and ws.investigation:
    inv = ws.investigation
    with st.container(border=True):
        st.markdown("**Recommend complementary evidence for a stated goal**")
        goal = st.text_input(
            "What do you want to understand?",
            value=inv.goal,
            max_chars=1000,
            key="ranking_goal",
            placeholder="For example: how does body size vary between recorded species?",
        )
        if st.button(
            "Review relevance with Jev",
            disabled=ws.replay
            or bool(ws.job_id)
            or not cfg.available("jev")
            or not st.session_state.get("external_ok")
            or not goal.strip(),
            key="rank_evidence",
        ):
            try:
                start_ranking(ws, goal)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.caption(
            "Python supplies eligible candidates and computes complementarity, support and cost. Jev judges relevance to your stated goal. Ranking cannot grant a blocked operation."
        )
        if inv.recommendations:
            st.dataframe(
                pd.DataFrame(inv.recommendations).rename(
                    columns={
                        "question": "Candidate",
                        "relevance": "Jev relevance",
                        "novelty": "Family complement",
                        "support_component": "Support",
                        "cost_component": "Cost",
                        "score": "Policy ranking",
                    }
                )[
                    [
                        "Candidate",
                        "Jev relevance",
                        "Family complement",
                        "Support",
                        "Cost",
                        "Policy ranking",
                        "method",
                    ]
                ],
                hide_index=True,
                alt="Model relevance and deterministic ranking components",
            )
if mode == "Recommendations":
    if not ws.investigation:
        st.info("Run a local investigation before reviewing candidate relevance.")
    st.stop()

records = recorded_judgments(ws)
if not records:
    st.info(
        "No typed model judgments are recorded yet. A connected investigation, prepared question, note review or Text lab run will appear here. Local analysis remains available without keys."
    )
    st.stop()
st.dataframe(
    [
        {
            "Record": r.id,
            "Purpose": r.purpose,
            "Questions": len(r.definitions),
            "Resolved model": r.resolved_model,
            "Policy": r.policy_version,
            "Input tokens": r.usage.get("input_tokens"),
            "Output tokens": r.usage.get("output_tokens"),
            "Latency (ms)": r.latency_ms,
        }
        for r in records
    ],
    hide_index=True,
    alt="Recorded judgment batches, models and reported usage",
)
selected_id = st.selectbox(
    "Inspect a recorded batch",
    [r.id for r in records],
    format_func=lambda k: next(r.purpose + " · " + r.id[:8] for r in records if r.id == k),
    key="judgment_record",
)
record = next(r for r in records if r.id == selected_id)
st.caption(
    f"Context {record.context} · state hash {record.state_hash} · requested {record.requested_model} / resolved {record.resolved_model}"
)
st.dataframe(
    [
        {
            "Question": s.id,
            "Purpose": s.purpose,
            "Type": s.kind,
            "Status": record.answers[s.id].status,
            "Outcome": str(record.answers[s.id].value),
        }
        for s in record.definitions
    ],
    hide_index=True,
    height=240,
    alt="Overview of all atomic questions and their code outcomes",
)
question_id = st.selectbox(
    "Question to inspect",
    [s.id for s in record.definitions],
    format_func=lambda k: next(s.purpose + " · " + k for s in record.definitions if s.id == k),
    key="judgment_question",
)
spec = next(s for s in record.definitions if s.id == question_id)
answer = record.answers[spec.id]
left, right = st.columns(2, gap="medium")
with left:
    st.markdown("**" + spec.question + "**")
    st.caption(f"{spec.kind} · {answer.status} · Python outcome: {answer.value}")
    if spec.kind == "noul":
        st.caption("Yes: " + spec.yes)
        st.caption("No: " + spec.no)
    elif spec.kind == "choice":
        st.dataframe(
            [{"Option": k, "Criteria": v} for k, v in spec.options.items()],
            hide_index=True,
            alt="Exact supplied Choice criteria",
        )
    else:
        st.dataframe(
            [{"Level": i, "Situation": v} for i, v in enumerate(spec.levels)],
            hide_index=True,
            alt="Standalone anchored Score levels",
        )
    st.caption(
        f"Policy thresholds: low {spec.low:g}, high {spec.high:g}, Choice margin {spec.margin:g}. Unresolved outcomes remain explicit."
    )
with right:
    st.markdown("**Complete answer distribution**")
    st.dataframe(
        [{"Alternative": k, "Probability": v} for k, v in answer.probabilities.items()],
        hide_index=True,
        column_config={"Probability": st.column_config.NumberColumn(format="percent")},
        alt="Complete model answer distribution",
    )
    with st.expander("Definition as a reusable record"):
        st.json(spec.model_dump(mode="json"), expanded=False)
st.download_button(
    "Download this judgment record",
    record.model_dump_json(indent=2),
    "first-look-judgment-" + record.id + ".json",
    "application/json",
)
with st.expander("Exact supplied state"):
    st.caption(
        "Inputs can contain selected source text. A matching hash detects changes; it does not establish authorship or correctness."
    )
    st.json(record.state, expanded=False)
if len(records) > 1:
    st.markdown("**Compare recorded judgments without another model call**")
    other_id = st.selectbox(
        "Compare with batch", [r.id for r in records if r.id != record.id], key="compare_judgment_record"
    )
    comparison = compare_records(record, next(r for r in records if r.id == other_id))
    if comparison:
        st.dataframe(
            comparison,
            hide_index=True,
            alt="Question, state, model and outcome changes between recorded batches",
        )
    else:
        st.caption(
            "These batches have no shared question identities. Their outcomes cannot be aligned by position."
        )
