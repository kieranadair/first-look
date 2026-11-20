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
