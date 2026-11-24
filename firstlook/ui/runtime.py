"""UI orchestration keeps expensive work and provider calls out of reruns."""

import copy
from datetime import timedelta

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from firstlook.challenges import automatic_challenges
from firstlook.config import settings_from
from firstlook.contracts import digest
from firstlook.discovery import discover
from firstlook.discovery import Investigation, analyze, plan_for
from firstlook.ingest import Dataset
from firstlook.investigation import prioritize, run_terra
from firstlook.jobs import JobManager
from firstlook.modeling import diagnostic_findings, run_model, suggested_model_plan
from firstlook.providers.base import ProviderError
from firstlook.providers.language import TerraProvider
from firstlook.providers.tabpfn import TabPFNProvider
from firstlook.providers.typesafe import JevProvider
from firstlook.state import Workspace


@st.cache_resource(max_entries=1)
def manager() -> JobManager:
    return JobManager()


def workspace() -> Workspace:
    if "workspace" not in st.session_state:
        st.session_state.workspace = Workspace()
    return st.session_state.workspace


def settings():
    try:
        secret = dict(st.secrets)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        secret = {}
    return settings_from(secret)


def snapshot(ws: Workspace) -> Dataset:
    assert ws.dataset is not None
    return Dataset(ws.dataset.record.model_copy(deep=True), ws.dataset.frame, ws.dataset.raw)


def start_analysis(ws: Workspace, connected: bool = False) -> None:
    ds, ctx, cfg = snapshot(ws), ws.context(), settings()
    goal = str(ws.preparation_inputs.get("goal", ""))[:1000]
    if connected and not st.session_state.get("external_ok", False):
        raise ValueError("Enable external analysis for this dataset before connecting providers.")
    model_plan = suggested_model_plan(ds, ctx) if connected and ws.model_count < 2 else None
    if ws.job_id and ws.job_kind == "preparation" and not connected:
        # Preserve preparation's worker handle while allowing immediate local exploration.
        with st.spinner("Computing a local overview while connected preparation continues"):
            inv = discover(ds, ctx)
            inv.goal = goal
            automatic_challenges(ds, inv)
        ws.investigation = inv
        return

    def work(progress, cancelled):
        progress("Computing eligible analytical views")
        inv = discover(ds, ctx)
        inv.goal = goal
        if cancelled():
            return inv
        progress("Challenging the leading observations")
        automatic_challenges(ds, inv)
        jev = JevProvider(cfg) if connected and cfg.available("jev") else None
        if model_plan and not cancelled():
            try:
                target, split, split_field = model_plan
                progress("Comparing held-out predictive structure")
                run = run_model(
                    ds,
                    ctx,
                    target,
                    split,
                    split_field,
                    provider=TabPFNProvider(cfg) if cfg.available("tabpfn") else None,
                    progress=progress,
                    cancelled=cancelled,
                )
                inv.model_runs.append(run)
                diagnostic_findings(ds, inv, run)
            except (ProviderError, ValueError) as exc:
                inv.terra["model_note"] = str(exc)
        if jev and not cancelled():
            try:
                progress("Reviewing task relevance with atomic Jev judgments")
                prioritize(inv, jev, ds)
            except ProviderError as exc:
                inv.terra["provider_note"] = str(exc)
        if connected and cfg.available("terra") and not cancelled():
            try:
                run_terra(ds, inv, TerraProvider(cfg), jev, cfg.terra_visual_review, progress, cancelled)
            except ProviderError as exc:
                inv.terra.update(status="unavailable", note=str(exc))
        return inv

    ws.job_id = manager().submit(ws.owner, ctx.id, "connected" if connected else "analysis", work)
    ws.job_context, ws.job_kind = ctx.id, "connected" if connected else "analysis"


def start_model(
    ws: Workspace, target: str, split: str, split_field: str | None, predictors: list[str], hosted: bool
) -> None:
    if ws.model_count >= 2:
        raise ValueError(
            "This context has used its two model experiments. Change the analytical context for a new investigation."
        )
    ds, ctx, cfg = snapshot(ws), ws.context(), settings()
    if hosted and not st.session_state.get("external_ok", False):
        raise ValueError("Enable external analysis before sending training values to TabPFN.")
    provider = TabPFNProvider(cfg) if hosted and cfg.available("tabpfn") else None

    def task(progress, cancelled):
        return run_model(ds, ctx, target, split, split_field, predictors, provider, progress, cancelled)

    previous = ws.job_id
    ws.job_id = manager().submit(
        ws.owner, ctx.id, "model:" + digest([target, split, split_field, predictors, hosted]), task
    )
    ws.job_kind, ws.job_context = "model", ctx.id
    if ws.job_id != previous:
        ws.model_count += 1


def start_event_preparation(ws, specification):
    from firstlook.event_tasks import EventTaskSpec, prepare_event_task

    if ws.replay or ws.event_prepare_count >= 2:
        raise ValueError("Two event preparations per context; recorded replay is read-only.")
    spec = EventTaskSpec.model_validate(specification)
    ds, ctx = snapshot(ws), ws.context()

    def task(progress, cancelled):
        return prepare_event_task(ds, ctx, spec, progress, cancelled).model_dump(mode="json")

    ws.job_id = manager().submit(ws.owner, ctx.id, "event-prepare:" + digest(spec.model_dump()), task)
    ws.job_kind, ws.job_context = "event_prepare", ctx.id
    ws.event_prepare_count += 1


def start_event_evaluation(ws, run_id, hosted=False):
    from firstlook.event_tasks import evaluate_event_task, event_preflight

    if ws.replay or ws.event_model_count >= 2:
        raise ValueError("Two event-model evaluations per context; recorded replay is read-only.")
    run = copy.deepcopy(next(r for r in ws.event_runs if r["id"] == run_id))
    if run["source_context"] != ws.context().model_dump(mode="json"):
        raise ValueError("This event task has a different source context.")
    readiness = event_preflight(run)
    if readiness["status"] == "blocked":
        raise ValueError(" ".join(readiness["errors"]))
    cfg, ctx = settings(), ws.context()
    if hosted and (not cfg.available("tabpfn") or not st.session_state.get("external_ok")):
        raise ValueError("Configure hosted TabPFN and allow external analysis first.")

    def task(progress, cancelled):
        return evaluate_event_task(
            run, TabPFNProvider(cfg) if hosted else None, progress, cancelled
        ).model_dump(mode="json")

    ws.job_id = manager().submit(ws.owner, ctx.id, "event-model:" + run_id, task)
    ws.job_kind, ws.job_context = "event_model", ctx.id
    ws.event_model_count += 1


def start_question(ws: Workspace, question: str) -> None:
    if ws.followups >= 5:
        raise ValueError("The five-question follow-up allowance is used for this context.")
    ds, inv, cfg = snapshot(ws), copy.deepcopy(ws.investigation), settings()
    assert inv is not None
    jev = JevProvider(cfg) if cfg.available("jev") and st.session_state.get("external_ok") else None

    def task(progress, cancelled):
        from firstlook.question_workflow import prepare_question

        progress("Preparing a supported interpretation for your review")
        try:
            return prepare_question(ds, inv.context, question, jev)
        except ProviderError as exc:
            review = prepare_question(ds, inv.context, question)
            review["provider_error"] = str(exc)
            return review

    ws.job_id = manager().submit(ws.owner, ws.context().id, "question:" + question, task)
    ws.job_context, ws.job_kind = ws.context().id, "interpretation"
    ws.followups += 1


def start_prepared_question(ws, review, override=None, group_field=None):
    from firstlook.question_workflow import execute_prepared

    ds, inv, ctx = snapshot(ws), copy.deepcopy(ws.investigation), ws.context()
    if inv is None or review.get("context") != ctx.id or review.get("executed"):
        raise ValueError("Prepare a fresh interpretation in this investigation first.")

    def task(progress, cancelled):
        progress("Executing the confirmed interpretation")
        return execute_prepared(ds, inv, review, override, group_field)

    ws.job_id = manager().submit(
        ws.owner, ctx.id, "confirmed-question:" + digest([review, override, group_field]), task
    )
    ws.job_context, ws.job_kind = ctx.id, "confirmed_question"


def _text_permission(ws, provider):
    cfg = settings()
    if (
        ws.replay
        or not cfg.available(provider)
        or not st.session_state.get("external_ok")
        or not st.session_state.get("external_text_" + ws.dataset.record.fingerprint)
    ):
        raise ValueError(
            "Configure the provider and explicitly allow sharing this dataset's selected text first."
        )
    return cfg


def start_text_proposal(ws, field):
    from firstlook.text_features import selected_text_rows, MAX_TEXT_CHARS

    cfg = _text_permission(ws, "terra")
    if ws.text_proposal_count >= 2:
        raise ValueError("This context has used its two feature-proposal requests.")
    ds, ctx = snapshot(ws), ws.context()
    ids = selected_text_rows(ds, ctx, field, 60)
    samples = list(
        dict.fromkeys(
            str(v)
            for v in ds.frame.loc[ids, field].dropna()
            if str(v).strip() and len(str(v)) <= MAX_TEXT_CHARS
        )
    )[:8]
    if not samples:
        raise ValueError("No nonempty bounded text examples are available.")

    def task(progress, cancelled):
        progress("Proposing frozen questions from text only; no target values supplied")
        terra = TerraProvider(cfg)
        result = terra.feature_questions(ds.label(field), samples)
        return {
            "context": ctx.id,
            "field": field,
            "features": [f.model_dump(mode="json") for f in result.features],
            "records": terra.records,
        }

    ws.job_id = manager().submit(ws.owner, ctx.id, "feature-proposal:" + field, task)
    ws.job_kind, ws.job_context = "text_proposal", ctx.id
    ws.text_proposal_count += 1


def start_text_coding(ws, field, definitions, limit):
    from firstlook.text_features import code_text, preview_text_cost

    cfg = _text_permission(ws, "jev")
    if ws.text_run_count >= 2:
        raise ValueError("This context has used its two text-coding experiments.")
    ds, ctx = snapshot(ws), ws.context()
    preview_text_cost(ds, ctx, field, definitions, limit)

    def task(progress, cancelled):
        return code_text(
            ds,
            ctx,
            field,
            definitions,
            limit,
            JevProvider(cfg, max_calls=64, max_questions=1440, max_input_bytes=2_000_000),
            progress,
            cancelled,
        ).model_dump(mode="json")

    ws.job_id = manager().submit(ws.owner, ctx.id, "text-coding:" + digest([field, definitions, limit]), task)
    ws.job_kind, ws.job_context = "text_coding", ctx.id
    ws.text_run_count += 1


def start_feature_model(ws, run_id, target, split, split_field, available, hosted):
    from firstlook.text_features import TextFeatureRun, evaluate_features

    if ws.replay or ws.text_model_count >= 2:
        raise ValueError("This context has used its two feature-model experiments or is recorded replay.")
    cfg, ds, ctx = settings(), snapshot(ws), ws.context()
    if hosted and (not cfg.available("tabpfn") or not st.session_state.get("external_ok")):
        raise ValueError("Configure hosted TabPFN and allow external analysis first.")
    run = TextFeatureRun.model_validate(next(r for r in ws.text_runs if r["id"] == run_id))
    if run.evaluation:
        raise ValueError(
            "This frozen feature run already has its final predictive evaluation. Use a new experiment rather than tuning against its holdout."
        )

    def task(progress, cancelled):
        result = evaluate_features(
            ds,
            ctx,
            run,
            target,
            split,
            split_field,
            available,
            TabPFNProvider(cfg) if hosted else None,
            progress,
            cancelled,
        )
        return {"run_id": run_id, "evaluation": result}

    ws.job_id = manager().submit(
        ws.owner, ctx.id, "feature-model:" + digest([run_id, target, split, split_field, hosted]), task
    )
    ws.job_kind, ws.job_context = "feature_model", ctx.id
    ws.text_model_count += 1


def start_note_review(ws, question_id, notes):
    from firstlook.clarifications import review_notes

    cfg, ds, ctx = settings(), snapshot(ws), ws.context()
    if (
        ws.replay
        or ws.note_review_count >= 2
        or not cfg.available("jev")
        or not st.session_state.get("external_ok")
    ):
        raise ValueError("This review needs Jev, dataset permission and an unused note-review allowance.")

    def task(progress, cancelled):
        return review_notes(ds, ctx, question_id, notes, JevProvider(cfg))

    ws.job_id = manager().submit(ws.owner, ctx.id, "notes:" + digest([question_id, notes]), task)
    ws.job_kind, ws.job_context = "notes", ctx.id
    ws.note_review_count += 1


def start_ranking(ws, goal):
    from firstlook.recommendations import prioritize_typed

    cfg, ds, ctx = settings(), snapshot(ws), ws.context()
    if (
        ws.replay
        or not ws.investigation
        or not cfg.available("jev")
        or not st.session_state.get("external_ok")
    ):
        raise ValueError("Run an investigation, configure Jev and allow external analysis first.")
    if (
        sum(r.purpose == "Relevance of eligible complementary evidence" for r in ws.investigation.judgments)
        >= 4
    ):
        raise ValueError("The relevance-review allowance has been used for this context.")
    inv = copy.deepcopy(ws.investigation)
    inv.goal = goal[:1000]

    def task(progress, cancelled):
        prioritize_typed(inv, JevProvider(cfg), ds)
        return inv

    ws.job_id = manager().submit(ws.owner, ctx.id, "ranking:" + digest(goal), task)
    ws.job_kind, ws.job_context = "analysis", ctx.id


def start_semantic_review(ws: Workspace) -> None:
    ds, cfg, ctx = snapshot(ws), settings(), ws.context()
    if not cfg.available("terra") or not st.session_state.get("external_ok"):
        raise ValueError("Configure Terra and enable external analysis for this dataset first.")
    if ws.semantic_review_count:
        raise ValueError("The optional field-meaning review has already run for this dataset.")
    # Metadata, summaries and recorded levels only. No source rows or invented units.
    packet = {
        "description": ds.record.description,
        "fields": [
            {
                "id": f.id,
                "name": f.name,
                "role": f.role.value,
                "unit": f.unit,
                "physical_type": f.physical_type,
                "profile": ws.profile["fields"][f.id],
            }
            for f in ds.record.fields
        ],
    }
    from firstlook.semantic.planner import semantic_packet

    packet["semantic_contract"] = semantic_packet(ds, 12)

    def task(progress, cancelled):
        terra = TerraProvider(cfg)
        progress("Reviewing field meanings as unconfirmed hypotheses")
        review = terra.semantics(packet)
        from firstlook.semantics import validate_semantic_review
        from firstlook.semantic.model import proposal_candidate

        proposals = []
        for proposal in review.metadata_proposals:
            valid, reason = True, "Eligible hypothesis; explicit user selection is required."
            try:
                proposal_candidate(ds, proposal)
            except ValueError as exc:
                valid, reason = False, str(exc)
            proposals.append(
                {"proposal": proposal.model_dump(mode="json"), "valid": valid, "validation": reason}
            )

        return {
            "context": ctx.id,
            "suggestions": validate_semantic_review(ds, review),
            "dataset_note": review.dataset_note,
            "records": terra.records,
            "metadata_proposals": proposals,
        }

    ws.job_id = manager().submit(ws.owner, ctx.id, "semantic_review", task)
    ws.job_context, ws.job_kind = ctx.id, "semantics"
    ws.semantic_review_count += 1


def start_preparation(ws: Workspace):
    """One session-owned job; explicit request or an enabled per-dataset automatic mode."""
    from firstlook.preparation import build_preparation
    from firstlook.preparation_connected import enrich_preparation, preparation_sources
    from firstlook.preparation_contracts import PREPARATION_POLICY, PreparationDraft

    if ws.replay or not ws.dataset:
        raise ValueError("Open an editable dataset before preparing it.")
    if ws.job_id:
        raise ValueError("Let the current task finish or cancel it before preparing another draft.")
    cfg, ds, ctx = settings(), snapshot(ws), ws.context()
    if not st.session_state.get("external_ok") or not (cfg.available("terra") or cfg.available("jev")):
        raise ValueError(
            "Allow connected preparation for this dataset first. The local draft remains available."
        )
    sources = preparation_sources(
        ws.preparation_inputs.get("notes", ""), ws.preparation_inputs.get("dictionary", "")
    )
    goal = str(ws.preparation_inputs.get("goal", ""))[:1000]
    draft = (
        PreparationDraft.model_validate(ws.preparation)
        if ws.preparation
        else build_preparation(ds, goal, sources)
    )
    if draft.goal != goal or draft.sources != sources or draft.base_semantics != ds.context().semantics:
        draft = build_preparation(ds, goal, sources)
    reusable = [c.payload for c in draft.changes if c.origin == "template"]
    request = digest(
        [
            ds.record.fingerprint,
            ds.record.parser,
            ds.context().semantics,
            goal,
            sources,
            cfg.openai_model,
            cfg.typesafe_model,
            PREPARATION_POLICY,
            reusable,
        ]
    )
    if request in ws.preparation_cache:
        ws.preparation = copy.deepcopy(ws.preparation_cache[request])
        ws.message = "Restored this exact preparation request from your session. No provider call was made."
        return
    if request in ws.preparation_requests:
        raise ValueError(
            "This exact request has already been attempted; it will not run again on a rerun. Change the supplied context to request another draft."
        )
    if len(ws.preparation_requests) >= 3:
        raise ValueError(
            "This upload has used its three connected preparation requests. Local review and edits remain available."
        )
    draft.request = request

    def task(progress, cancelled):
        return enrich_preparation(
            ds,
            draft,
            TerraProvider(cfg) if cfg.available("terra") else None,
            JevProvider(cfg) if cfg.available("jev") else None,
            progress,
            cancelled,
            visual=cfg.terra_visual_review,
        ).model_dump(mode="json")

    ws.job_id = manager().submit(ws.owner, ctx.id, "preparation:" + request, task)
    ws.job_context, ws.job_kind = ctx.id, "preparation"
    ws.preparation_requests.add(request)


def accept_preparation(ws, result):
    """Receiving a draft grants no permission; per-subject checks preserve concurrent edits."""
    from firstlook.preparation import assert_scope
    from firstlook.preparation_contracts import PreparationDraft

    draft = PreparationDraft.model_validate(result)
    assert_scope(ws.dataset, draft)
    ws.preparation = draft.model_dump(mode="json")
    ws.preparation_cache[draft.request] = copy.deepcopy(ws.preparation)
    ws.preparation_history = (
        ws.preparation_history
        + [
            {
                "request": draft.request,
                "policy": draft.policy,
                "dataset": draft.dataset,
                "parsing_scope": draft.parsing_scope,
                "base_semantics": draft.base_semantics,
                "goal": draft.goal,
                "sources": draft.sources,
                "records": draft.records,
                "errors": draft.errors,
                "telemetry": draft.telemetry,
            }
        ]
    )[-3:]


def apply_prepared_bundle(ws, ids):
    from firstlook.preparation import apply_preparation
    from firstlook.preparation_contracts import PreparationDraft

    if ws.replay:
        raise ValueError("Recorded preparation is read-only.")
    draft = PreparationDraft.model_validate(ws.preparation)
    before = ws.dataset.record.model_dump(mode="json")
    applied = apply_preparation(ws.dataset, draft, ids)
    ws.preparation_undo = {"before": before, "after": ws.dataset.context().semantics}
    ws.preparation = draft.model_dump(mode="json")
    ws.invalidate()
    if any(c.kind == "task" and c.id in applied for c in draft.changes):
        for key in ["model_target", "model_split", "model_split_field"]:
            st.session_state.pop(key, None)
    ws.message = (
        f"Applied {len(applied)} related definitions in one transaction. The new contract is ready to use."
    )
    return applied


def undo_preparation(ws):
    from firstlook.contracts import DatasetRecord
    from firstlook.semantic.model import commit_model, get_model

    if ws.replay or not ws.preparation_undo or ws.dataset.context().semantics != ws.preparation_undo["after"]:
        raise ValueError(
            "The contract changed after this bundle. Use Meaning to review it; automatic undo is no longer applicable."
        )
    record = DatasetRecord.model_validate(ws.preparation_undo["before"])
    clone = Dataset(record, ws.dataset.frame, ws.dataset.raw)
    commit_model(clone, get_model(clone), "table", "undo_preparation", ws.preparation_undo["after"])
    ws.dataset.record = clone.record
    ws.preparation_undo = {}
    from firstlook.preparation import build_preparation
    from firstlook.preparation_connected import preparation_sources

    sources = preparation_sources(
        ws.preparation_inputs.get("notes", ""), ws.preparation_inputs.get("dictionary", "")
    )
    ws.preparation = build_preparation(ws.dataset, ws.preparation_inputs.get("goal", ""), sources).model_dump(
        mode="json"
    )
    ws.invalidate()
    ws.message = "Restored the definitions from before that bundle and recorded the undo."


def start_recipe(ws: Workspace, recipe: str, fields: list[str], params: dict):
    from firstlook.exploration import RECIPES, perspective_coverage

    ds, ctx = snapshot(ws), ws.context()
    inv = copy.deepcopy(ws.investigation) if ws.investigation else Investigation(ctx)
    plan = plan_for(ctx, "exploration", fields, RECIPES[recipe], {"recipe": recipe, **params})

    def work(progress, cancelled):
        progress(RECIPES[recipe])
        result, finding = analyze(ds, ctx, plan)
        companion_operation = (
            "relationship"
            if recipe in {"density", "influence"}
            else "group_distribution"
            if recipe == "group_shape"
            else "distribution"
            if recipe == "histogram_sensitivity"
            else None
        )
        if companion_operation:
            try:
                cr, cf = analyze(
                    ds,
                    ctx,
                    plan_for(
                        ctx,
                        companion_operation,
                        fields,
                        "Recorded context for " + RECIPES[recipe],
                        {"normalization": params.get("normalization", "count")}
                        if recipe == "histogram_sensitivity"
                        else None,
                    ),
                )
                inv.add_view(cr, cf)
                inv.related_views[result.id] = {"companion": cr.id, "intent": "Complementary perspective"}
            except ValueError:
                pass
        if recipe == "temporal" and params.get("mode") == "calendar":
            from firstlook.semantic.planner import metric_plan

            cr, cf = analyze(
                ds,
                ctx,
                metric_plan(
                    ds,
                    ctx,
                    params["metric"],
                    time_field=params["time_field"],
                    period=params.get("period", "MS"),
                    question="Recorded chronological context",
                ),
            )
            inv.add_view(cr, cf)
            inv.related_views[result.id] = {
                "companion": cr.id,
                "intent": "Calendar phase beside its recorded chronology",
            }
        inv.add_view(result, finding)
        inv.coverage = perspective_coverage(ds, inv)
        return inv

    ws.job_id = manager().submit(ws.owner, ctx.id, "recipe:" + plan.id, work)
    ws.job_kind, ws.job_context = "recipe", ctx.id


def start_view(ws: Workspace, operation: str, fields: list[str], params: dict, question: str):
    from firstlook.exploration import perspective_coverage

    ds, ctx = snapshot(ws), ws.context()
    inv = copy.deepcopy(ws.investigation) if ws.investigation else Investigation(ctx)
    p = plan_for(ctx, operation, fields, question, params)

    def work(progress, cancelled):
        progress(question)
        result, finding = analyze(ds, ctx, p)
        if operation == "quantile_bin_summary":
            cr, cf = analyze(
                ds,
                ctx,
                plan_for(ctx, "relationship", fields, "Recorded pairs behind conditional center and spread"),
            )
            inv.add_view(cr, cf)
        inv.add_view(result, finding)
        if operation == "quantile_bin_summary":
            inv.related_views[result.id] = {
                "companion": cr.id,
                "intent": "Conditional center and spread beside recorded pairs",
            }
        inv.coverage = perspective_coverage(ds, inv)
        return inv

    ws.job_id = manager().submit(ws.owner, ctx.id, "view:" + p.id, work)
    ws.job_kind, ws.job_context = "recipe", ctx.id


def start_comparison(ws: Workspace, **kwargs):
    from firstlook.comparison import build_comparison

    if ws.selection is None:
        raise ValueError("Preview a cohort first.")
    ds, ctx = snapshot(ws), ws.context()
    selection = ws.selection.model_copy(deep=True)
    model = ws.model.model_copy(deep=True) if ws.model else None

    def work(progress, cancelled):
        progress("Computing selected and reference populations with shared definitions")
        return build_comparison(ds, selection, model=model, **kwargs)

    ws.job_id = manager().submit(ws.owner, ctx.id, "comparison:" + digest([selection.id, kwargs]), work)
    ws.job_kind, ws.job_context, ws.job_revision = "comparison", ctx.id, selection.revision


def start_comparison_review(ws: Workspace):
    from firstlook.investigation import review_comparison

    cfg = settings()
    if (
        ws.comparison is None
        or ws.comparison_review_count
        or not cfg.available("terra")
        or not st.session_state.get("external_ok", False)
    ):
        raise ValueError(
            "Comparison review needs Terra, dataset permission and an unused review allowance in this investigation."
        )
    ds, ctx = snapshot(ws), ws.context()
    bundle = ws.comparison.model_copy(deep=True)

    def work(progress, cancelled):
        try:
            return review_comparison(
                ds,
                bundle,
                TerraProvider(cfg),
                JevProvider(cfg) if cfg.available("jev") else None,
                cfg.terra_visual_review,
                progress,
                cancelled,
            )
        except ProviderError as exc:
            bundle.interpretation = {"status": "unavailable", "note": str(exc)}
            return bundle

    ws.job_id = manager().submit(ws.owner, ctx.id, "comparison-review:" + bundle.id, work)
    ws.job_kind, ws.job_context, ws.job_revision = "comparison", ctx.id, bundle.spec.selection.revision
    ws.comparison_review_count += 1


@st.fragment(run_every=timedelta(seconds=1))
def poll_job():
    ws = workspace()
    if not ws.job_id:
        return
    job = manager().get(ws.owner, ws.job_id)
    if job is None:
        ws.job_id = None
        st.warning("This worker expired or restarted. Run the investigation again.")
        return
    if job.state in {"queued", "running"}:
        with st.container(border=True):
            st.caption("INVESTIGATION IN PROGRESS")
            st.markdown(f"**{job.stage}**")
            st.caption("The workspace stays available. A context change will discard stale results.")
            if st.button("Cancel task", key="cancel_job", icon=":material/close:"):
                manager().cancel(ws.owner, ws.job_id)
        return
    same_revision = ws.job_kind != "comparison" or (
        ws.selection is not None and ws.selection.revision == ws.job_revision
    )
    if (
        job.state == "completed"
        and ws.dataset
        and (job.context == ws.context().id or ws.job_kind == "preparation")
        and same_revision
    ):
        if ws.job_kind == "preparation":
            try:
                accept_preparation(ws, job.result)
            except ValueError:
                ws.message = (
                    "An earlier preparation used different source bytes or parsing and was discarded."
                )
        elif ws.job_kind == "comparison":
            ws.comparison = job.result
        elif ws.job_kind == "interpretation":
            ws.question_review = job.result
        elif ws.job_kind == "text_proposal":
            ws.text_proposal = job.result
        elif ws.job_kind == "text_coding":
            ws.text_runs = (ws.text_runs + [job.result])[-2:]
            ws.investigation = ws.investigation or Investigation(ws.context())
        elif ws.job_kind == "event_prepare":
            ws.event_runs = (ws.event_runs + [job.result])[-2:]
            ws.investigation = ws.investigation or Investigation(ws.context())
        elif ws.job_kind == "event_model":
            ws.event_runs = [job.result if r["id"] == job.result["id"] else r for r in ws.event_runs]
        elif ws.job_kind == "feature_model":
            for run in ws.text_runs:
                if run["id"] == job.result["run_id"]:
                    run["evaluation"] = job.result["evaluation"]
        elif ws.job_kind == "notes":
            ws.note_review = job.result
        elif ws.job_kind == "semantics":
            ws.semantic_review = job.result
        elif ws.job_kind == "model":
            ws.model = job.result
            if ws.investigation:
                ws.investigation.model_runs.append(job.result)
                diagnostic_findings(ws.dataset, ws.investigation, job.result)
        else:
            ws.investigation = job.result
            if ws.job_kind == "confirmed_question":
                ws.question_review["executed"] = True
            if ws.job_kind == "recipe" and ws.investigation.findings:
                ws.opened.add(ws.investigation.findings[0].id)
                ws.explore_id = ws.investigation.findings[0].id
            if ws.investigation.model_runs:
                ws.model = ws.investigation.model_runs[-1]
                if ws.job_kind == "connected":
                    ws.model_count += 1
        ws.bound_views()
        if ws.job_kind == "preparation":
            ws.message = (
                ws.message
                or "Your preparation draft is ready to review. Existing declarations have not been changed."
            )
        else:
            ws.message = "The investigation is ready."
    elif job.state == "failed":
        ws.message = job.error
    elif job.state == "completed":
        ws.message = "An earlier context finished; its result was not applied to the current data."
    else:
        ws.message = "Task cancelled. Remote work may already have consumed provider quota."
    manager().forget(ws.owner, ws.job_id)
    ws.job_id = None
    st.rerun()
