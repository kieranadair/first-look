"""User corrections are transactions; validity is independent of model preference."""

from __future__ import annotations

import pandas as pd

from firstlook.contracts import FieldSpec, Role, SemanticReview
from firstlook.ingest import Dataset


def semantic_table(dataset: Dataset) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "field": f.id,
                "name": f.name,
                "role": f.role.value,
                "unit": f.unit,
                "order": " | ".join(f.order),
                "exclude": f.excluded,
                "confirmed": f.confirmed,
            }
            for f in dataset.record.fields
        ]
    )


def apply_semantics(dataset: Dataset, edited: pd.DataFrame) -> list[str]:
    if set(edited["field"]) != {f.id for f in dataset.record.fields} or len(edited) != len(
        dataset.record.fields
    ):
        raise ValueError("The semantic editor must contain every original field once.")
    updated: list[FieldSpec] = []
    changed = []
    for _, row in edited.iterrows():
        old = dataset.field(row["field"])
        role = Role(row["role"])
        raw_order = "" if pd.isna(row["order"]) else str(row["order"])
        order = [v.strip() for v in raw_order.split("|") if v.strip()]
        s = dataset.frame[old.id]
        if role == Role.MEASURE and not pd.api.types.is_numeric_dtype(s):
            raise ValueError(f"{old.name}: a measure requires numeric values.")
        if role == Role.TIME and not pd.api.types.is_datetime64_any_dtype(s):
            raise ValueError(f"{old.name}: timestamps must parse successfully before use.")
        if role == Role.ORDINAL and (
            not order or len(order) != len(set(order)) or not set(s.dropna().astype(str)).issubset(order)
        ):
            raise ValueError(f"{old.name}: declare each observed category exactly once in its order.")
        new = old.model_copy(
            update={
                "role": role,
                "unit": "" if pd.isna(row["unit"]) else str(row["unit"]).strip(),
                "order": order,
                "excluded": bool(row["exclude"]),
                "confirmed": bool(row["confirmed"]),
            }
        )
        if new != old:
            new.confirmed = True
            new.evidence = "User correction"
            changed.append(old.id)
        updated.append(new)
    dataset.record.fields = updated
    if changed and dataset.record.semantic_model is not None:
        from firstlook.semantic.model import get_model
        from firstlook.semantic.profile import build_model, refresh_questions

        model = get_model(dataset)
        for meaning in model.meanings:
            meaning.unit = dataset.field(meaning.field).unit
            if meaning.field in changed:
                meaning.confirmed = False
        # Newly corrected identifier roles become eligible entity proposals.
        fresh = build_model(dataset)
        known = {tuple(e.keys) for e in model.entities}
        model.entities = (model.entities + [e for e in fresh.entities if tuple(e.keys) not in known])[:12]
        entity_ids = {e.id for e in model.entities}
        additions = [m for m in fresh.metrics if not m.entity or m.entity in entity_ids]
        metric_ids = {m.id for m in model.metrics} | {m.id for m in additions if m.aggregation != "ratio"}
        additions = [
            m for m in additions if m.aggregation != "ratio" or {m.numerator, m.denominator} <= metric_ids
        ]
        model.metrics = (model.metrics + [m for m in additions if m.id not in {v.id for v in model.metrics}])[
            :160
        ]
        model.time_policies = [t for t in model.time_policies if dataset.field(t.field).role == Role.TIME]
        model.time_policies += [
            t for t in fresh.time_policies if t.id not in {v.id for v in model.time_policies}
        ]
        time_ids = {t.id for t in model.time_policies}
        for metric in model.metrics:
            if metric.time_policy and metric.time_policy not in time_ids:
                metric.time_policy = None
        model.assertions = fresh.assertions + [a for a in model.assertions if a.origin == "human"][-200:]
        refresh_questions(model, dataset)
    return changed


def measures(dataset: Dataset) -> list[str]:
    return [f.id for f in dataset.record.fields if f.role == Role.MEASURE and not f.excluded]


def dimensions(dataset: Dataset) -> list[str]:
    return [
        f.id
        for f in dataset.record.fields
        if f.role in {Role.CATEGORY, Role.ORDINAL, Role.BOOL} and not f.excluded
    ]


def validate_semantic_review(dataset: Dataset, review: SemanticReview) -> list[dict]:
    """Validate each hypothesis in isolation, without changing active meaning or data."""
    records, seen = [], set()
    for suggestion in review.suggestions:
        if suggestion.field_id in seen or suggestion.field_id not in dataset.frame:
            continue
        seen.add(suggestion.field_id)
        table = semantic_table(dataset)
        mask = table.field == suggestion.field_id
        table.loc[mask, "role"] = suggestion.role.value
        if suggestion.role == Role.ORDINAL:
            table.loc[mask, "order"] = " | ".join(suggestion.ordered_levels)
        candidate = Dataset(dataset.record.model_copy(deep=True), dataset.frame)
        valid, reason = True, "Eligible unconfirmed hypothesis"
        try:
            apply_semantics(candidate, table)
        except ValueError as exc:
            valid, reason = False, str(exc)
        records.append({**suggestion.model_dump(mode="json"), "valid": valid, "validation": reason})
    return records
