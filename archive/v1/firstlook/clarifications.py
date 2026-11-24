"""Consequences and isolated assumptions, never automatic semantic confirmation."""

from __future__ import annotations

from firstlook.contracts import digest
from firstlook.ingest import Dataset
from firstlook.judgment_catalog import note_specs
from firstlook.recommendations import descriptive_key, rank_candidates
from firstlook.semantic.model import get_model, commit_model
from firstlook.semantic.policy import decision


def clarification_queue(dataset, context, goal="", jev=None):
    model = get_model(dataset)
    candidates = []
    for q in model.clarifications[:16]:
        affected = []
        for mid in q.affected_metrics:
            m = model.metric(mid)
            outcome = decision(dataset, m, [], rows=context.row_ids)
            affected.append(
                {
                    "id": mid,
                    "metric": m.label,
                    "status": outcome.status,
                    "requirements": outcome.requirements,
                    "reasons": outcome.reasons,
                }
            )
        candidates.append(
            {
                "id": q.id,
                "alias": descriptive_key(q.question, q.id),
                "question": q.question,
                "definition": q.reason,
                "family": q.property,
                "support": len(context.row_ids),
                "cost": 0,
                "affected": affected,
                "unlock_count": sum(a["status"] != "allowed" for a in affected),
                "subject": q.subject,
            }
        )
    ranked, batch = rank_candidates(
        candidates,
        goal or "Resolve declarations that affect the current analytical question.",
        context.id,
        jev,
    )
    # Dependency counts are observable; they do not estimate information gain.
    for row in ranked:
        row["score"] += min(row["unlock_count"], 8) * 0.03
    return sorted(ranked, key=lambda r: (-r["score"], -r["unlock_count"], r["id"])), batch


def review_notes(dataset, context, question_id, notes, jev):
    if not notes.strip() or len(notes) > 4000:
        raise ValueError("Supply collection notes of at most 4,000 characters.")
    q = next((q for q in get_model(dataset).clarifications if q.id == question_id), None)
    if q is None:
        raise ValueError("Choose an unresolved decision in this contract.")
    sentences = [s.strip() for s in notes.splitlines() if s.strip()][:12]
    state = {"decision": q.question, "notes": {"note_" + str(i + 1): s for i, s in enumerate(sentences)}}
    specs = note_specs(state["notes"])
    record = jev.judge(state, specs, context=context.id, purpose="Unconfirmed note evidence")
    passage = record.answers["passage"]
    supported = record.answers["explicit"].status == "yes" and passage.status == "selected"
    return {
        "question": q.id,
        "status": "unconfirmed source evidence" if supported else "unresolved",
        "passage": state["notes"][str(passage.value)] if supported else "",
        "record": record.model_dump(mode="json"),
        "boundary": "This selects supplied wording; a human must confirm its applicability and business meaning.",
    }


def hypothetical_quantity(dataset, context, metric_id, kind, groups=None):
    """Compute a named alternative on a copy with its own semantic context."""
    from firstlook.discovery import analyze
    from firstlook.semantic.planner import metric_plan

    if context.id != dataset.context(context.row_ids, context.focus, context.assumption).id:
        raise ValueError("The hypothetical scenario has a stale context.")
    clone = Dataset(dataset.record.model_copy(deep=True), dataset.frame, dataset.raw)
    model = get_model(clone).model_copy(deep=True)
    metric = model.metric(metric_id)
    if not metric.field or kind not in {"flow", "amount", "state", "rate", "ratio", "cumulative"}:
        raise ValueError("Choose an existing value metric and a supported explicit quantity assumption.")
    meaning = model.meaning(metric.field)
    meaning.kind, meaning.confirmed, metric.confirmed = kind, True, True
    commit_model(clone, model)
    child = clone.context(context.row_ids, context.focus, context.assumption)
    permission = decision(clone, get_model(clone).metric(metric_id), groups or [], rows=child.row_ids)
    out = {
        "id": digest([context.id, metric_id, kind, groups]),
        "parent_context": context.id,
        "context": child.model_dump(mode="json"),
        "assumption": f"For this isolated scenario only: {dataset.label(metric.field)} is {kind}, and the existing metric definition is confirmed. Entity grain, allocation and gap policies are not invented.",
        "eligibility": permission.model_dump(mode="json"),
        "result": None,
        "chart": None,
    }
    if permission.status == "allowed":
        result, finding = analyze(
            clone,
            child,
            metric_plan(clone, child, metric_id, groups or [], question="Hypothetical quantity: " + kind),
        )
        out.update(result=result.model_dump(mode="json"), chart=finding.chart.model_dump(mode="json"))
    return out
