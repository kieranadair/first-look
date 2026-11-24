"""Bounded exact structural discovery; semantic interpretations remain proposals."""

from __future__ import annotations
import re
from itertools import combinations
import numpy as np
import pandas as pd
from firstlook.contracts import Role, clean, digest
from firstlook.semantic_contracts import (
    Assertion,
    Clarification,
    Entity,
    FieldMeaning,
    Metric,
    Relationship,
    SemanticModel,
    TimePolicy,
)


def parsing_scope(dataset) -> str:
    return digest(
        {
            "parser": dataset.record.parser,
            "fields": [(f.id, f.name, f.physical_type) for f in dataset.record.fields],
        }
    )


def build_model(dataset) -> SemanticModel:
    frame, record = dataset.frame, dataset.record
    model = SemanticModel(dataset=record.fingerprint, parsing_scope=parsing_scope(dataset))
    assertions = []

    def assert_fact(subject, prop, value, method, evidence=None, origin="computed", confirmed=False):
        assertions.append(
            Assertion(
                id=digest([subject, prop]),
                subject=subject,
                property=prop,
                value=clean(value),
                origin=origin,
                confirmed=confirmed,
                scope=record.fingerprint,
                method=method,
                evidence=clean(evidence or {}),
            )
        )

    for f in record.fields:
        s = frame[f.id]
        kind = "unknown"
        if f.role == Role.MEASURE:
            name = f.name.casefold()
            if re.search(r"temp|celsius|fahrenheit", name):
                kind = "temperature"
            elif re.search(r"balance|inventory|stock|headcount", name):
                kind = "state"
            elif re.search(r"cumulative|counter|meter.*reading", name):
                kind = "cumulative"
            elif re.search(r"percent|discount|margin|ratio|probability|rate", name):
                kind = "ratio"
            elif re.search(r"price|cost.per|per.unit", name):
                kind = "rate"
            elif re.search(r"sales|revenue|profit|amount|quantity|consumption|^cnt$", name):
                kind = "flow"
            elif re.search(r"(^|_)total$", name):
                kind = "amount"
        model.meanings.append(FieldMeaning(field=f.id, kind=kind, unit=f.unit))
        if f.role == Role.MEASURE:
            values = s.dropna().astype(float)
            assert_fact(
                f.id,
                "numeric_domain",
                {
                    "nonmissing": len(values),
                    "negative": int((values < 0).sum()),
                    "zero": int((values == 0).sum()),
                    "min": values.min(),
                    "max": values.max(),
                },
                "Exact finite recorded values",
            )
        if f.role == Role.ID and len(model.entities) < 8:
            complete = bool(s.notna().all())
            entity = Entity(
                id="e_" + f.id,
                label=f.name,
                keys=[f.id],
                unique=bool(s.is_unique),
                complete=complete,
                distinct=int(s.nunique()),
            )
            model.entities.append(entity)
            assert_fact(
                entity.id,
                "identity",
                {"unique": entity.unique, "complete": complete, "distinct": entity.distinct},
                "Exact distinct/nonmissing counts",
            )
        if f.role == Role.TIME and len(model.time_policies) < 8:
            dates = s.dropna().sort_values().drop_duplicates()
            intervals = dates.diff().dropna().dt.total_seconds()
            mode = float(intervals.mode().iloc[0]) if len(intervals) else None
            policy = TimePolicy(id="t_" + f.id, field=f.id, observed_interval_seconds=mode)
            model.time_policies.append(policy)
            assert_fact(
                policy.id,
                "observed_time",
                {"start": s.min(), "end": s.max(), "typical_interval_seconds": mode},
                "Most frequent positive interval; not an expected schedule",
            )
    model.metrics.append(
        Metric(
            id="m_rows",
            label="Recorded rows",
            aggregation="count_rows",
            confirmed=True,
            description="Count recorded source rows in the active context.",
        )
    )
    for entity in model.entities:
        mid = "m_distinct_" + entity.id
        model.metrics.append(
            Metric(
                id=mid,
                label="Distinct " + entity.label,
                aggregation="count_distinct",
                entity=entity.id,
                confirmed=True,
                description="Count distinct nonmissing recorded identifiers; entity meaning remains reviewable.",
            )
        )
        model.metrics.append(
            Metric(
                id=mid + "_share",
                label="Share of distinct " + entity.label,
                aggregation="ratio",
                numerator=mid,
                denominator=mid,
                confirmed=True,
                description="Group incidence divided by distinct identifiers in the active population. Groups may overlap.",
            )
        )
    for meaning in [m for m in model.meanings if dataset.field(m.field).role == Role.MEASURE][:24]:
        fid = meaning.field
        model.metrics.append(
            Metric(
                id="m_mean_" + fid,
                label="Mean recorded " + dataset.label(fid),
                field=fid,
                aggregation="mean",
                confirmed=True,
                description="Equal weighting of nonmissing recorded rows; not an entity-level average.",
            )
        )
        if meaning.kind in {"flow", "amount", "count", "state", "cumulative", "rate", "ratio"}:
            model.metrics.append(
                Metric(
                    id="m_total_" + fid,
                    label="Total " + dataset.label(fid),
                    field=fid,
                    aggregation="sum",
                    description="Proposed total. Confirm quantity meaning and value grain before use.",
                )
            )
    # Finite templates suggest analytical definitions, never silently approve them.
    amounts = [m for m in model.meanings if m.kind in {"flow", "amount", "count"}][:6]
    for entity in [e for e in model.entities if not e.unique][:2]:
        for meaning in amounts:
            model.metrics.append(
                Metric(
                    id="m_per_" + entity.id + "_" + meaning.field,
                    label=dataset.label(meaning.field) + " per distinct " + entity.label,
                    aggregation="average_per_entity",
                    field=meaning.field,
                    entity=entity.id,
                    description="Proposed sum of recorded amounts divided by distinct nonmissing entities. Confirm the amount belongs to each recorded row.",
                )
            )
    for meaning in [m for m in model.meanings if m.kind in {"state", "cumulative"}][:4]:
        if model.entities and model.time_policies:
            aggregation = "snapshot_last" if meaning.kind == "state" else "delta"
            model.metrics.append(
                Metric(
                    id="m_temporal_" + meaning.field,
                    label=("Last snapshot of " if aggregation == "snapshot_last" else "Counter increment in ")
                    + dataset.label(meaning.field),
                    field=meaning.field,
                    aggregation=aggregation,
                    entity=model.entities[0].id,
                    time_policy=model.time_policies[0].id,
                    description="Proposed temporal definition; confirm quantity, entity grain and observation process.",
                )
            )
    dims = [
        f.id
        for f in record.fields
        if f.role in {Role.CATEGORY, Role.ORDINAL, Role.BOOL} and 2 <= frame[f.id].nunique() <= 100
    ][:10]
    children = list(dict.fromkeys([e.keys[0] for e in model.entities] + dims))
    tested = 0
    for child in children:
        if frame[child].is_unique:
            continue  # A unique ID trivially determines every column.
        for parent in dims:
            if parent == child or len(model.relationships) >= 80:
                continue
            if child in dims and frame[child].nunique() < frame[parent].nunique():
                continue
            rel = inspect_relationship(dataset, child, parent)
            tested += 1
            if rel.strict or child not in dims:
                model.relationships.append(rel)
    # Test a bounded family of repeated higher-grain values; equality never proves intent.
    for e in model.entities[:4]:
        if e.unique:
            continue
        for m in [v for v in model.meanings if v.kind in {"flow", "amount", "state"}][:12]:
            sub = frame[e.keys + [m.field]].dropna()
            groups = sub.groupby(e.keys, dropna=False)[m.field].nunique()
            if len(groups) >= 2 and groups.max() == 1:
                assert_fact(
                    m.field,
                    "constant_within_" + e.id,
                    True,
                    "Exact observed entity/value dependency",
                    {"entity": e.id, "groups": len(groups)},
                    origin="computed",
                )
                if m.kind in {"flow", "amount"}:
                    model.metrics.append(
                        Metric(
                            id="m_entity_total_" + e.id + "_" + m.field,
                            label=dataset.label(m.field) + " once per " + e.label,
                            aggregation="sum",
                            field=m.field,
                            entity=e.id,
                            description="Proposal from exact repeated values within recorded identities. Equality is not proof of value grain; confirm whether deduplication represents the business amount.",
                        )
                    )
    bounded = [
        m.field
        for m in model.meanings
        if dataset.field(m.field).role == Role.MEASURE and frame[m.field].dropna().between(0, 1).all()
    ][:8]
    for subset in combinations(bounded, 3):
        valid = frame[list(subset)].dropna()
        if len(valid) >= 20 and np.allclose(valid.sum(axis=1), 1, atol=1e-8):
            assert_fact(
                "table",
                "candidate_composition",
                list(subset),
                "Exact row sums on complete records; closure meaning unconfirmed",
                {"rows": len(valid)},
                origin="heuristic",
            )
            break
    model.assertions = assertions
    model.search = {
        "method_version": "semantic-1",
        "relationship_tests": tested,
        "relationship_cap": 80,
        "entity_cap": 8,
        "numeric_metric_cap": 24,
        "rows_checked": len(frame),
    }
    refresh_questions(model, dataset)
    return model


def inspect_relationship(dataset, child: str, parent: str, within: list[str] | None = None) -> Relationship:
    if child == parent or child not in dataset.frame or parent not in dataset.frame:
        raise ValueError("Choose two different known fields.")
    within = list(within or [])
    if (
        len(within) > 2
        or set(within) & {child, parent}
        or len(set(within)) != len(within)
        or not set(within) <= set(dataset.frame)
    ):
        raise ValueError("Choose at most two separate context fields for the hierarchy.")
    frame = dataset.frame[[child, parent] + within]
    valid = frame.dropna()
    counts = valid.groupby(within + [child], dropna=False)[parent].nunique()
    bad = counts[counts > 1]
    examples = []
    for c in bad.index[:5]:
        values = c if isinstance(c, tuple) else (c,)
        mask = pd.Series(True, index=valid.index)
        for key, value in zip(within + [child], values):
            mask &= valid[key].eq(value)
        examples.append(
            {"child": str(c), "parents": valid.loc[mask, parent].astype(str).unique()[:5].tolist()}
        )
    return Relationship(
        id=digest([child, parent, within]) if within else digest([child, parent]),
        child=child,
        parent=parent,
        within=within,
        relation="hierarchy" if not len(bad) else "membership",
        strict=bool(len(counts) > 0 and not len(bad)),
        complete=bool(frame.notna().all().all()),
        child_levels=len(counts),
        violating_levels=len(bad),
        overlap_entities=len(bad),
        scope=dataset.record.fingerprint,
        examples=examples,
    )


def refresh_questions(model: SemanticModel, dataset) -> None:
    questions = []
    task = model.search.get("analytical_task")
    rules = model.search.get("availability", {})
    if isinstance(task, dict) and task.get("purpose") == "prediction" and isinstance(rules, dict):
        for field in dataset.record.fields:
            raw = rules.get(field.id, {})
            if (
                field.role in {Role.MEASURE, Role.CATEGORY, Role.BOOL, Role.ORDINAL, Role.TEXT}
                and not field.excluded
                and field.id != task.get("target")
                and (
                    not isinstance(raw, dict)
                    or raw.get("status", "unreviewed") == "unreviewed"
                    or (
                        raw.get("status") == "known_at_anchor"
                        and raw.get("basis")
                        != digest(
                            {
                                "decision_time": task.get("decision_time"),
                                "anchor_field": task.get("anchor_field"),
                            }
                        )
                    )
                    or (raw.get("mutable") and not raw.get("history_available"))
                )
            ):
                questions.append(
                    Clarification(
                        id="q_availability_" + field.id,
                        subject=field.id,
                        property="availability",
                        question="Was " + field.name + " known at the declared decision time?",
                        reason="Prospective predictors require reviewed time-of-knowledge evidence. Use Task & availability; a column name or observed association does not establish availability.",
                        priority=0.97,
                    )
                )
                if len(questions) >= 8:
                    break
    for meaning in model.meanings:
        if not meaning.confirmed and meaning.kind != "unknown":
            affected = [
                m.id
                for m in model.metrics
                if m.field == meaning.field and m.aggregation not in {"mean", "median"}
            ]
            questions.append(
                Clarification(
                    id="q_kind_" + meaning.field,
                    subject=meaning.field,
                    property="kind",
                    suggested=meaning.kind,
                    question="What does " + dataset.label(meaning.field) + " measure?",
                    reason="This determines whether totals, temporal roll-ups and transformations preserve meaning.",
                    priority=0.9 if affected else 0.45,
                    affected_metrics=affected,
                )
            )
    if not model.grain_confirmed:
        questions.append(
            Clarification(
                id="q_grain",
                subject="table",
                property="grain",
                question="What does one recorded row represent?",
                reason="Rows, orders, customers and readings are different analytical units.",
                priority=0.95,
            )
        )
    for metric in model.metrics:
        equivalent = any(
            other.confirmed
            and (other.aggregation, other.field, other.entity)
            == (metric.aggregation, metric.field, metric.entity)
            for other in model.metrics
        )
        if not metric.confirmed and metric.entity and not equivalent:
            questions.append(
                Clarification(
                    id="q_metric_" + metric.id,
                    subject=metric.id,
                    property="metric",
                    question="Is " + metric.label + " the quantity you want?",
                    reason="Confirm the value grain and entity denominator before this proposed definition can run.",
                    priority=0.8,
                    affected_metrics=[metric.id],
                )
            )
    for policy in model.time_policies:
        if not policy.confirmed:
            questions.append(
                Clarification(
                    id="q_time_" + policy.id,
                    subject=policy.id,
                    property="time",
                    question="What observations are expected for " + dataset.label(policy.field) + "?",
                    reason="Observed cadence cannot establish whether an absent period means zero, unknown or not scheduled.",
                    priority=0.65,
                )
            )
    model.clarifications = sorted(questions, key=lambda q: -q.priority)[:80]
