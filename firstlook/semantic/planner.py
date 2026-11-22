"""Bounded semantic planning shared by discovery, questions and model packets."""

from __future__ import annotations

from firstlook.contracts import clean
from firstlook.semantic.model import get_model
from firstlook.semantic.policy import decision
from firstlook.semantics import dimensions


def metric_fields(dataset, metric, seen=None):
    seen = set(seen or [])
    if metric.id in seen:
        raise ValueError("Circular metric definition.")
    seen.add(metric.id)
    fields = [f for f in [metric.field, metric.weight] if f]
    if metric.entity:
        fields += get_model(dataset).entity(metric.entity).keys
    if metric.aggregation == "ratio":
        for mid in [metric.numerator, metric.denominator]:
            fields += metric_fields(dataset, get_model(dataset).metric(mid), seen)
    return list(dict.fromkeys(fields))


def metric_plan(dataset, ctx, mid, groups=None, time_field=None, period="MS", question=None, **extra):
    from firstlook.discovery import plan_for

    metric = get_model(dataset).metric(mid)
    groups = list(groups or [])
    fields = list(
        dict.fromkeys(metric_fields(dataset, metric) + groups + ([time_field] if time_field else []))
    )
    params = {"metric": mid, "group_by": groups, "period": period, **extra}
    if time_field:
        params["time_field"] = time_field
    title = question or metric.label + (
        " over time"
        if time_field
        else " by " + " / ".join(dataset.label(f) for f in groups)
        if groups
        else " in the active population"
    )
    return plan_for(ctx, "metric", fields, title, params)


def semantic_packet(dataset, limit=16):
    """Bound metadata, not raw rows. Meanings carry their confirmation state."""
    model = get_model(dataset)
    return clean(
        {
            "revision": model.revision,
            "grain": model.grain,
            "grain_confirmed": model.grain_confirmed,
            "model_group": model.model_group,
            "meanings": [m.model_dump(mode="json") for m in model.meanings],
            "entities": [e.model_dump(mode="json") for e in model.entities],
            "metrics": [m.model_dump(mode="json") for m in model.metrics[:limit]],
            "relationships": [
                r.model_dump(mode="json", exclude={"examples"}) for r in model.relationships[:24]
            ],
            "time_policies": [t.model_dump(mode="json") for t in model.time_policies],
            "unresolved": [q.model_dump(mode="json") for q in model.clarifications[:8]],
            "scope": "Exact uploaded table; observed dependencies do not prove future or domain constraints.",
        }
    )


def candidates(dataset, ctx):
    model = get_model(dataset)
    dims = [f for f in dimensions(dataset) if 2 <= dataset.frame.loc[ctx.row_ids, f].nunique() <= 30][:2]
    proposed = []
    log = []
    # Explicit authored definitions get first consideration, not arbitrary numeric sums.
    selected = sorted(
        model.metrics, key=lambda m: (not (m.confirmed and m.aggregation not in {"count_rows", "mean"}), m.id)
    )[:16]
    for metric in selected:
        if metric.aggregation == "count_distinct" and metric.entity and model.entity(metric.entity).unique:
            continue
        if metric.aggregation == "ratio" and metric.numerator == metric.denominator:
            base = model.metric(metric.numerator or "")
            if base.entity and model.entity(base.entity).unique:
                continue
        groups = dims[:1]
        time = None
        if metric.aggregation in {"snapshot_last", "delta"}:
            policy = next((t for t in model.time_policies if t.id == metric.time_policy), None)
            time = policy.field if policy else None
            groups = []
        check = decision(dataset, metric, groups, time, ctx.row_ids)
        plan = metric_plan(dataset, ctx, metric.id, groups, time)
        log.append(
            {
                "operation": "metric",
                "plan": plan.id,
                "metric": metric.id,
                "eligible": check.status == "allowed",
                "status": check.status,
                "reason": " ".join(check.reasons + check.requirements),
                "rules": check.rules,
            }
        )
        if check.status == "allowed":
            priority = (
                0.97
                if metric.aggregation not in {"mean", "count_rows", "count_distinct", "ratio"}
                else 0.9
                if metric.aggregation == "ratio"
                else 0.48
            )
            if ctx.focus in plan.fields:
                priority += 0.15
            proposed.append((priority, plan))
    # A confirmed time process should have an eligible time view even when its native
    # metric is not a snapshot/counter. At most two extra candidates.
    for policy in [t for t in model.time_policies if t.confirmed][:2]:
        metric = next(
            (
                m
                for m in sorted(model.metrics, key=lambda v: v.aggregation != "sum")
                if m.confirmed
                and m.aggregation in {"sum", "count_rows"}
                and decision(dataset, m, [], policy.field, ctx.row_ids).status == "allowed"
            ),
            None,
        )
        if metric:
            proposed.append((0.92, metric_plan(dataset, ctx, metric.id, [], policy.field)))
    return proposed, log
