"""A native, upload-first conversation with the user's data. No generated code executes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from typing import Any, Literal, cast
import copy
import hashlib

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from firstlook import __version__
from firstlook.analysis import compare
from firstlook.charts import options
from firstlook.data import load_table, starting_requests
from firstlook.evidence import export, inspect_bundle, readable_markdown
from firstlook.providers import assist_view, build_packet, settings_from
from firstlook.session import Session
from firstlook.types import (
    ChoiceRequired,
    Comparison,
    Field,
    Meaning,
    Metric,
    Request,
    Result,
    TimeRule,
    View,
    clean,
    digest,
)

VIEWS = {
    "distribution": "Variation in a quantity",
    "categories": "Variation across categories",
    "groups": "Distributions across groups",
    "relationship": "Relationship between quantities",
    "time": "Variation over time",
    "category_relationship": "Relationships between categories",
    "multivariate": "Several quantities together",
    "spatial": "Variation across locations",
    "missingness": "Missing information",
}
METRICS = {
    "count": "Recorded rows",
    "distinct": "Distinct identifiers",
    "mean": "Mean recorded value",
    "median": "Median recorded value",
    "sum": "Total amount",
    "weighted_mean": "Weighted mean",
}


def workspace():
    if "investigation" not in st.session_state:
        st.session_state.investigation = Session()
    return st.session_state.investigation


def configuration():
    try:
        secrets = dict(st.secrets)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        secrets = {}
    return settings_from(secrets)


@st.cache_resource(max_entries=1)
def executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="first-look")


def _revision(state):
    return state.assistance_context


@st.fragment(run_every=1.0)
def poll_work():
    job = st.session_state.get("work")
    if not job:
        return
    if not job["future"].done():
        st.caption("Thinking alongside you… Your local views are still available.")
        return
    state = workspace()
    try:
        payload = job["future"].result()
        matches = (
            state.context == job["context"]
            if job["kind"] == "prediction"
            else _revision(state) == job["revision"]
        )
        if state.ds and matches:
            if job["kind"] == "assistance":
                state.accept_assistance(payload, job["context"])
            else:
                state.accept_prediction(payload, job["context"])
            st.session_state.notice = (
                "Your predictive comparison is ready."
                if job["kind"] == "prediction"
                else "A fresh perspective is ready beside your evidence."
            )
        else:
            if job["kind"] == "assistance" and state.ds:
                state.accept_assistance(payload, job["context"], retain_stale=True)
            st.session_state.notice = (
                "You moved on while that work was running, so I kept your current investigation."
            )
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, ValueError)
            else "That connection did not finish. Your local work is still here."
        )
        st.session_state.notice = message
        if job["kind"] == "assistance" and state.ds:
            state.accept_assistance({"status": "unavailable", "errors": [message]}, job["context"])
    del st.session_state["work"]
    st.rerun()


def title_for(ds, request):
    if request.view == "missingness":
        return "Where is information missing?"
    if request.view == "multivariate":
        return "How do these quantities vary together?"
    x = ds.label(request.x)
    if request.view == "distribution":
        return "How does " + x + " vary?"
    if request.view == "relationship":
        return x + " and " + ds.label(request.y)
    if request.view == "groups":
        return x + " across " + ds.label(request.group)
    if request.view == "time":
        return (METRICS[request.metric] if not request.y else ds.label(request.y)) + " over " + x
    if request.view == "spatial":
        return "Where were these locations recorded?"
    if request.view == "category_relationship":
        return ds.label(request.y) + " within " + x
    return (METRICS[request.metric] if not request.y else ds.label(request.y)) + " by " + x


def _scope(state):
    ds = state.ds
    st.caption(
        f"{ds.name} · {len(state.rows) if state.rows is not None else len(ds.frame):,} active records · {len(ds.fields)} fields"
    )


def _context_form(state, location):
    with st.form("context_" + location, border=False):
        question = st.text_input(
            "What would you like to understand?",
            value=state.question,
            max_chars=1000,
            placeholder="A question is a good start. Curiosity is enough, too.",
        )
        notes = st.text_area(
            "What should I know about this table?",
            value=state.notes,
            max_chars=4000,
            height=85,
            placeholder="Optional: what a record represents, how values were collected, or what matters to you.",
        )
        if st.form_submit_button("Keep this context", icon=":material/edit_note:"):
            state.question, state.notes = question.strip(), notes.strip()
            state.assistance = {}
            st.session_state.notice = "I’ll keep that beside the evidence."
            st.rerun()


def _open_file(state):
    with st.container(border=True):
        st.subheader("Start with your table")
        uploaded = st.file_uploader(
            "Choose a CSV or Parquet file",
            type=["csv", "parquet"],
            key="upload_" + str(st.session_state.get("upload_epoch", 0)),
            help="Up to 25 MiB, 50,000 records and 80 fields.",
        )
        with st.popover("File reading options", icon=":material/tune:"):
            delimiter = st.selectbox("CSV separator", [",", ";", "\t", "|"], key="separator")
            encoding = st.selectbox("Text encoding", ["utf-8-sig", "utf-8", "latin-1"], key="encoding")
            tokens = st.text_input(
                "Treat these literal values as missing",
                key="missing_tokens",
                help="Optional comma-separated values. Empty cells are missing; literal NA is otherwise preserved.",
            )
        st.caption(
            "First Look uses Jev and Terra to review bounded summaries, views and the context you supply. Predictive checks use TabPFN and share selected predictor values. Keys are managed by the app owner; there’s nothing to configure."
        )
        if uploaded:
            raw = uploaded.getvalue()
            parser_key = digest([delimiter, encoding, tokens])
            file_key = digest([hashlib.sha256(raw).hexdigest(), parser_key])
            if st.session_state.get("opened_file") != file_key:
                try:
                    with st.spinner("Getting to know the shape of your table…"):
                        ds = load_table(
                            raw,
                            uploaded.name,
                            delimiter,
                            encoding,
                            [v.strip() for v in tokens.split(",") if v.strip()],
                        )
                        state.load(ds)
                    st.session_state.opened_file = file_key
                    st.session_state.pop("waiting", None)
                    old_work = st.session_state.pop("work", None)
                    if old_work:
                        old_work["future"].cancel()
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def data_page():
    state = workspace()
    if state.ds is None:
        st.space("medium")
        left, right = st.columns([1.15, 1], gap="large", vertical_alignment="center")
        with left:
            st.caption("YOUR DATA. YOUR QUESTIONS.")
            st.title("Hi, I’m First Look.")
            st.markdown(
                "Bring a table you know a little about. We’ll explore what’s in it, follow what catches your eye, and check the choices that could change its meaning."
            )
            st.markdown("**You bring the context. I’ll help with the calculations and comparisons.**")
            st.caption("A good investigation starts with noticing something—not knowing every answer.")
        with right:
            _open_file(state)
        st.space("medium")
        with st.container(horizontal=True, gap="large"):
            st.caption(":material/visibility: See useful views straight away")
            st.caption(":material/compare_arrows: Make sense of the differences")
            st.caption(":material/bookmarks: Keep the evidence and your thinking")
        st.caption("Open source · entirely Python · First Look " + __version__)
        return
    st.title("Your table is ready.")
    st.caption("DEFINE · Start with what you want to understand. Refine the question as you learn.")
    _scope(state)
    st.markdown(
        "I’ve made a first view of the recorded data. Follow something that interests you; we’ll refine its meaning when it matters."
    )
    context, preview, perspective = st.columns([1, 1.65, 1], gap="large")
    with context:
        _context_form(state, "data")
        if st.button("Let’s explore", type="primary", key="start_exploring", icon=":material/arrow_forward:"):
            if state.current is None:
                state.run(starting_requests(state.ds)[0])
            st.switch_page("app_pages/investigate.py")
        with st.popover("Open another table", icon=":material/upload_file:"):
            _open_file(state)
    with preview:
        if state.current:
            draw(state.ds, state.current, "first_view", height=400)
    with perspective:
        assistance_controls(state)
    st.subheader("A little orientation")
    st.caption(
        "Fields describe what was recorded. Their names and patterns are clues; your knowledge gives them meaning."
    )
    inspect_fields(state)


def inspect_fields(state):
    ds = state.ds
    selected = st.selectbox(
        "Look at a field",
        [f.id for f in ds.fields],
        format_func=ds.label,
        key="inspect_field_" + ds.fingerprint,
    )
    f = ds.field(selected)
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        st.caption(f"{f.distinct:,} distinct recorded values · {f.missing:,} missing")
        st.dataframe(
            ds.frame[[f.id]].head(8).rename(columns={f.id: ds.label(f.id)}),
            hide_index=True,
            alt="A few records from your selected field",
        )
    with right:
        with st.form("field_" + selected, border=False):
            role = st.selectbox(
                "Use this field as",
                ["number", "category", "time", "identifier", "text"],
                index=["number", "category", "time", "identifier", "text"].index(f.kind),
            )
            unit = st.text_input(
                "Unit, if you know it",
                value=state.meanings.get(selected, Meaning(unit=f.unit)).unit,
                max_chars=80,
            )
            if st.form_submit_button("Update field", icon=":material/check:"):
                try:
                    state.set_role(selected, role)
                    if role == "number":
                        state.declare(
                            selected, replace(state.meanings.get(selected, Meaning()), unit=unit.strip())
                        )
                    st.session_state.notice = "Updated. Saved views keep their original definition."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        for warning in f.warnings:
            st.caption(warning)


def draw(ds, result, key, height=400, comparison=None, compact=False):
    st.markdown("**" + title_for(ds, result.request) + "**")
    if result.request.view == "spatial":
        if result.table:
            st.map(
                pd.DataFrame(result.table),
                latitude="latitude",
                longitude="longitude",
                size=45,
                color="#3157CE",
                height=440,
                alt="Recorded locations in the selected latitude and longitude fields",
            )
        else:
            st.info("There are no complete recorded locations in this scope.")
    elif result.request.view == "relationship" and not compact:
        chart, context = st.columns([1.1, 1], gap="large")
        with chart:
            st.echarts_chart(
                options(ds, result, comparison), height=540, key=key, alt=title_for(ds, result.request)
            )
        with context:
            st.space("small")
            st.markdown("**Read the pattern, then question it.**")
            st.caption(
                "Look for direction, curvature, unusual points and changes in spread. A correlation summarizes a straight-line association; it can miss other patterns."
            )
            summary = result.summary
            a, b = st.columns(2)
            a.metric("Complete pairs", f"{summary.get('n', 0):,}")
            corr = summary.get("correlation")
            b.metric("Pearson correlation", "Not defined" if corr is None else f"{corr:.3f}")
            if result.meta.get("group_stats"):
                st.dataframe(
                    pd.DataFrame(result.meta["group_stats"]).rename(
                        columns={"label": "Group", "n": "Pairs", "correlation": "Correlation"}
                    ),
                    hide_index=True,
                    alt="Within-group associations alongside the pooled plot",
                )
            st.caption(
                "A shared direction can disappear or reverse within groups. Use a grouping you have reason to consider; this view cannot establish causality."
            )
    else:
        if result.request.view == "category_relationship":
            from firstlook.perspectives import categorical_layout

            _, rows, row_height = categorical_layout(result)
            height = rows * row_height
        st.echarts_chart(
            options(ds, result, comparison),
            height=max(height, 540) if result.request.view == "relationship" else height,
            key=key,
            alt=title_for(ds, result.request),
        )
    st.caption(result.definition)
    st.caption(f"{len(result.rows):,} records in scope · {result.omitted:,} omitted from this calculation")
    for warning in result.warnings:
        st.caption(warning)


def draw_comparison(ds, comparison, key):
    """Keep a matched pair together within the desktop investigation canvas."""
    st.caption(comparison.definition)
    left, right = st.columns(2, gap="medium")
    for column, name, label in [
        (left, "selected", "YOUR SELECTED GROUP"),
        (right, "reference", "THE REFERENCE"),
    ]:
        part = getattr(comparison, name)
        with column:
            st.caption(label)
            draw(ds, part, key + "_" + name + "_" + part.id, compact=True)


def _candidate_requests(state):
    """A small relevant frontier; models rank permitted views rather than invent code."""
    current, ds = state.current.request, state.ds
    nums = [f.id for f in ds.fields if f.kind == "number"]
    groups = [f.id for f in ds.fields if f.kind == "category" and 2 <= f.distinct <= 8]
    candidates = []
    if current.view == "relationship" and groups and not current.group:
        candidates.append(replace(current, group=groups[0]))
    if current.view in {"distribution", "relationship"} and groups:
        candidates.append(Request("groups", current.x, group=groups[0]))
    if current.view == "groups":
        candidates.append(Request("distribution", current.x, representation="quantile"))
    if current.view == "categories" and nums and current.x in groups:
        candidates.append(Request("groups", nums[0], group=current.x))
    if current.view == "time":
        candidates.append(
            replace(current, representation="bars" if current.representation != "bars" else "auto")
        )
    candidates.extend(starting_requests(ds))
    if any(f.missing for f in ds.fields):
        candidates.insert(1, Request("missingness"))
    unique = {}
    for candidate in candidates:
        if candidate != current:
            unique.setdefault(
                digest(candidate),
                {"id": digest(candidate), "request": asdict(candidate), "label": title_for(ds, candidate)},
            )
    return list(unique.values())[:3] or [
        {"id": digest(current), "request": asdict(current), "label": title_for(ds, current)}
    ]


def run_request(state, request):
    try:
        state.run(request)
        st.session_state.pop("waiting", None)
    except ChoiceRequired as exc:
        st.session_state.waiting = {
            "request": asdict(request),
            "context": state.context,
            "field": exc.field,
            "message": str(exc),
            "evidence": clean(exc.evidence),
        }
    except ValueError as exc:
        st.session_state.notice = str(exc)


def view_controls(state):
    ds = state.ds
    nums = [f.id for f in ds.fields if f.kind == "number"]
    cats = [f.id for f in ds.fields if f.kind in {"category", "identifier"}]
    times = [f.id for f in ds.fields if f.kind == "time"]
    choices = [
        v
        for v in VIEWS
        if v == "missingness"
        or v == "distribution"
        and nums
        or v == "categories"
        and cats
        or v == "groups"
        and nums
        and cats
        or v in {"relationship", "multivariate", "spatial"}
        and len(nums) >= 2
        or v == "time"
        and times
        or v == "category_relationship"
        and len(cats) >= 2
    ]
    current = state.last_request or starting_requests(ds)[0]
    key = "perspective_" + ds.fingerprint + "_" + current.view
    st.caption(
        "PLAN → EXECUTE · Choose an angle that helps your question. Each view states exactly what it counts or summarizes."
    )
    selector, body = st.columns([1, 2.2], gap="medium")
    view = selector.selectbox(
        "Look from another angle",
        choices,
        index=choices.index(current.view) if current.view in choices else 0,
        format_func=lambda v: VIEWS[v],
        key=key,
    )
    with body, st.form("view_controls_" + view, border=False):
        row = st.columns(3, gap="small")
        x, y, group, entity, weight, period, zero, metric = "", None, None, None, None, "MS", False, "count"
        many, confirmed = [], True
        with row[0]:
            fields = (
                nums
                if view in {"distribution", "groups", "relationship", "spatial"}
                else times
                if view == "time"
                else cats
            )
            if view == "multivariate":
                many = st.multiselect(
                    "Quantities to compare",
                    nums,
                    default=current.fields if current.view == view and current.fields else nums[:3],
                    max_selections=6,
                    format_func=ds.label,
                )
            elif view != "missingness":
                x = st.selectbox(
                    "Latitude" if view == "spatial" else "Look at",
                    fields,
                    index=fields.index(current.x) if current.x in fields else 0,
                    format_func=ds.label,
                )
        with row[1]:
            if view in {"relationship", "spatial", "category_relationship"}:
                # Form options/defaults must stay stable while batched inputs are
                # submitted. Filtering by the newly submitted x resets y's widget.
                other = cats if view == "category_relationship" else nums
                initial_x = current.x if current.x in fields else fields[0]
                initial_y = (
                    current.y
                    if current.y in other and current.y != initial_x
                    else next(f for f in other if f != initial_x)
                )
                y = st.selectbox(
                    "Alongside",
                    other,
                    index=other.index(initial_y),
                    format_func=ds.label,
                )
            elif view == "groups":
                group = st.selectbox(
                    "Across groups",
                    cats,
                    index=cats.index(current.group) if current.group in cats else 0,
                    format_func=ds.label,
                )
            elif view in {"categories", "time"}:
                metrics = ["count", "distinct"] + (["mean", "median", "sum", "weighted_mean"] if nums else [])
                metric = st.selectbox(
                    "Compare",
                    metrics,
                    index=metrics.index(current.metric) if current.metric in metrics else 0,
                    format_func=lambda v: METRICS[v],
                )
            elif view == "multivariate":
                group = st.selectbox(
                    "Compare profiles by",
                    [None] + cats,
                    index=([None] + cats).index(current.group) if current.group in cats else 0,
                    format_func=lambda v: "Individual complete records" if v is None else ds.label(v),
                )
        with row[2]:
            if view == "relationship":
                group = st.selectbox(
                    "Colour by",
                    [None] + cats,
                    index=([None] + cats).index(current.group) if current.group in cats else 0,
                    format_func=lambda v: "All recorded pairs" if v is None else ds.label(v),
                )
            if view == "time":
                period = st.selectbox(
                    "Time interval",
                    ["D", "W", "MS"],
                    index=["D", "W", "MS"].index(current.period),
                    format_func=lambda v: {"D": "Day", "W": "Week", "MS": "Month"}[v],
                )
            if view == "multivariate":
                metric = st.selectbox(
                    "Group summary, when grouped", ["mean", "median", "sum"], format_func=lambda v: METRICS[v]
                )
        modes = {
            "distribution": {
                "auto": "Histogram · recorded frequencies",
                "frequency": "Frequency polygon · see the shape",
                "quantile": "Quantiles · values and cumulative fractions",
                "box": "Box · median, middle half and full range",
            },
            "groups": {
                "auto": "Frequency lines · common bins and within-group shares",
                "box": "Boxes · centres and spread",
            },
            "categories": {
                "auto": "Ranked bars · compare precisely",
                "treemap": "Treemap · composition of a nonnegative total",
            },
            "time": {
                "auto": "Line · preserve gaps",
                "bars": "Bars · interval amounts",
                "share": "Line · fraction of series total",
                "smooth": "Line · trailing three-period mean",
                "deviation": "Line · deviation from trailing mean",
                "calendar": "Heatmap · recorded weekday and hour",
            },
            "category_relationship": {
                "auto": "Small multiples · recorded counts",
                "share": "Small multiples · shares within each group",
            },
        }
        mode = "auto"
        if view in modes:
            choices_mode = list(modes[view])
            target = (
                row[1]
                if view == "distribution"
                else row[2]
                if view in {"groups", "categories", "category_relationship"}
                else st.container()
            )
            with target:
                mode = st.selectbox(
                    "Representation",
                    choices_mode,
                    index=choices_mode.index(current.representation)
                    if current.representation in choices_mode
                    else 0,
                    format_func=lambda v: modes[view][v],
                )
        if view == "spatial":
            st.caption(
                "Use a map when location could explain the pattern. Basemap tiles load from an external map service."
            )
            confirmed = st.checkbox(
                "These fields are latitude and longitude in degrees; geography matters to my question"
            )
        if view == "multivariate":
            st.caption(
                "With groups: aligned numerical profiles, ranked on the first quantity (up to four fields and twelve groups). Without groups: up to six axes for complete recorded profiles, with each axis on its own scale."
            )
        # Conditional controls are outside intermediate reruns; choosing a metric updates on submit.
        if view in {"categories", "time"}:
            y = st.selectbox(
                "Value, for a numerical summary",
                [None] + nums,
                index=([None] + nums).index(current.y) if current.y in nums else 0,
                format_func=lambda v: "Choose only when summarising a value" if v is None else ds.label(v),
            )
            with st.popover("Only if your question needs it", icon=":material/tune:"):
                entity = st.selectbox(
                    "Identifier for a distinct count",
                    [None] + cats,
                    index=([None] + cats).index(current.entity) if current.entity in cats else 0,
                    format_func=lambda v: "Not used" if v is None else ds.label(v),
                )
                weight = st.selectbox(
                    "Weight for a weighted mean",
                    [None] + nums,
                    index=([None] + nums).index(current.weight) if current.weight in nums else 0,
                    format_func=lambda v: "Not used" if v is None else ds.label(v),
                )
                if view == "time":
                    zero = st.checkbox(
                        "Show absent event periods as zero",
                        help="This will ask about recording completeness if it has not been established.",
                    )
        if st.form_submit_button("Look at this", type="primary", icon=":material/query_stats:"):
            if confirmed:
                run_request(
                    state,
                    Request(
                        cast(View, view),
                        x,
                        y
                        if metric not in {"count", "distinct"}
                        or view in {"relationship", "spatial", "category_relationship"}
                        else None,
                        group,
                        cast(Metric, metric),
                        entity if metric == "distinct" else None,
                        weight if metric == "weighted_mean" else None,
                        cast(Literal["D", "W", "MS"], period),
                        zero,
                        fields=many,
                        representation=mode,
                    ),
                )
            else:
                st.session_state.notice = (
                    "Confirm the coordinate system and why a map helps before placing these values on a map."
                )
            st.rerun()


def meaning_choice(state):
    pending = st.session_state.get("waiting")
    if not pending:
        return
    if pending["context"] != state.context:
        st.session_state.pop("waiting", None)
        return
    ds, fid = state.ds, pending["field"]
    request = Request(**pending["request"])
    with st.container(border=True):
        st.subheader("One thing your knowledge can settle")
        st.markdown(pending["message"])
        proof, controls = st.columns([1, 1.2], gap="large")
        if pending["evidence"]:
            proof.dataframe(
                pd.DataFrame([pending["evidence"]])
                if all(not isinstance(v, (list, dict)) for v in pending["evidence"].values())
                else pd.DataFrame(
                    ds.frame[
                        [c for c in [fid, request.entity, state.meanings.get(fid, Meaning()).entity] if c]
                    ]
                    .head(3)
                    .rename(columns={f.id: ds.label(f.id) for f in ds.fields})
                ),
                hide_index=True,
                alt="Source evidence for this analytical choice",
            )
        else:
            proof.caption(
                "A few recorded values. The recording process and intended question determine how they can be interpreted."
            )
            proof.dataframe(
                ds.frame[[fid]].head(3).rename(columns={fid: ds.label(fid)}),
                hide_index=True,
                alt="Recorded values beside the requested context decision",
            )
        if request.zero_fill and ds.field(fid).kind == "time":
            complete = controls.checkbox(
                "Every event was recorded for the periods I want to compare", key="complete_events"
            )
            through = controls.date_input("Last complete date", key="complete_through")
            if controls.button("Use this recording context", disabled=not complete, key="confirm_time"):
                try:
                    state.set_time_rule(
                        fid, TimeRule(True, True, through.isoformat()), expected_context=pending["context"]
                    )
                    run_request(state, request)
                    st.rerun()
                except ValueError as exc:
                    controls.error(str(exc))
        elif request.metric == "distinct" and not request.entity:
            identifiers = [f.id for f in ds.fields if f.kind in {"identifier", "category"}]
            entity = controls.selectbox(
                "Count each distinct…", identifiers, format_func=ds.label, key="distinct_entity"
            )
            if controls.button("Count this identifier", key="confirm_distinct"):
                run_request(state, replace(request, entity=entity))
                st.rerun()
        elif request.metric == "weighted_mean" and not request.weight:
            weights = [f.id for f in ds.fields if f.kind == "number" and f.id != fid]
            if weights:
                weight = controls.selectbox(
                    "The intended exposure or weight is…", weights, format_func=ds.label, key="meaning_weight"
                )
                if controls.button("Use this weight", key="confirm_weight"):
                    run_request(state, replace(request, weight=weight))
                    st.rerun()
            else:
                controls.caption(
                    "There is no separate numeric weight. Keep exploring without a weighted summary."
                )
        elif pending["evidence"].get("overlapping_entities"):
            allocation = controls.radio(
                "When an identifier belongs to several groups…",
                [
                    "Choose how it should contribute",
                    "Give each group the full amount",
                    "Split equally across its recorded groups",
                ],
                key="allocation",
            )
            if controls.button(
                "Use this attribution", disabled=allocation.startswith("Choose"), key="confirm_attribution"
            ):
                run_request(state, replace(request, attribution="full" if "full" in allocation else "equal"))
                st.rerun()
        else:
            if ds.field(fid).kind == "number":
                frame = ds.frame if state.rows is None else ds.frame.loc[state.rows]
                alternatives = [
                    {
                        "Interpretation": "Each recorded row contributes",
                        "Total if additive": frame[fid].sum(min_count=1),
                    }
                ]
                for candidate in [
                    f
                    for f in ds.fields
                    if f.kind in {"identifier", "category"} and 1 < f.distinct < len(ds.frame)
                ][:3]:
                    valid = frame.dropna(subset=[candidate.id])
                    if valid.groupby(candidate.id)[fid].nunique(dropna=False).max() <= 1:
                        alternatives.append(
                            {
                                "Interpretation": "Once per " + ds.label(candidate.id),
                                "Total if additive": valid.drop_duplicates(candidate.id)[fid].sum(
                                    min_count=1
                                ),
                            }
                        )
                if request.metric == "sum" and len(alternatives) > 1:
                    proof.caption(
                        "These totals illustrate the consequence of different meanings. Matching values do not establish which meaning is right."
                    )
                    proof.dataframe(
                        pd.DataFrame(alternatives),
                        hide_index=True,
                        alt="How the total changes under candidate value grains",
                    )
            choice = controls.radio(
                "How is this quantity recorded?",
                [
                    "One amount per recorded row",
                    "An amount repeated from an identifier",
                    "Not an additive amount",
                ],
                index=None,
                key="quantity_choice",
            )
            entity = None
            if choice == "An amount repeated from an identifier":
                identifiers = [
                    f.id
                    for f in ds.fields
                    if f.kind in {"identifier", "category"} and 1 < f.distinct < len(ds.frame)
                ]
                if identifiers:
                    entity = controls.selectbox(
                        "The amount belongs once to each…",
                        identifiers,
                        format_func=ds.label,
                        key="quantity_entity",
                    )
                else:
                    controls.caption(
                        "No repeated identifier is available in this table. Keep the meaning unresolved until it can be identified."
                    )
            if controls.button(
                "Use this meaning",
                type="primary",
                disabled=choice is None
                or choice == "An amount repeated from an identifier"
                and entity is None,
                key="confirm_meaning",
            ):
                try:
                    old = state.meanings.get(fid, Meaning(unit=ds.field(fid).unit))
                    state.declare(
                        fid,
                        Meaning(
                            "nonadditive" if choice == "Not an additive amount" else "additive",
                            entity,
                            old.unit,
                            "Declared while investigating: " + str(choice),
                        ),
                        expected_context=pending["context"],
                    )
                    run_request(
                        state,
                        replace(request, metric="mean") if choice == "Not an additive amount" else request,
                    )
                    st.rerun()
                except ValueError as exc:
                    controls.error(str(exc))
        if controls.button("I’m not sure—keep exploring recorded values", key="keep_unknown"):
            st.session_state.pop("waiting", None)
            if state.current is None:
                run_request(state, replace(request, zero_fill=False, metric="mean" if request.y else "count"))
            st.rerun()


def investigate_page():
    state = workspace()
    if state.ds is None:
        st.title("Let’s begin with your data.")
        st.caption("A table you care about gives our questions a place to start.")
        st.page_link("app_pages/data.py", label="Open your table", icon=":material/upload_file:")
        return
    heading, context = st.columns([3, 1], vertical_alignment="center")
    heading.title(state.question or "What catches your eye?")
    with context, st.popover("Question and context", icon=":material/edit_note:"):
        _context_form(state, "investigate")
    _scope(state)
    view_controls(state)
    meaning_choice(state)
    if state.current is None and not st.session_state.get("waiting"):
        run_request(state, state.last_request or starting_requests(state.ds)[0])
    canvas, companion = st.columns([2.9, 1], gap="large")
    with canvas:
        if state.current:
            if state.comparison:
                draw_comparison(state.ds, state.comparison, "active")
            else:
                draw(state.ds, state.current, "view_" + state.current.id)
            with st.container(horizontal=True, gap="small"):
                if st.button("Keep this view", icon=":material/bookmark:", key="keep_view"):
                    state.save_result()
                    st.session_state.notice = (
                        "Kept with its definition. You can add your interpretation in Record."
                    )
                    st.rerun()
                with st.popover("Exact values", icon=":material/table:"):
                    values = state.current.meta.get(
                        "plotted_values",
                        state.current.meta.get(
                            "calendar_cells",
                            state.current.meta.get("quantiles")
                            if state.current.request.representation == "quantile"
                            else state.current.table,
                        ),
                    )
                    display = pd.DataFrame(values).drop(columns=["rows"], errors="ignore")
                    if "row" in display:
                        display["row"] += 1
                    display = display.rename(
                        columns={
                            **{f.id: state.ds.label(f.id) for f in state.ds.fields},
                            "row": "Record position",
                        }
                    )
                    st.dataframe(display, hide_index=True, alt="Calculated values supporting this view")
                    if state.current.meta.get("support"):
                        st.caption("Nonmissing support for each quantity and group")
                        st.dataframe(
                            pd.DataFrame(state.current.meta["support"]).rename(
                                columns={f.id: state.ds.label(f.id) for f in state.ds.fields}
                            ),
                            hide_index=True,
                            alt="Separate support behind each ranked numerical summary",
                        )
                if state.comparison and st.button("Return to the whole view", key="clear_comparison"):
                    state.comparison = None
                    state.assistance = {}
                    st.rerun()
            guidance = {
                "distribution": "A typical value is only part of the story. Look at spread, gaps and the tails before comparing averages.",
                "categories": "A count, a contribution and an average answer different questions. Keep the denominator in mind.",
                "groups": "Look beyond the average. Groups can have similar centres and very different shapes.",
                "relationship": "A pooled pattern can change within groups. Try a relevant grouping before interpreting it.",
                "time": "An absent period is not automatically a zero. The recording process matters.",
                "missingness": "Missing information may follow a pattern. It does not, by itself, tell us why it is missing.",
                "category_relationship": "Compare the same category across panels. Within-group shares answer a different question from counts.",
                "spatial": "A geographic pattern is useful when location matters to the question. Uneven sampling can create apparent clusters.",
                "multivariate": "Follow one pattern across the axes. Each quantity has its own units; similar shapes are a reason to investigate, not a verified grouping.",
            }
            st.caption(guidance[state.current.request.view])
            comparison_controls(state)
    with companion:
        assistance_controls(state)
        prediction_controls(state)


def comparison_controls(state):
    ds = state.ds
    if state.current.request.view in {
        "spatial",
        "multivariate",
        "category_relationship",
    } or state.current.request.representation in {"calendar", "treemap"}:
        return
    candidates = [f.id for f in ds.fields if f.kind == "category" and 1 < f.distinct <= 40]
    if not candidates:
        return
    with st.popover(
        "Compare a group with the rest", icon=":material/compare_arrows:", on_change="rerun"
    ) as panel:
        if not panel.open:
            return
        group = st.selectbox("Choose a grouping", candidates, format_func=ds.label)
        values = sorted(ds.frame[group].dropna().astype(str).unique())
        value = st.selectbox("The group you want to examine", values)
        if st.button("Put them side by side", key="compare_group"):
            active = list(ds.frame.index) if state.rows is None else state.rows
            rows = [int(i) for i in active if str(ds.frame.loc[i, group]) == value]
            reference = [int(i) for i in active if i not in set(rows)]
            try:
                state.comparison = compare(
                    ds, state.current.request, rows, state.meanings, reference, state.time_rules
                )
                state.assistance = {}
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def ensure_assistance(state, *, retry=False):
    """Review new analytical context once; returning to evidence reuses its review."""
    if state.ds is None or state.current is None:
        return
    context = state.assistance_context
    if retry:
        state.assistance_cache.pop(context, None)
    elif context in state.assistance_cache:
        state.assistance = copy.deepcopy(state.assistance_cache[context])
        return
    state.assistance = {}
    if st.session_state.get("work"):
        return
    try:
        cfg = configuration()
        packet = build_packet(
            state.ds, state.current, state.question, state.notes, _candidate_requests(state), state.comparison
        )
        packet["declared_meanings"] = clean(state.meanings)
        packet["recording_context"] = clean(state.time_rules)
        if state.prediction:
            packet["predictive_check"] = {
                k: state.prediction.get(k)
                for k in [
                    "id",
                    "definition",
                    "task",
                    "target",
                    "predictors",
                    "split",
                    "split_field",
                    "warnings",
                ]
            }
            packet["predictive_check"]["models"] = [
                {k: model.get(k) for k in ["name", "metric", "score"]}
                for model in state.prediction.get("models", [])
            ]
            packet["predictive_check"]["support"] = {
                "training": len(state.prediction.get("train_ids", [])),
                "held_out": len(state.prediction.get("test_ids", [])),
            }
        key = digest([packet, cfg.openai_model, cfg.typesafe_model])
        if retry:
            state.assistance_requests.discard(key)
        if key in state.assistance_requests:
            return
        state.begin_assistance(key)
        st.session_state.work = {
            "future": executor().submit(
                assist_view,
                replace(state.ds, fields=copy.deepcopy(state.ds.fields)),
                copy.deepcopy(state.current),
                packet,
                cfg,
            ),
            "kind": "assistance",
            "context": context,
            "revision": context,
        }
    except ValueError as exc:
        state.accept_assistance({"status": "unavailable", "errors": [str(exc)]}, context)


def assistance_controls(state):
    ensure_assistance(state)
    with st.container(border=True):
        st.markdown("**A perspective alongside your evidence**")
        st.caption("Jev and Terra review this evidence in the context of your question.")
        if st.session_state.get("work", {}).get("kind") == "assistance":
            st.caption(
                "Reviewing this view and its context… You can keep exploring."
                if st.session_state.work["context"] == state.assistance_context
                else "Finishing the previous review; this view is next. You can keep exploring."
            )
        if state.assistance:
            answer = state.assistance
            if answer.get("interpretation"):
                st.markdown(answer["interpretation"])
                st.caption("A model interpretation of the supplied evidence—not a confirmed conclusion.")
            if answer.get("clarification"):
                st.markdown("**A question to consider:** " + answer["clarification"])
                st.caption("Your question and notes guide the next review.")
            if answer.get("hypotheses"):
                with st.popover("Possible field meanings", icon=":material/help_outline:"):
                    st.caption(
                        "Unconfirmed hypotheses. Review these when a field’s meaning matters to your question; they do not authorize an aggregation."
                    )
                    for hypothesis in answer.get("hypotheses", []):
                        st.caption(
                            "Unconfirmed meaning for "
                            + state.ds.label(hypothesis["field"])
                            + ": "
                            + hypothesis["reason"]
                        )
            for suggestion in answer.get("suggestions", []):
                judgment = next(
                    (j for j in answer.get("judgments", []) if j.get("candidate") == suggestion["id"]), None
                )
                if judgment:
                    st.caption(
                        "Jev’s relevance judgment: "
                        + judgment["status"]
                        + ". This is a judgment, not a measured finding."
                    )
                if st.button(suggestion["label"], key="suggestion_" + suggestion["id"]):
                    run_request(state, Request(**suggestion["request"]))
                    st.rerun()
            for error in answer.get("errors", []):
                st.caption(error)

            if answer.get("errors") and st.button(
                "Try this review again", key="retry_assistance", disabled=bool(st.session_state.get("work"))
            ):
                ensure_assistance(state, retry=True)
                st.rerun()


def prediction_controls(state):
    with st.popover(
        "Would a predictive check help?", icon=":material/model_training:", on_change="rerun"
    ) as panel:
        if not panel.open:
            return
        st.caption(
            "Use this only if predicting a recorded quantity helps your question. This is a retrospective diagnostic, not evidence of causality or a promise about future use. We keep one fixed experiment so the holdout stays useful."
        )
        cfg, ds = configuration(), state.ds
        targets = [
            f.id for f in ds.fields if f.kind in {"number", "category"} and len(ds.frame) - f.missing >= 200
        ]
        if not targets:
            st.caption(
                "This check needs at least 200 labelled records and a suitable numeric or categorical target. There is plenty to explore without fitting a model."
            )
            return
        target = st.selectbox("What would you try to predict?", targets, format_func=ds.label)
        candidates = [f.id for f in ds.fields if f.id != target and f.kind in {"number", "category"}]
        predictors = st.multiselect(
            "Which recorded fields are appropriate predictors?",
            candidates,
            default=candidates[:12],
            format_func=ds.label,
        )
        repeated = [f.id for f in ds.fields if f.kind == "identifier" and 3 <= f.distinct < len(ds.frame)]
        split = st.selectbox(
            "What should the held-out cases represent?",
            ["random", "group", "time"],
            index=1 if repeated else 0,
            format_func=lambda v: {
                "random": "Other recorded rows",
                "group": "Unseen groups",
                "time": "Later recorded observations",
            }[v],
        )
        split_field = None
        if split != "random":
            fields = [f.id for f in ds.fields if f.kind == "time"] if split == "time" else repeated
            if not fields:
                st.caption("This table does not have a suitable field for that split.")
                return
            split_field = st.selectbox("Split on", fields, format_func=ds.label)
        st.caption(
            "TabPFN is included automatically alongside a simple reference and a linear or logistic baseline. Choose the prediction question and holdout that fit your investigation."
        )
        appropriate = st.checkbox(
            "This target, predictor set and split match the question I’m investigating",
            key="prediction_context",
        )
        if st.button(
            "Run this one predictive check",
            key="predict",
            disabled=not appropriate
            or not predictors
            or state.prediction_used
            or bool(st.session_state.get("work")),
        ):
            try:
                from firstlook.prediction import predict_structure

                context = state.begin_prediction()
                future = executor().submit(
                    predict_structure,
                    replace(ds, fields=copy.deepcopy(ds.fields)),
                    target,
                    predictors,
                    split,
                    split_field,
                    state.rows,
                    cfg,
                    meanings=copy.deepcopy(state.meanings),
                )
                st.session_state.work = {
                    "future": future,
                    "kind": "prediction",
                    "context": context,
                    "revision": _revision(state),
                }
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
        if state.prediction:
            _prediction_result(state.prediction)
    if state.prediction:
        st.caption("A predictive check is recorded for this investigation.")


def _prediction_result(run):
    st.markdown("**What the held-out comparison showed**")
    st.caption(run.get("definition", ""))
    st.dataframe(
        [{k: m.get(k) for k in ["name", "metric", "score"]} for m in run.get("models", [])],
        hide_index=True,
        alt="Predictive scores under one fixed holdout",
    )
    for warning in run.get("warnings", []):
        st.caption(warning)


def _recorded_result(raw):
    payload: dict[str, Any] = dict(raw)
    payload["request"] = Request(**payload["request"])
    return Result(**payload)


def record_page():
    state = workspace()
    st.title("What’s worth keeping?")
    st.caption("REFLECT · What does the evidence support? What changed your mind? What remains uncertain?")
    st.caption(
        "Keep the views and explanations you’d want someone else to see. Your interpretation can change as you investigate."
    )
    if state.ds:
        _scope(state)
        canvas, notes = st.columns([2.9, 1], gap="large")
        with canvas:
            if state.record:
                ids = [r["id"] for r in state.record]
                chosen = st.selectbox(
                    "A view in your record",
                    ids,
                    format_func=lambda v: next(
                        title_for(state.ds, Request(**r["result"]["request"]))
                        for r in state.record
                        if r["id"] == v
                    ),
                    key="saved_view",
                )
                saved = next(r for r in state.record if r["id"] == chosen)
                result = _recorded_result(saved["result"])
                saved_ds = replace(state.ds, fields=[Field(**f) for f in saved["fields"]])
                if saved.get("comparison"):
                    raw = saved["comparison"]
                    comparison = Comparison(
                        _recorded_result(raw["selected"]),
                        _recorded_result(raw["reference"]),
                        raw["definition"],
                    )
                    draw_comparison(saved_ds, comparison, "saved_" + chosen)
                else:
                    draw(saved_ds, result, "saved_" + chosen)
            else:
                st.markdown("Your record starts with a view that matters to you.")
                st.page_link(
                    "app_pages/investigate.py",
                    label="Return to your investigation",
                    icon=":material/explore:",
                )
            if state.prediction:
                _prediction_result(state.prediction)
        with notes:
            if state.record:
                with st.form("note_" + chosen, border=False):
                    note = st.text_area(
                        "What do you notice—or want to check next?",
                        value=saved.get("note", ""),
                        max_chars=2000,
                        height=180,
                    )
                    if st.form_submit_button("Keep this interpretation", icon=":material/edit_note:"):
                        state.update_note(chosen, note)
                        st.rerun()
            with st.container(border=True):
                st.markdown("**Take your investigation with you**")
                st.caption(
                    "Saved views, notes and model records can contain data values even when the original file is omitted. Choose what you’re comfortable sharing."
                )
                include = st.checkbox("Include the original table", key="include_original")
                if st.button(
                    "Prepare my record",
                    key="prepare_record",
                    type="primary",
                    disabled=not state.record and not state.prediction,
                ):
                    try:
                        st.session_state.downloads = {
                            "bundle": export(state, include),
                            "markdown": readable_markdown(state),
                            "scope": digest(
                                [state.record, state.prediction, include, state.provider_history]
                            ),
                        }
                    except ValueError as exc:
                        st.error(str(exc))
                downloads = st.session_state.get("downloads", {})
                if downloads.get("scope") == digest(
                    [state.record, state.prediction, include, state.provider_history]
                ):
                    with st.container(horizontal=True):
                        st.download_button(
                            "Download readable record",
                            downloads["markdown"],
                            "first-look-record.md",
                            "text/markdown",
                            key="download_record",
                        )
                        st.download_button(
                            "Download reproducible evidence",
                            downloads["bundle"],
                            "first-look-evidence.zip",
                            "application/zip",
                            key="download_evidence",
                        )
    with st.popover("Open a saved investigation", icon=":material/folder_open:"):
        uploaded = st.file_uploader("Reopen evidence", type=["zip"], key="evidence_upload")
        if uploaded and st.button("Inspect this saved record", key="inspect_evidence"):
            try:
                saved = inspect_bundle(uploaded.getvalue())
                st.session_state.imported_record = saved
            except ValueError as exc:
                st.error(str(exc))
    if st.session_state.get("imported_record"):
        imported = st.session_state.imported_record
        st.caption(imported["verification"] + ". Opened without model calls.")
        st.markdown(imported["readable_markdown"])
        with st.popover("Recorded definitions and complete tables", icon=":material/data_object:"):
            st.json({k: v for k, v in imported.items() if k != "readable_markdown"}, expanded=False)
