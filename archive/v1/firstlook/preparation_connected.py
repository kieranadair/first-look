"""One coherent interpretation, atomic evidence judgments, deterministic reconciliation."""

from __future__ import annotations

import json
import io
import re

from firstlook.contracts import Role, clean
from firstlook.judgment_catalog import preparation_specs
from firstlook.judgments import relevance_spec
from firstlook.preparation import change_id, link_dependencies, make_change
from firstlook.preparation_contracts import PreparationDraft, PreparationInterpretation
from firstlook.providers.base import ProviderError
from firstlook.semantic.model import get_model


def preparation_sources(notes="", dictionary=""):
    sources = {
        k: str(v).strip() for k, v in {"notes": notes, "dictionary": dictionary}.items() if str(v).strip()
    }
    if any(len(v) > 12000 for v in sources.values()) or sum(map(len, sources.values())) > 16000:
        raise ValueError("Use at most 12,000 characters per source and 16,000 in total.")
    return sources


def embedded_dictionary(dataset):
    """Read supplied Parquet descriptions/units; never treat arbitrary metadata as instructions."""
    if not dataset.raw or not dataset.raw.startswith(b"PAR1"):
        return ""
    import pyarrow.parquet as pq

    schema = pq.ParquetFile(io.BytesIO(dataset.raw)).schema_arrow
    entries = []
    allowed = {b"description", b"comment", b"unit", b"units", b"currency", b"title"}

    def extract(metadata, subject):
        for key, raw in (metadata or {}).items():
            if key.lower() in allowed and len(raw) <= 1200:
                try:
                    value = raw.decode("utf-8")
                    entries.append(subject + " · " + key.decode("ascii") + ": " + value)
                except (UnicodeDecodeError, UnicodeEncodeError):
                    continue

    extract(schema.metadata, "Table")
    for field in schema:
        extract(field.metadata, field.name)
    result = "\n".join(entries)
    return result if len(result) <= 12000 else ""


def preparation_packet(dataset, draft):
    model, frame = get_model(dataset), dataset.frame
    fields = []
    for f in dataset.record.fields:
        s = frame[f.id]
        item = {
            "id": f.id,
            "name": f.name,
            "role": f.role.value,
            "physical_type": f.physical_type,
            "unit": f.unit,
            "nonmissing": int(s.notna().sum()),
            "distinct": int(s.nunique()),
            "meaning": model.meaning(f.id).model_dump(mode="json"),
        }
        if f.role == Role.MEASURE:
            item["domain"] = clean(
                {"min": s.min(), "max": s.max(), "negative": int((s < 0).sum()), "zero": int((s == 0).sum())}
            )
        elif f.role != Role.TEXT:
            item["examples"] = [str(v)[:100] for v in s.dropna().unique()[:3]]
        fields.append(item)
    candidates = []
    for c in draft.changes:
        if c.kind in {"entity", "metric", "relationship"}:
            candidates.append(
                {
                    "id": c.id,
                    "kind": c.kind,
                    "label": c.label,
                    "definition": {
                        k: v
                        for k, v in c.payload.items()
                        if k not in {"confirmed", "description", "examples", "scope"}
                    },
                }
            )
    packet = clean(
        {
            "policy": draft.policy,
            "source_fingerprint": draft.dataset,
            "goal": draft.goal,
            "recorded_rows": len(frame),
            "current_grain": {
                "description": model.grain,
                "entity": model.grain_entity,
                "confirmed": model.grain_confirmed,
            },
            "fields": fields,
            "candidates": candidates[:64],
            "recorded_relationships": [
                {
                    "child": r.child,
                    "parent": r.parent,
                    "within": r.within,
                    "strict": r.strict,
                    "complete": r.complete,
                    "exceptions": r.violating_levels,
                }
                for r in model.relationships[:12]
            ],
            "time_policies": [p.model_dump(mode="json") for p in model.time_policies[:4]],
            "witnesses": draft.evidence[:8],
            "sources": draft.sources,
            "analytical_task": model.search.get("analytical_task"),
            "reused_definitions_for_review": [
                {"kind": c.kind, "definition": c.payload} for c in draft.changes if c.origin == "template"
            ][:20],
            "omissions": {
                "candidate_changes": max(0, len(candidates) - 64),
                "text_values": "Free-text values are omitted; supplied notes/dictionary are included explicitly.",
            },
        }
    )
    # Preserve source passages verbatim. Reduce optional evidence, not hidden pieces of a definition.
    while len(json.dumps(packet, ensure_ascii=True)) > 42000 and packet["witnesses"]:
        packet["witnesses"].pop()
    while len(json.dumps(packet, ensure_ascii=True)) > 42000 and len(packet["candidates"]) > 8:
        packet["candidates"].pop()
        packet["omissions"]["candidate_changes"] += 1
    packet["omissions"]["witnesses"] = max(0, len(draft.evidence) - len(packet["witnesses"]))
    if len(json.dumps(packet, ensure_ascii=True)) > 42000:
        raise ValueError(
            "Preparation exceeds its bounded evidence packet. Shorten the supplied notes/dictionary."
        )
    return packet


def reconcile_interpretation(dataset, original, response):
    draft = original.model_copy(deep=True)
    response = PreparationInterpretation.model_validate(response)
    draft.summary = response.summary
    catalog = {c.id: c for c in draft.changes}
    quantities = {q.meaning.field for q in response.quantities}
    duplicates = []

    def literal_support(value, quote):
        left = r"(?<!\w)" if value[0].isalnum() else ""
        right = r"(?!\w)" if value[-1].isalnum() else ""
        return bool(re.search(left + re.escape(value) + right, quote, re.I))

    def put(change, explanation):
        if change.id in duplicates:
            draft.errors.append("Terra repeated a conflicting declaration: " + change.label)
            return
        duplicates.append(change.id)
        change.evidence = explanation.evidence
        if any(
            q.source not in draft.sources or q.quote not in draft.sources[q.source] for q in change.evidence
        ):
            change.issue = (
                "A cited passage is absent from the supplied source. This proposal cannot be applied."
            )
        if change.kind == "quantity":
            meaning = get_model(dataset).meaning(change.subject)
            for key in ["unit", "currency", "basis"]:
                value = str(change.payload.get(key, ""))
                if (
                    value
                    and value != getattr(meaning, key)
                    and not any(literal_support(value, q.quote) for q in change.evidence)
                ):
                    change.issue = "A new unit, currency or measurement basis needs a verbatim supporting source. Enter it directly in Meaning if known."
        if change.kind in {"time", "availability"} and not change.evidence:
            change.issue = "Observation schedules, coverage and historical availability require supplied recording-process evidence or direct entry in Meaning."
        if (
            change.kind == "task"
            and (change.payload.get("complete_through") or change.payload.get("horizon_days"))
            and not change.evidence
        ):
            change.issue = "A complete outcome window requires supplied recording-process evidence."
        if isinstance(change.before, dict) and change.before.get("confirmed") and change.origin == "terra":
            change.suggested = False
            change.review = "This changes a confirmed declaration. Select it deliberately after reviewing the supplied correction."
        catalog[change.id] = change

    for proposal in response.quantities:
        try:
            fid = proposal.meaning.field
            if (
                fid not in dataset.frame
                or dataset.field(fid).role != Role.MEASURE
                and not any(r.field == fid and r.role == Role.MEASURE for r in response.roles)
            ):
                raise ValueError("Quantity proposal does not refer to a recorded measure.")
            # Model guesses cannot smuggle availability or transform permissions into a kind change.
            proposal.meaning.available_at_prediction = get_model(dataset).meaning(fid).available_at_prediction
            proposal.meaning.composition = get_model(dataset).meaning(fid).composition
            proposal.meaning.allowed_transforms = []
            put(
                make_change(
                    dataset,
                    "quantity",
                    fid,
                    proposal.meaning.model_dump(mode="json"),
                    dataset.label(fid) + " · " + proposal.meaning.kind,
                    proposal.reason,
                    "terra",
                    True,
                ),
                proposal,
            )
        except (ValueError, StopIteration) as exc:
            draft.errors.append(str(exc))
    for proposal in response.roles:
        try:
            f = dataset.field(proposal.field)
            put(
                make_change(
                    dataset,
                    "role",
                    f.id,
                    {"role": proposal.role.value, "order": proposal.order, "excluded": f.excluded},
                    f.name + " · " + proposal.role.value,
                    proposal.reason,
                    "terra",
                    True,
                ),
                proposal,
            )
        except StopIteration:
            draft.errors.append("Terra proposed an unknown role field.")
    for proposal in response.selections:
        selected = catalog.get(proposal.candidate)
        if selected is None or selected.kind not in {"entity", "metric", "relationship"}:
            draft.errors.append("Terra selected an unknown candidate; it was not added.")
            continue
        c = selected.model_copy(deep=True)
        c.origin, c.suggested, c.reason = "terra", True, proposal.reason
        put(c, proposal)
    if response.grain:
        p = response.grain
        entity_ids = {e.id for e in get_model(dataset).entities} | {
            c.subject for c in catalog.values() if c.kind == "entity"
        }
        if p.entity is None or p.entity in entity_ids:
            put(
                make_change(
                    dataset,
                    "grain",
                    "table",
                    {"description": p.description, "entity": p.entity},
                    "One row · " + p.description[:220],
                    p.reason,
                    "terra",
                    True,
                ),
                p,
            )
        else:
            draft.errors.append("Terra proposed an unknown row identity.")
    for p in response.times:
        if (p.policy.id, p.policy.field) in {(t.id, t.field) for t in get_model(dataset).time_policies}:
            put(
                make_change(
                    dataset,
                    "time",
                    p.policy.id,
                    p.policy.model_dump(mode="json"),
                    "Recording process · "
                    + dataset.label(p.policy.field)
                    + " · "
                    + p.policy.gap_policy
                    + " · "
                    + p.policy.expected_frequency,
                    p.reason,
                    "terra",
                ),
                p,
            )
        else:
            draft.errors.append("Terra proposed an unknown observation policy.")
    if response.task:
        p = response.task
        if p.task.dataset == dataset.record.fingerprint:
            put(
                make_change(
                    dataset,
                    "task",
                    "table",
                    p.task.model_dump(mode="json"),
                    "Task · " + p.task.question[:220],
                    p.reason,
                    "terra",
                    True,
                ),
                p,
            )
        else:
            draft.errors.append("Terra proposed a task for a different dataset.")
    for p in response.availability:
        if p.rule.field in dataset.frame:
            put(
                make_change(
                    dataset,
                    "availability",
                    p.rule.field,
                    p.rule.model_dump(mode="json"),
                    "Availability · " + dataset.label(p.rule.field) + " · " + p.rule.status,
                    p.reason,
                    "terra",
                ),
                p,
            )
        else:
            draft.errors.append("Terra proposed availability for an unknown field.")
    # A changed quantity must not inherit a contradictory name-based total recommendation.
    for c in catalog.values():
        if c.kind == "metric" and c.payload.get("field") in quantities:
            q = catalog.get(change_id("quantity", c.payload["field"]))
            if (
                q
                and q.payload["kind"] not in {"flow", "amount", "count"}
                and c.payload.get("aggregation") in {"sum", "average_per_entity"}
            ):
                c.suggested = False
                c.issue = "The proposed quantity is not additive. Choose a compatible definition."
    draft.changes = list(catalog.values())[:140]
    draft.errors = draft.errors[:8]
    return link_dependencies(dataset, draft)


def preparation_visuals(dataset, draft):
    """Two finite local diagnostic views, with matched renderer tables and explicit scope."""
    from firstlook.discovery import analyze, plan_for
    from firstlook.visualization.review_assets import render_asset

    measures = [f.id for f in dataset.record.fields if f.role == Role.MEASURE and not f.excluded]
    goal = draft.goal.casefold()
    measures.sort(key=lambda fid: dataset.label(fid).casefold() not in goal)
    if not measures:
        return [], []
    tasks = [("distribution", measures[:1])]
    if len(measures) > 1:
        tasks.append(("relationship", measures[:2]))
    views, images = [], []
    context = dataset.context()
    for operation, fields in tasks:
        try:
            result, finding = analyze(
                dataset,
                context,
                plan_for(context, operation, fields, "Recorded diagnostic context for proposed meanings"),
            )
            asset = render_asset(result, finding.chart, max_points=80)
            views.append(
                clean(
                    {
                        "plan": result.plan.model_dump(mode="json"),
                        "chart": finding.chart.model_dump(mode="json"),
                        "asset": asset.manifest,
                        "matched_records": asset.records,
                        "scope": "Full-upload statistics; diagnostic display/review reductions are specified by the asset manifest. Shapes support hypotheses, not business confirmations.",
                    }
                )
            )
            images.append(asset.png)
        except ValueError:
            continue
    return views, images


def enrich_preparation(
    dataset, draft, terra=None, jev=None, progress=lambda _: None, cancelled=lambda: False, visual=False
):
    draft = PreparationDraft.model_validate(draft).model_copy(deep=True)
    if terra is not None and not cancelled():
        progress("Connecting structure, supplied notes and analytical definitions")
        try:
            packet = preparation_packet(dataset, draft)
            if visual:
                views, images = preparation_visuals(dataset, draft)
                packet["diagnostic_views"] = views
                if len(json.dumps(packet)) > 42000:
                    packet.pop("diagnostic_views")
                    images = []
                response = terra.preparation(packet, images)
            else:
                response = terra.preparation(packet)
            draft = reconcile_interpretation(dataset, draft, response)
            draft.records.extend(clean(terra.records[-1:]))
        except (ProviderError, ValueError) as exc:
            draft.errors.append(str(exc))
    if jev is not None and not cancelled():
        candidates = [c for c in draft.changes if c.evidence and not c.issue][:8]
        questions = draft.decisions[:8] if draft.goal else []
        if candidates or questions:
            progress("Checking narrow source-support and scope questions with Jev")
            state = {
                "goal": draft.goal,
                "clarifications": {"question_" + str(i): q for i, q in enumerate(questions)},
                "definitions": {
                    "proposal_" + str(i): {
                        "definition": c.label,
                        "proposed_values": c.payload,
                        "supplied_passages": [e.model_dump(mode="json") for e in c.evidence],
                    }
                    for i, c in enumerate(candidates)
                },
            }
            specs = [s for i in range(len(candidates)) for s in preparation_specs("proposal_" + str(i))]
            specs += [
                relevance_spec("question_" + str(i), "clarifications.question_" + str(i))
                for i in range(len(questions))
            ]
            try:
                batch = jev.judge(
                    state,
                    specs,
                    context=draft.base_semantics,
                    purpose="Prepared definitions versus supplied documentation",
                )
                draft.records.append(clean(batch.model_dump(mode="json")))
                for i, c in enumerate(candidates):
                    support = batch.answers["proposal_" + str(i) + "_support"].status
                    scope = batch.answers["proposal_" + str(i) + "_scope"].status
                    c.review = (
                        "Jev source support: "
                        + support
                        + "; applicability to the stated field/process: "
                        + scope
                        + ". Human bundle review is still required."
                    )
                    if support != "yes" or scope != "yes":
                        c.suggested = False
                for i, q in enumerate(questions):
                    answer = batch.answers["question_" + str(i)]
                    priority = q.get("priority", 0)
                    if (
                        answer.status == "scored"
                        and isinstance(answer.value, (int, float))
                        and isinstance(priority, (int, float))
                    ):
                        q["priority"] = float(priority) + float(answer.value)
                        q["jev_relevance"] = answer.value
                draft.decisions = sorted(draft.decisions, key=lambda q: -float(str(q["priority"])))
            except (ProviderError, ValueError) as exc:
                draft.errors.append(str(exc))
    draft.errors = draft.errors[:8]
    draft.telemetry["provider_calls"] = int(getattr(terra, "calls", 0)) + int(getattr(jev, "calls", 0))
    draft.telemetry["provider_responses_recorded"] = len(draft.records)
    return draft
