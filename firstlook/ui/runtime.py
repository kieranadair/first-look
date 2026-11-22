"""UI orchestration keeps expensive work and provider calls out of reruns."""

import copy
from datetime import timedelta

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from firstlook.challenges import automatic_challenges
from firstlook.config import settings_from
from firstlook.contracts import digest
from firstlook.discovery import discover
from firstlook.ingest import Dataset
from firstlook.investigation import prioritize, run_terra
from firstlook.jobs import JobManager
from firstlook.modeling import diagnostic_findings, run_model, suggested_model_plan
from firstlook.providers.base import ProviderError
from firstlook.providers.language import TerraProvider
from firstlook.providers.tabpfn import TabPFNProvider
from firstlook.providers.typesafe import JevProvider
from firstlook.questions import run_question
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
    if connected and not st.session_state.get("external_ok", False):
        raise ValueError("Enable external analysis for this dataset before connecting providers.")
    model_plan = suggested_model_plan(ds, ctx) if connected and ws.model_count < 2 else None

    def work(progress, cancelled):
        progress("Computing eligible analytical views")
        inv = discover(ds, ctx)
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
                progress("Jev is choosing among valid views")
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


def start_question(ws: Workspace, question: str) -> None:
    if ws.followups >= 5:
        raise ValueError("The five-question follow-up allowance is used for this context.")
    ds, inv, cfg = snapshot(ws), copy.deepcopy(ws.investigation), settings()
    assert inv is not None
    terra = TerraProvider(cfg) if cfg.available("terra") and st.session_state.get("external_ok") else None

    def task(progress, cancelled):
        return run_question(ds, inv, question, terra)

    ws.job_id = manager().submit(ws.owner, ws.context().id, "question:" + question, task)
    ws.job_context, ws.job_kind = ws.context().id, "analysis"
    ws.followups += 1


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
    if job.state == "completed" and ws.dataset and job.context == ws.context().id:
        if ws.job_kind == "semantics":
            ws.semantic_review = job.result
        elif ws.job_kind == "model":
            ws.model = job.result
            if ws.investigation:
                ws.investigation.model_runs.append(job.result)
                diagnostic_findings(ws.dataset, ws.investigation, job.result)
        else:
            ws.investigation = job.result
            if ws.investigation.model_runs:
                ws.model = ws.investigation.model_runs[-1]
                if ws.job_kind == "connected":
                    ws.model_count += 1
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
