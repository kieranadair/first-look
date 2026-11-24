"""Progressive preparation: exact evidence, finite alternatives and one reviewed transaction."""

from __future__ import annotations

import re
import time
from itertools import combinations
from typing import cast

import numpy as np
import pandas as pd

from firstlook.analytical_tasks import AvailabilityRule, TaskDefinition, availability_basis, current_task
from firstlook.contracts import Role, clean, digest
from firstlook.ingest import Dataset
from firstlook.preparation_contracts import PreparationDraft, PreparedChange
from firstlook.semantic.model import commit_model, get_model, validate_model
from firstlook.semantic.policy import decision
from firstlook.semantic.profile import parsing_scope
from firstlook.semantic_contracts import Entity, FieldMeaning, Metric, Relationship, TimePolicy

MAX_COMPOSITE_TESTS = 12


def change_id(kind, subject):
    return kind + "_" + digest(subject)


def subject_value(dataset, kind, subject):
    model = get_model(dataset)
    if kind == "quantity":
        return model.meaning(subject).model_dump(mode="json")
    if kind == "role":
        f = dataset.field(subject)
        return {"role": f.role.value, "order": f.order, "excluded": f.excluded}
    if kind == "grain":
        return {"description": model.grain, "entity": model.grain_entity, "confirmed": model.grain_confirmed}
    if kind in {"task", "availability"}:
        if kind == "task":
            return model.search.get("analytical_task")
        rules = model.search.get("availability", {})
        return rules.get(subject) if isinstance(rules, dict) else None
    collection = {
        "entity": model.entities,
        "metric": model.metrics,
        "relationship": model.relationships,
        "time": model.time_policies,
    }[kind]
    item = next((v for v in collection if v.id == subject), None)
    return item.model_dump(mode="json") if item else None


def make_change(
    dataset, kind, subject, payload, label, reason, origin="heuristic", suggested=False, evidence=None
):
    return PreparedChange(
        id=change_id(kind, subject),
        kind=kind,
        subject=subject,
        payload=clean(payload),
        before=clean(subject_value(dataset, kind, subject)),
        label=label,
        reason=reason,
        origin=origin,
        suggested=suggested,
        evidence=evidence or [],
    )


def _metric_identity(metric):
    return digest(
        {
            k: v
            for k, v in metric.model_dump(mode="json").items()
            if k not in {"id", "label", "description", "confirmed"}
        }
    )


def _witness(dataset, fields, rows, description, **facts):
    ids = list(dict.fromkeys(int(i) for i in rows))[:6]
    return clean(
        {
            "id": digest([fields, description]),
            "description": description,
            "fields": fields,
            "rows": [{"source_row": i, **{f: dataset.frame.at[i, f] for f in fields}} for i in ids],
            "scope": "Exact full uploaded table; examples are illustrative source rows, not a statistical sample.",
            **facts,
        }
    )


def _goal_fields(dataset, goal):
    words = set(re.findall(r"[a-z0-9]+", goal.casefold()))
    return {
        f.id
        for f in dataset.record.fields
        if words & set(re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", f.name).casefold()))
    }


def link_dependencies(dataset, draft):
    """Dependencies describe the same bundle the user will review, never hidden confirmations."""
    model = get_model(dataset)
    available = {c.id: c for c in draft.changes}
    metrics = {m.id: m for m in model.metrics}
    metrics.update({c.subject: Metric.model_validate(c.payload) for c in draft.changes if c.kind == "metric"})
    for c in draft.changes:
        required = []
        if c.kind == "metric":
            m = metrics[c.subject]
            if m.field and m.aggregation in {
                "sum",
                "average_per_entity",
                "weighted_mean",
                "snapshot_last",
                "delta",
                "circular_mean",
            }:
                required.append(change_id("quantity", m.field))
            if m.weight:
                required.append(change_id("quantity", m.weight))
            if m.entity:
                required.append(change_id("entity", m.entity))
            if m.time_policy:
                required.append(change_id("time", m.time_policy))
            for mid in [m.numerator, m.denominator]:
                if mid:
                    required.append(change_id("metric", mid))
        elif c.kind == "grain" and c.payload.get("entity"):
            required.append(change_id("entity", c.payload["entity"]))
        elif c.kind == "availability":
            required.append(change_id("task", "table"))
        if c.kind == "quantity":
            required.append(change_id("role", c.subject))
        c.requires = list(dict.fromkeys(r for r in required if r in available and r != c.id))
    return draft


def build_preparation(dataset, goal="", sources=None):
    """A bounded local draft. Facts are computed automatically; meanings remain reviewable."""
    started = time.perf_counter()
    model, frame = get_model(dataset), dataset.frame
    goal = str(goal).strip()[:1000]
    draft = PreparationDraft(
        dataset=dataset.record.fingerprint,
        parsing_scope=parsing_scope(dataset),
        base_semantics=dataset.context().semantics,
        goal=goal,
        sources=sources or {},
        summary="Python has prepared candidate meanings and metric definitions from the recorded structure. Review the relevant bundle together; descriptive exploration is already available.",
    )
    for meaning in model.meanings:
        if (
            not meaning.confirmed
            and meaning.kind != "unknown"
            and dataset.field(meaning.field).role == Role.MEASURE
        ):
            draft.changes.append(
                make_change(
                    dataset,
                    "quantity",
                    meaning.field,
                    meaning.model_dump(mode="json"),
                    dataset.label(meaning.field) + " · " + meaning.kind,
                    "Candidate quantity kind from the field name and numeric domain. Check its business interpretation.",
                    suggested=True,
                )
            )
    entities = list(model.entities)
    candidates = [f.id for f in dataset.record.fields if f.role == Role.ID and not frame[f.id].is_unique][:6]
    # Composite keys are observations, not proof that a business entity has this key.
    tests = 0
    for keys in combinations(candidates, 2):
        if tests >= MAX_COMPOSITE_TESTS or len(entities) >= 12:
            break
        tests += 1
        if frame[list(keys)].notna().all().all() and not frame.duplicated(list(keys)).any():
            if any(set(e.keys) == set(keys) for e in entities):
                continue
            entities.append(
                Entity(
                    id="e_prep_" + digest(keys),
                    label=" / ".join(dataset.label(f) for f in keys)[:150],
                    keys=list(keys),
                    unique=True,
                    complete=True,
                    distinct=len(frame),
                )
            )
    for entity in entities:
        if not entity.confirmed:
            draft.changes.append(
                make_change(
                    dataset,
                    "entity",
                    entity.id,
                    entity.model_dump(mode="json"),
                    "Recorded identity · " + entity.label,
                    "Distinctness and completeness are observed in this upload. Confirm what the identifier represents.",
                    origin="python",
                    suggested=entity.id in {e.id for e in model.entities},
                )
            )
    if not model.grain_confirmed:
        unique = next((e for e in entities if e.unique and e.complete), None)
        if unique:
            draft.changes.append(
                make_change(
                    dataset,
                    "grain",
                    "table",
                    {"description": "One record identified by " + unique.label + ".", "entity": unique.id},
                    "Row identity · " + unique.label,
                    "The key is unique and complete in this upload; the business meaning of a row remains a proposal.",
                )
            )
    metrics = list(model.metrics)
    means = [m for m in model.meanings if dataset.field(m.field).role == Role.MEASURE]
    # Finite additional recipes. Selection is an explicit declaration of the estimator and its denominator.
    weights = [
        m.field
        for m in means
        if m.kind == "flow"
        and re.search(r"quantity|units|count|exposure|weight", dataset.label(m.field), re.I)
    ][:3]
    for meaning in [m for m in means if m.kind in {"rate", "ratio"}][:4]:
        for weight in weights:
            if weight != meaning.field and (frame[weight].dropna() >= 0).all() and frame[weight].sum() > 0:
                metrics.append(
                    Metric(
                        id="m_prep_weighted_" + digest([meaning.field, weight]),
                        label=("Weighted " + dataset.label(meaning.field) + " by " + dataset.label(weight))[
                            :160
                        ],
                        aggregation="weighted_mean",
                        field=meaning.field,
                        weight=weight,
                        description="Proposed weighted estimator. Confirm that this weight represents the intended denominator/exposure; nonnegative values alone do not establish that.",
                    )
                )
    # Named amount components make useful ratio candidates without inventing algebra.
    amounts = [
        m
        for m in metrics
        if m.aggregation == "sum"
        and m.field
        and not m.entity
        and model.meaning(m.field).kind in {"amount", "flow", "count"}
    ][:8]
    for numerator in amounts:
        for denominator in amounts:
            if (
                numerator.id != denominator.id
                and re.search(r"profit|cost|return|defect", dataset.label(numerator.field), re.I)
                and re.search(r"sales|revenue|total|units|quantity", dataset.label(denominator.field), re.I)
            ):
                metrics.append(
                    Metric(
                        id="m_prep_ratio_" + digest([numerator.id, denominator.id]),
                        label=(numerator.label + " / " + denominator.label)[:160],
                        aggregation="ratio",
                        numerator=numerator.id,
                        denominator=denominator.id,
                        denominator_scope="group",
                        description="Ratio of recomputed component totals in the same group. The business meaning and compatible units require review.",
                    )
                )
    known = set()
    for metric in metrics:
        signature = _metric_identity(metric)
        if signature in known:
            continue
        known.add(signature)
        if metric.confirmed:
            continue
        if len([c for c in draft.changes if c.kind == "metric"]) >= 56:
            break
        kind = model.meaning(metric.field).kind if metric.field else "unknown"
        if metric.aggregation == "sum" and kind in {"rate", "ratio", "state", "cumulative", "temperature"}:
            continue
        draft.changes.append(
            make_change(
                dataset,
                "metric",
                metric.id,
                metric.model_dump(mode="json"),
                metric.label,
                metric.description or "Review this explicit analytical definition.",
                suggested=metric.aggregation == "sum"
                and not metric.entity
                and kind in {"flow", "amount", "count"},
            )
        )
    for rel in model.relationships[:12]:
        if rel.strict and rel.complete and not rel.confirmed:
            draft.changes.append(
                make_change(
                    dataset,
                    "relationship",
                    rel.id,
                    rel.model_dump(mode="json"),
                    dataset.label(rel.child) + " → " + dataset.label(rel.parent),
                    "Every observed child has one recorded parent. Confirm that this is the intended roll-up hierarchy.",
                    origin="python",
                )
            )
    for f in dataset.record.fields:
        if f.role != Role.CATEGORY or f.confirmed:
            continue
        levels = set(frame[f.id].dropna().astype(str))
        for order in [
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ],
            ["Low", "Medium", "High"],
        ]:
            if 3 <= len(levels) and levels <= set(order):
                draft.changes.append(
                    make_change(
                        dataset,
                        "role",
                        f.id,
                        {
                            "role": "ordinal",
                            "order": [v for v in order if v in levels],
                            "excluded": f.excluded,
                        },
                        f.name + " · ordered levels",
                        "Observed labels match a familiar order. Confirm that this order applies here.",
                    )
                )
                break
    draft.evidence, draft.decisions = interpretation_evidence(dataset, goal)
    ambiguous = {q["subject"] for q in draft.decisions if q.get("alternatives")}
    for c in draft.changes:
        if (
            c.kind == "metric"
            and c.payload.get("field") in ambiguous
            and c.payload.get("aggregation") == "sum"
        ):
            c.suggested = False
    draft.telemetry = {
        "local_seconds": round(time.perf_counter() - started, 4),
        "composite_key_tests": tests,
        "rows_checked": len(frame),
        "provider_calls": 0,
    }
    return link_dependencies(dataset, draft)


def interpretation_evidence(dataset, goal=""):
    """Exact numerical alternatives are conditional illustrations, never chosen automatically."""
    model, frame = get_model(dataset), dataset.frame
    witnesses, questions = [], []
    relevant = _goal_fields(dataset, goal)
    for entity in [e for e in model.entities if not e.unique][:4]:
        for meaning in [m for m in model.meanings if dataset.field(m.field).role == Role.MEASURE][:12]:
            if meaning.kind not in {"unknown", "amount", "flow", "count"}:
                continue
            fid = meaning.field
            valid = frame.dropna(subset=entity.keys + [fid])
            grouped = valid.groupby(entity.keys, dropna=False)[fid]
            if (
                not len(valid)
                or grouped.ngroups < 2
                or grouped.nunique().max() != 1
                or len(valid) == grouped.ngroups
            ):
                continue
            row_total, entity_total = float(valid[fid].sum()), float(grouped.first().sum())
            if not np.isfinite([row_total, entity_total]).all():
                continue
            if meaning.confirmed and any(
                m.confirmed and m.field == fid and m.aggregation == "sum" for m in model.metrics
            ):
                continue
            key = valid[valid.duplicated(entity.keys, keep=False)][entity.keys].head(1)
            if key.empty:
                continue
            mask = pd.Series(True, index=valid.index)
            for field in entity.keys:
                mask &= valid[field].eq(key.iloc[0][field])
            rows = list(valid[mask].index[:4]) + list(valid[~mask].index[:2])
            scale = max(abs(row_total), abs(entity_total), 1e-12)
            difference = abs(row_total - entity_total) / scale
            witness = _witness(
                dataset,
                entity.keys + [fid],
                rows,
                dataset.label(fid) + " is constant within recorded " + entity.label,
                row_sum=row_total,
                once_per_entity_sum=entity_total,
                valid_rows=len(valid),
                omitted_rows=len(frame) - len(valid),
                entities=grouped.ngroups,
                relative_difference=difference,
            )
            witnesses.append(witness)
            questions.append(
                clean(
                    {
                        "id": "grain_" + digest([entity.id, fid]),
                        "subject": fid,
                        "entity": entity.id,
                        "question": "Does "
                        + dataset.label(fid)
                        + " belong to each row, or is it repeated from "
                        + entity.label
                        + "?",
                        "reason": "Both are plausible interpretations of equal recorded values. Their totals are shown under explicit alternatives; equality does not prove the value grain.",
                        "witness": witness["id"],
                        "priority": (2 if difference else 0.1)
                        + min(difference, 1)
                        + (2 if fid in relevant else 0),
                        "alternatives": [
                            {
                                "assumption": "An additive amount belongs to each recorded row",
                                "total": row_total,
                            },
                            {
                                "assumption": "An additive amount belongs once to each recorded identifier",
                                "total": entity_total,
                            },
                        ],
                        "scope": "Full upload, complete identifier/value records only. Other semantic permissions are not established.",
                        "relative_difference": difference,
                    }
                )
            )
            if len(witnesses) >= 12:
                break
        if len(witnesses) >= 12:
            break
    for q in model.clarifications:
        if len(questions) >= 24:
            break
        if q.property == "availability" and current_task(dataset).purpose != "prediction":
            continue
        # Observation policies are deferred until the requested work depends on filling a gap.
        if q.property == "time" and not re.search(r"gap|missing date|zero|interpol|schedule", goal, re.I):
            continue
        questions.append(
            clean(
                {
                    "id": q.id,
                    "subject": q.subject,
                    "question": q.question,
                    "reason": q.reason,
                    "priority": q.priority
                    + (2 if q.subject in relevant else 0)
                    + min(len(q.affected_metrics), 6) / 6,
                    "affected_metrics": q.affected_metrics,
                    "witness": "",
                }
            )
        )
    return witnesses[:24], sorted(questions, key=lambda q: (-float(q["priority"]), str(q["id"])))[:24]


def assert_scope(dataset, draft):
    if draft.dataset != dataset.record.fingerprint or draft.parsing_scope != parsing_scope(dataset):
        raise ValueError(
            "Preparation belongs to different source bytes or parsing. Prepare this upload again."
        )


def prepare_grain_answer(dataset, draft, question_id, once_per_entity=False):
    """An explicit answer expands to an additive quantity, entity and metric definition."""
    assert_scope(dataset, draft)
    question = next((q for q in draft.decisions if q["id"] == question_id and q.get("entity")), None)
    if question is None:
        raise ValueError("Choose a current value-grain clarification.")
    fid, eid = str(question["subject"]), str(question["entity"])
    meaning = get_model(dataset).meaning(fid).model_copy(deep=True)
    if meaning.kind not in {"amount", "flow", "count", "unknown"}:
        raise ValueError("This quantity is not an eligible additive amount.")
    if meaning.kind == "unknown":
        meaning.kind = "amount"
    entity = get_model(dataset).entity(eid)
    metric = Metric(
        id="m_prep_answer_" + digest([fid, eid if once_per_entity else None]),
        label=(
            dataset.label(fid) + (" once per " + entity.label if once_per_entity else " across recorded rows")
        )[:160],
        aggregation="sum",
        field=fid,
        entity=eid if once_per_entity else None,
        description="Explicit clarification answer: additive value counted "
        + ("once per recorded identifier." if once_per_entity else "on each recorded row."),
    )
    additions = [
        make_change(
            dataset,
            "quantity",
            fid,
            meaning.model_dump(mode="json"),
            dataset.label(fid) + " · additive " + meaning.kind,
            "Your selected interpretation declares an additive quantity and its value grain.",
            "heuristic",
        ),
        make_change(
            dataset,
            "metric",
            metric.id,
            metric.model_dump(mode="json"),
            metric.label,
            metric.description,
            "heuristic",
        ),
    ]
    if once_per_entity:
        additions.append(
            make_change(
                dataset,
                "entity",
                eid,
                entity.model_dump(mode="json"),
                "Recorded identity · " + entity.label,
                "Identifier explicitly selected in the value-grain clarification.",
                "python",
            )
        )
    by_id = {c.id: c for c in draft.changes}
    by_id.update({c.id: c for c in additions})
    draft.changes = list(by_id.values())[:140]
    link_dependencies(dataset, draft)
    return draft, change_id("metric", metric.id)


def change_state(dataset, draft, change):
    assert_scope(dataset, draft)
    if change.id in draft.applied:
        return "applied"
    if change.issue:
        return "blocked"
    if subject_value(dataset, change.kind, change.subject) != change.before:
        return "stale"
    return "ready"


def selection_closure(draft, ids):
    by_id = {c.id: c for c in draft.changes}
    requested = list(dict.fromkeys(ids))
    if not requested or not set(requested) <= set(by_id):
        raise ValueError("Choose known preparation changes before applying a bundle.")
    result = set(requested)
    pending = list(requested)
    while pending:
        for dependency in by_id[pending.pop()].requires:
            if dependency not in by_id:
                raise ValueError("A preparation dependency is missing. Prepare a fresh draft.")
            if dependency not in result:
                result.add(dependency)
                pending.append(dependency)
    return [c for c in draft.changes if c.id in result and c.id not in draft.applied]


def candidate_bundle(dataset, draft, ids):
    """Validate all changes on an isolated copy; failures cannot partially change the source."""
    assert_scope(dataset, draft)
    chosen = selection_closure(draft, ids)
    if not chosen:
        raise ValueError("This bundle has already been applied.")
    for c in chosen:
        state = change_state(dataset, draft, c)
        if state != "ready":
            raise ValueError(
                c.label + ": " + (c.issue or "the declaration changed since this draft; refresh it.")
            )
    clone = Dataset(dataset.record.model_copy(deep=True), dataset.frame, dataset.raw)
    # Role validation must precede quantities; it may add identifier/time proposals.
    roles = [c for c in chosen if c.kind == "role"]
    if roles:
        from firstlook.semantics import apply_semantics, semantic_table

        table = semantic_table(clone)
        for c in roles:
            table.loc[table.field == c.subject, "role"] = c.payload["role"]
            table.loc[table.field == c.subject, "order"] = " | ".join(
                str(v) for v in c.payload.get("order", [])
            )
            table.loc[table.field == c.subject, "exclude"] = bool(c.payload.get("excluded", False))
            table.loc[table.field == c.subject, "confirmed"] = True
        apply_semantics(clone, table)
    model = get_model(clone).model_copy(deep=True)
    for c in chosen:
        payload = dict(c.payload)
        if c.kind == "quantity":
            payload["confirmed"] = True
            item = FieldMeaning.model_validate(payload)
            if item.field != c.subject or clone.field(item.field).role != Role.MEASURE:
                raise ValueError("Quantity definitions require the exact recorded measure field.")
            # Availability has a task-bound editor, separate from a quantity guess.
            item.available_at_prediction = model.meaning(item.field).available_at_prediction
            if not item.allowed_transforms:
                item.allowed_transforms = (
                    ["identity", "zscore"]
                    if item.kind in {"temperature", "state", "rate", "ratio", "index", "unknown"}
                    else ["identity", "log", "sqrt", "zscore"]
                )
            model.meanings = [item if v.field == item.field else v for v in model.meanings]
        elif c.kind in {"entity", "metric", "relationship", "time"}:
            cls, attribute = {
                "entity": (Entity, "entities"),
                "metric": (Metric, "metrics"),
                "relationship": (Relationship, "relationships"),
                "time": (TimePolicy, "time_policies"),
            }[c.kind]
            payload["confirmed"] = True
            item = cls.model_validate(payload)
            if item.id != c.subject:
                raise ValueError("Prepared identity differs from its payload.")
            setattr(model, attribute, [v for v in getattr(model, attribute) if v.id != c.subject] + [item])
        elif c.kind == "grain":
            model.grain = str(payload["description"])
            model.grain_entity = payload.get("entity")
            model.grain_confirmed = True
        elif c.kind == "task":
            task = TaskDefinition.model_validate(payload)
            model.search["analytical_task"] = task.model_dump(mode="json")
    for c in [v for v in chosen if v.kind == "availability"]:
        rule = AvailabilityRule.model_validate(c.payload)
        if rule.field != c.subject:
            raise ValueError("Availability refers to a different field.")
        task = (
            TaskDefinition.model_validate(model.search["analytical_task"])
            if model.search.get("analytical_task")
            else TaskDefinition(dataset=dataset.record.fingerprint)
        )
        if rule.status == "known_at_anchor":
            rule.basis = availability_basis(task)
        existing = model.search.get("availability", {})
        if not isinstance(existing, dict):
            raise ValueError("Invalid availability declarations.")
        rules = dict(existing)
        rules[c.subject] = rule.model_dump(mode="json")
        model.search["availability"] = rules
    validate_model(clone, model)
    clone.record.semantic_model = model
    # Mathematical incompatibilities are blocked now, rather than saving a broken metric bundle.
    for c in [v for v in chosen if v.kind == "metric"]:
        metric = model.metric(c.subject)
        time_field = next((t.field for t in model.time_policies if t.id == metric.time_policy), None)
        permission = decision(clone, metric, [], time_field=time_field)
        if permission.status != "allowed":
            raise ValueError(c.label + ": " + " ".join(permission.reasons + permission.requirements))
    return clone, chosen


def apply_preparation(dataset, draft, ids):
    clone, chosen = candidate_bundle(dataset, draft, ids)
    reviewed = [
        {
            "id": c.id,
            "kind": c.kind,
            "subject": c.subject,
            "value": c.payload,
            "origin": c.origin,
            "reason": c.reason,
            "evidence": [e.model_dump(mode="json") for e in c.evidence],
            "review": c.review,
        }
        for c in chosen
    ]
    commit_model(
        clone,
        get_model(clone),
        "table",
        "prepared_bundle",
        clean({"policy": draft.policy, "request": draft.request, "reviewed_changes": reviewed}),
    )
    dataset.record.fields = clone.record.fields
    dataset.record.semantic_model = clone.record.semantic_model
    draft.applied = list(dict.fromkeys(draft.applied + [c.id for c in chosen]))
    draft.evidence, draft.decisions = interpretation_evidence(dataset, draft.goal)
    draft.telemetry["applied_changes"] = len(draft.applied)
    draft.telemetry["apply_transactions"] = int(draft.telemetry.get("apply_transactions", 0)) + 1
    return [c.id for c in chosen]


def validate_preparation_evidence(dataset, raw):
    """Inspect records without providers; source-backed replay verifies illustrative rows."""
    from firstlook.judgments import JudgmentBatch

    draft = PreparationDraft.model_validate(raw)
    assert_scope(dataset, draft)
    fields = {f.id for f in dataset.record.fields}
    for c in draft.changes:
        if c.id != change_id(c.kind, c.subject):
            raise ValueError("A preparation change has an inconsistent identity.")
        for quote in c.evidence:
            if quote.source not in draft.sources or quote.quote not in draft.sources[quote.source]:
                if not c.issue:
                    raise ValueError("A preparation citation is absent from its supplied source.")
    for witness in draft.evidence:
        raw_fields, rows = witness.get("fields"), witness.get("rows")
        if (
            not isinstance(raw_fields, list)
            or not all(isinstance(f, str) for f in raw_fields)
            or not isinstance(rows, list)
        ):
            raise ValueError("Invalid preparation witness fields/rows.")
        witness_fields = cast(list[str], raw_fields)
        if not witness_fields or not set(witness_fields) <= fields or len(rows) > 6:
            raise ValueError("A preparation witness refers to unknown fields or exceeds its row bound.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid preparation source example.")
            rid = row.get("source_row")
            if isinstance(rid, bool) or not isinstance(rid, int) or not 0 <= rid < dataset.record.rows:
                raise ValueError("A preparation source example has an invalid row membership.")
            if set(row) != {"source_row", *witness_fields}:
                raise ValueError("Preparation source example fields disagree with their witness.")
            if not dataset.frame.empty:
                actual = clean(
                    {"source_row": rid, **{fid: dataset.frame.at[rid, fid] for fid in witness_fields}}
                )
                if actual != row:
                    raise ValueError("A preparation source example disagrees with the supplied source bytes.")
        if "row_sum" in witness and not dataset.frame.empty:
            keys, fid = witness_fields[:-1], witness_fields[-1]
            if not keys:
                raise ValueError("A repeated-entity comparison needs identifier fields.")
            valid = dataset.frame.dropna(subset=keys + [fid])
            grouped = valid.groupby(keys, dropna=False)[fid]
            expected = clean(
                {
                    "row_sum": float(valid[fid].sum()),
                    "once_per_entity_sum": float(grouped.first().sum()),
                    "valid_rows": len(valid),
                    "omitted_rows": len(dataset.frame) - len(valid),
                    "entities": grouped.ngroups,
                }
            )
            if any(witness.get(k) != v for k, v in expected.items()) or grouped.nunique().max() != 1:
                raise ValueError("A preparation interpretation comparison disagrees with the supplied data.")
    for record in draft.records:
        if "answers" in record and "definitions" in record:
            if JudgmentBatch.model_validate(record).context != draft.base_semantics:
                raise ValueError("A preparation judgment has a different semantic scope.")
        elif record.get("packet"):
            packet = record["packet"]
            preparation = packet.get("preparation") if isinstance(packet, dict) else None
            if not isinstance(preparation, dict) or preparation.get("source_fingerprint") != draft.dataset:
                raise ValueError("A preparation provider record has a different source scope.")
    return draft


def preparation_readiness(dataset, goal="", rows=None):
    model = get_model(dataset)
    rows = list(dataset.frame.index) if rows is None else rows
    relevant = _goal_fields(dataset, goal)
    entries = []
    for metric in model.metrics:
        time_field = next((t.field for t in model.time_policies if t.id == metric.time_policy), None)
        permission = decision(dataset, metric, [], time_field=time_field, rows=rows)
        entries.append(
            {
                "id": metric.id,
                "label": metric.label,
                "field": metric.field,
                "status": permission.status,
                "requirements": permission.requirements,
                "reasons": permission.reasons,
                "relevant": bool(metric.field in relevant),
                "aggregation": metric.aggregation,
                "time_field": time_field,
            }
        )
    ready = [v for v in entries if v["status"] == "allowed"]
    # Prefer an accepted task-relevant business metric, then an accepted amount, then a recorded mean.
    ordered = sorted(
        ready,
        key=lambda v: (
            not v["relevant"],
            v["aggregation"] not in {"sum", "ratio", "average_per_entity", "weighted_mean"},
            v["aggregation"] == "count_rows",
            v["id"],
        ),
    )
    return {
        "status": "Ready to explore recorded data",
        "ready": ready,
        "pending": [v for v in entries if v["status"] != "allowed"],
        "recommended": ordered[:4],
        "scope": "Readiness is specific to these operations; unresolved meanings remain visible.",
    }
