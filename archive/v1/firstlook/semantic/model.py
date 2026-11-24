"""Atomic semantic edits and portable contracts. Human declarations never rewrite data."""

from __future__ import annotations
import json
from graphlib import TopologicalSorter, CycleError
import pandas as pd
from firstlook.contracts import Role, digest
from firstlook.semantic_contracts import FieldMeaning, Kind
from firstlook.semantic_contracts import Assertion, MetadataProposal, Metric, SemanticModel
from firstlook.semantic.profile import refresh_questions, inspect_relationship, parsing_scope


def get_model(dataset) -> SemanticModel:
    if dataset.record.semantic_model is None:
        from firstlook.semantic.profile import build_model

        dataset.record.semantic_model = build_model(dataset)
    return dataset.record.semantic_model


def validate_model(dataset, model: SemanticModel) -> SemanticModel:
    from firstlook.analytical_tasks import validate_task_metadata

    validate_task_metadata(dataset, model)
    if model.dataset != dataset.record.fingerprint:
        raise ValueError("This semantic contract belongs to a different dataset.")
    if model.parsing_scope != parsing_scope(dataset):
        raise ValueError("This contract uses different parsing options or a different physical field layout.")
    fields = set(dataset.frame.columns)

    def check(ids):
        if not set(ids) <= fields:
            raise ValueError("A semantic reference uses an unknown field identity.")

    if set(m.field for m in model.meanings) != fields or len(model.meanings) != len(fields):
        raise ValueError("The contract must describe each original field once.")
    if any(assertion.scope != model.dataset for assertion in model.assertions):
        raise ValueError("A semantic assertion has a different dataset scope.")
    for e in model.entities:
        check(e.keys)
        if len(set(e.keys)) != len(e.keys):
            raise ValueError("Entity key fields must be distinct.")
        e.complete = bool(dataset.frame[e.keys].notna().all().all())
        e.unique = not bool(dataset.frame.duplicated(e.keys).any())
        e.distinct = len(dataset.frame[e.keys].dropna().drop_duplicates())
    if model.grain_entity:
        e = model.entity(model.grain_entity)
        if not e.unique or not e.complete:
            raise ValueError(
                "The chosen row identity is not unique and complete. Repeated entities need a finer row grain."
            )
    if model.model_group:
        check([model.model_group])
        group = dataset.frame[model.model_group]
        if group.isna().any() or not 3 <= group.nunique() < len(group):
            raise ValueError(
                "A declared predictive group requires complete repeated identities and at least three groups."
            )
    graph = {m.id: set(v for v in [m.numerator, m.denominator] if v) for m in model.metrics}
    for m in model.metrics:
        check([v for v in [m.field, m.weight] if v])
        if m.entity:
            model.entity(m.entity)
        if m.aggregation == "ratio":
            if not m.numerator or not m.denominator:
                raise ValueError("A ratio requires numerator and denominator metric identities.")
            model.metric(m.numerator)
            model.metric(m.denominator)
            if any(model.metric(mid).transform != "identity" for mid in [m.numerator, m.denominator]):
                raise ValueError(
                    "Compose ratios from untransformed component metrics, then transform the final ratio explicitly."
                )
            if any(
                model.metric(mid).aggregation in {"snapshot_last", "delta"}
                for mid in [m.numerator, m.denominator]
            ):
                raise ValueError(
                    "Temporal snapshot and counter components require a dedicated time comparison; nesting them inside a ratio is not supported."
                )
        if (
            m.aggregation in {"count_distinct", "average_per_entity", "snapshot_last", "delta"}
            and not m.entity
        ):
            raise ValueError("This metric requires an explicit entity.")
        if m.aggregation not in {"count_rows", "count_distinct", "ratio"} and not m.field:
            raise ValueError("This metric requires a value field.")
        if m.aggregation == "weighted_mean" and not m.weight:
            raise ValueError("A weighted mean requires weights.")
        if m.time_policy and m.time_policy not in {t.id for t in model.time_policies}:
            raise ValueError("Unknown time policy.")
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc:
        raise ValueError("Metric definitions cannot be circular.") from exc
    hierarchy = {}
    for rel in model.relationships:
        check([rel.child, rel.parent] + rel.within)
        if rel.scope != model.dataset:
            raise ValueError("Relationship evidence has a different dataset scope.")
        actual = inspect_relationship(dataset, rel.child, rel.parent, rel.within)
        if rel.confirmed and rel.relation == "hierarchy":
            if not actual.strict or not actual.complete:
                raise ValueError(
                    "A roll-up hierarchy requires one recorded parent for every child. Inspect exceptions first."
                )
            hierarchy.setdefault("/".join(rel.within + [rel.child]), set()).add(
                "/".join(rel.within + [rel.parent])
            )
        rel.strict = actual.strict
        rel.complete = actual.complete
        rel.child_levels = actual.child_levels
        rel.violating_levels = actual.violating_levels
        rel.overlap_entities = actual.overlap_entities
        rel.examples = actual.examples
    try:
        tuple(TopologicalSorter(hierarchy).static_order())
    except CycleError as exc:
        raise ValueError("Hierarchy paths cannot contain a cycle.") from exc
    for policy in model.time_policies:
        check([policy.field] + policy.series)
        if policy.field in policy.series or len(set(policy.series)) != len(policy.series):
            raise ValueError("Time series identities must be distinct fields separate from the timestamp.")
        if dataset.field(policy.field).role != Role.TIME:
            raise ValueError("Time policies require a parsed timestamp role.")
        if policy.gap_policy != "preserve" and (
            not policy.confirmed or policy.expected_frequency == "unknown"
        ):
            raise ValueError("Gap filling requires a confirmed observation schedule.")
        if policy.gap_policy == "zero" and (
            policy.kind != "event" or not policy.coverage_complete or not policy.complete_through
        ):
            raise ValueError(
                "Structural zero requires event recording, complete coverage and a last complete date."
            )
        if policy.gap_policy in {"forward_fill", "interpolate"} and policy.max_gap_periods < 1:
            raise ValueError("Carry/interpolation requires a positive maximum gap.")
        if policy.gap_policy == "forward_fill" and policy.kind != "state":
            raise ValueError("Carry-forward requires an explicitly declared state process.")
        if policy.gap_policy == "interpolate" and policy.kind != "instant":
            raise ValueError(
                "Interpolation requires an explicitly declared continuous instantaneous process."
            )
        if policy.complete_through:
            try:
                pd.Timestamp(policy.complete_through)
            except (ValueError, TypeError) as exc:
                raise ValueError("Use a valid complete-through date.") from exc
    return model


def commit_model(
    dataset, candidate: SemanticModel, subject="table", property="contract", value="Updated semantic contract"
) -> None:
    candidate = candidate.model_copy(deep=True)
    validate_model(dataset, candidate)
    aid = digest([subject, property, "human", candidate.revision])
    candidate.assertions = (
        candidate.assertions
        + [
            Assertion(
                id=aid,
                subject=subject,
                property=property,
                value=value,
                origin="human",
                confirmed=True,
                scope=candidate.dataset,
                method="Explicit user declaration; structural preconditions validated",
            )
        ]
    )[-400:]
    refresh_questions(candidate, dataset)
    dataset.record.semantic_model = candidate
    for meaning in candidate.meanings:
        dataset.field(meaning.field).unit = meaning.unit


def configure_meaning(
    dataset, fid: str, kind: Kind, unit: str = "", currency: str = "", basis: str = ""
) -> None:
    candidate = get_model(dataset).model_copy(deep=True)
    meaning = candidate.meaning(fid)
    meaning.kind = kind
    meaning.confirmed = True
    meaning.unit = unit.strip()
    meaning.currency = currency.strip()
    meaning.basis = basis.strip()
    meaning.allowed_transforms = (
        ["identity", "zscore"]
        if kind in {"temperature", "state", "rate", "ratio", "index", "unknown"}
        else ["identity", "log", "sqrt", "zscore"]
    )
    commit_model(dataset, candidate, fid, "kind", kind)


def add_metric(dataset, metric: Metric) -> None:
    candidate = get_model(dataset).model_copy(deep=True)
    candidate.metrics = [m for m in candidate.metrics if m.id != metric.id] + [metric]
    commit_model(dataset, candidate, metric.id, "metric", metric.model_dump(mode="json"))


def proposal_candidate(dataset, proposal: MetadataProposal) -> SemanticModel:
    candidate = get_model(dataset).model_copy(deep=True)
    if proposal.property == "kind":
        meaning = candidate.meaning(proposal.subject)
        meaning = FieldMeaning.model_validate(
            {**meaning.model_dump(mode="json"), "kind": proposal.value, "confirmed": True}
        )
        candidate.meanings = [meaning if m.field == meaning.field else m for m in candidate.meanings]
    elif proposal.property == "unit":
        meaning = candidate.meaning(proposal.subject)
        # A model can refer to an existing explicit unit, never introduce a new one.
        if proposal.value != dataset.field(proposal.subject).unit:
            raise ValueError("A model cannot invent a measurement unit. Enter a known unit yourself.")
        meaning.unit = proposal.value
    elif proposal.property == "grain":
        entity = candidate.entity(proposal.value)
        candidate.grain_entity = entity.id
        candidate.grain_confirmed = True
        candidate.grain = "One " + entity.label + " per recorded row."
    elif proposal.property == "model_group":
        if proposal.value not in dataset.frame:
            raise ValueError("Unknown grouping field.")
        candidate.model_group = proposal.value
    else:
        raise ValueError(
            "Observation schedules and gap meanings require direct human declaration in Time policies."
        )
    validate_model(dataset, candidate)
    return candidate


def export_contract(dataset) -> bytes:
    model = get_model(dataset)
    return json.dumps(model.model_dump(mode="json"), indent=2, allow_nan=False).encode()


def import_contract(dataset, blob: bytes) -> None:
    if len(blob) > 2_000_000:
        raise ValueError("Semantic contracts are limited to 2 MB.")
    candidate = SemanticModel.model_validate_json(blob)
    # Imported machine facts are recomputed; imported declarations are attestations,
    # not authenticated authorship. No supplied fact grants an operation permission.
    from firstlook.semantic.profile import build_model

    fresh = build_model(dataset)
    candidate.assertions = fresh.assertions + [a for a in candidate.assertions if a.origin == "human"][-200:]
    commit_model(
        dataset,
        candidate,
        "table",
        "import",
        "Imported contract for the exact dataset; structural validation repeated",
    )
