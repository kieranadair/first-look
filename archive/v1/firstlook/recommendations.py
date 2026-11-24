"""Transparent rankings over Python-eligible evidence; no delegated policy."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from firstlook.contracts import digest
from firstlook.judgments import relevance_spec


def descriptive_key(label: str, identity: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", label).strip("_").lower()[:65] or "candidate"
    return stem + "_" + digest(identity)[:6]


def rank_candidates(candidates: list[dict], goal: str, context: str, jev=None):
    """Only semantic relevance needs a model. Other components are computed."""
    candidates = list({c["id"]: c for c in candidates}.values())[:16]
    if not candidates:
        return [], None
    state = {
        "goal": goal,
        "candidates": {
            c["alias"]: {k: c[k] for k in ["question", "definition"] if k in c} for c in candidates
        },
    }
    batch = None
    if jev is not None:
        specs = [
            relevance_spec("relevance_" + digest(c["id"]), "candidates." + c["alias"]) for c in candidates
        ]
        batch = jev.judge(
            state, specs, context=context, purpose="Relevance of eligible complementary evidence"
        )
    family_counts = Counter(c.get("family", "") for c in candidates)
    ranked: list[dict[str, Any]] = []
    for position, candidate in enumerate(candidates):
        answer = batch.answers["relevance_" + digest(candidate["id"])] if batch else None
        relevance = float(answer.value) if answer and answer.status == "scored" else None
        novelty = 1 / family_counts[candidate.get("family", "")]
        support = min(1.0, max(0, candidate.get("support", 0)) / 100)
        cost = float(candidate.get("cost", 0))
        score = (
            (0.55 * relevance + 0.25 * novelty + 0.15 * support - 0.05 * cost)
            if relevance is not None
            else -1 - position / 100
        )
        ranked.append(
            {
                **candidate,
                "relevance": relevance,
                "novelty": novelty,
                "support_component": support,
                "cost_component": cost,
                "score": score,
                "method": "Jev relevance + Python policy"
                if relevance is not None
                else "Recorded deterministic order",
                "reason": "Weights: relevance .55, complementary family .25, support .15, cost −.05. These are ranking conventions, not truth probabilities.",
            }
        )
    return sorted(ranked, key=lambda r: (-r["score"], r["id"])), batch


def prioritize_typed(inv, jev, dataset):
    from firstlook.discovery import analyze, plan_for, validate_plan
    from firstlook.exploration import perspective_coverage
    from firstlook.semantics import measures

    goal = inv.goal or (
        "Understand " + dataset.label(inv.context.focus)
        if inv.context.focus
        else "Build a first understanding of the recorded dataset from complementary perspectives."
    )
    candidates = []
    for f in inv.findings[:12]:
        r = inv.results[f.result_id]
        candidates.append(
            {
                "id": f.id,
                "alias": descriptive_key(f.title, f.id),
                "question": f.title,
                "definition": {
                    "operation": r.plan.operation,
                    "fields": [dataset.label(k) for k in r.plan.fields],
                    "scope": "Recorded active population",
                },
                "family": f.family,
                "support": r.support,
                "cost": 0,
            }
        )
    task_plans = {}
    nums = sorted(measures(dataset), key=lambda f: f != inv.context.focus)
    if nums and not any(
        r.plan.operation == "ecdf" and r.plan.fields == nums[:1] for r in inv.results.values()
    ):
        p = plan_for(
            inv.context, "ecdf", nums[:1], "Inspect cumulative distribution of " + dataset.label(nums[0])
        )
        try:
            validate_plan(dataset, inv.context, p)
            task_plans[p.id] = p
            candidates.append(
                {
                    "id": p.id,
                    "alias": descriptive_key(p.question, p.id),
                    "question": p.question,
                    "definition": {
                        "operation": "ecdf",
                        "meaning": "Cumulative proportion at or below a value",
                    },
                    "family": "ecdf",
                    "support": int(dataset.frame.loc[inv.context.row_ids, nums[0]].notna().sum()),
                    "cost": 1,
                }
            )
        except ValueError:
            pass
    ranked, batch = rank_candidates(candidates, goal, inv.context.id, jev)
    if batch:
        inv.judgments.append(batch)
    inv.recommendations = ranked
    if ranked and ranked[0]["relevance"] is not None and ranked[0]["relevance"] >= 0.45:
        selected = ranked[0]["id"]
        if selected in task_plans:
            r, f = analyze(dataset, inv.context, task_plans[selected])
            companion = next(
                (
                    other
                    for other in inv.results.values()
                    if other.plan.operation == "distribution" and other.plan.fields == r.plan.fields
                ),
                None,
            )
            inv.add_view(r, f)
            if companion and companion.id in inv.results:
                inv.related_views[r.id] = {
                    "companion": companion.id,
                    "intent": "Cumulative shape beside interval counts",
                }
        else:
            inv.findings.sort(key=lambda f: f.id != selected)
    inv.coverage = perspective_coverage(dataset, inv)
    from firstlook.clarifications import clarification_queue

    queue, batch = clarification_queue(dataset, inv.context, goal, jev)
    if batch:
        inv.judgments.append(batch)
    if queue:
        inv.semantic_decisions.append(
            {
                "stage": "clarification_priority",
                "question": queue[0]["id"],
                "method": queue[0]["method"],
                "unlock_count": queue[0]["unlock_count"],
                "semantic_revision": dataset.record.semantic_model.revision,
            }
        )


def rank_proposals(proposals, goal, context, jev, support=None):
    candidates = [
        {
            "id": digest(p.model_dump()),
            "alias": descriptive_key(p.question, digest(p.model_dump())),
            "question": p.question,
            "definition": {"operation": p.operation, "reason": p.reason},
            "family": p.operation,
            "cost": 1,
            "support": (support or {}).get(p.finding_id, 0),
        }
        for p in proposals
    ]
    ranked, batch = rank_candidates(candidates, goal, context, jev)
    by_id = {digest(p.model_dump()): p for p in proposals}
    # Unsettled model judgments retain the deterministic proposal order.
    selected = [by_id[r["id"]] for r in ranked if r["relevance"] is None or r["relevance"] >= 0.45]
    return selected, batch
