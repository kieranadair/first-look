"""Compile metric intent and observed structure into executable preconditions."""

from __future__ import annotations
from functools import lru_cache
import pandas as pd
from pint.errors import PintError
from firstlook.contracts import Role
from firstlook.semantic_contracts import Metric, OperationDecision
from firstlook.semantic.model import get_model


@lru_cache(maxsize=1)
def unit_registry():
    from pint import UnitRegistry

    return UnitRegistry()


def decision(
    dataset, metric: Metric, group_by: list[str], time_field: str | None = None, rows=None, _seen=None
) -> OperationDecision:
    model = get_model(dataset)
    reasons, requirements, warnings = [], [], []
    fields = set(dataset.frame.columns)
    if len(group_by) > 2 or len(set(group_by)) != len(group_by) or not set(group_by) <= fields:
        reasons.append("Choose at most two distinct recorded grouping fields.")
        return OperationDecision(status="disallowed", reasons=reasons, rules=["SEM-VALID"])
    if any(dataset.field(f).excluded for f in group_by):
        reasons.append("An excluded field cannot be a grouping field.")
    if any(dataset.field(f).role not in {Role.CATEGORY, Role.ORDINAL, Role.BOOL, Role.ID} for f in group_by):
        reasons.append(
            "Grouping fields require categorical, ordered or identifier meaning; numeric bins must be explicit."
        )
    frame = dataset.frame if rows is None else dataset.frame.loc[rows]
    if time_field and (time_field not in fields or dataset.field(time_field).role != Role.TIME):
        reasons.append("A time view requires a timestamp role.")
    if metric.field:
        if metric.field not in fields:
            reasons.append("Unknown value field.")
        elif dataset.field(metric.field).excluded or dataset.field(metric.field).role != Role.MEASURE:
            reasons.append("A value metric requires a permitted measure, not an identifier or category code.")
    if reasons:
        return OperationDecision(status="disallowed", reasons=reasons, rules=["SEM-VALID"])
    meaning = model.meaning(metric.field) if metric.field else None
    if metric.field and metric.aggregation in {"sum", "mean", "average_per_entity"}:
        repeated = [
            e
            for e in model.entities
            if any(
                a.subject == metric.field
                and a.property == "constant_within_" + e.id
                and a.origin == "computed"
                and a.value is True
                for a in model.assertions
            )
        ]
        if repeated and not metric.entity:
            warnings.append(
                "Values are recorded as constant within "
                + ", ".join(e.label for e in repeated[:2])
                + ". If they are repeated entity amounts, row weighting or row sums can double-count them. Equality alone does not prove the value grain."
            )
        if metric.aggregation == "average_per_entity" and any(e.id == metric.entity for e in repeated):
            warnings.append(
                "This value is constant within the repeated denominator entity. If it is an entity amount repeated on its rows, choose a mean at that value entity instead of summing row amounts per entity."
            )
    if (
        metric.aggregation
        in {"sum", "average_per_entity", "weighted_mean", "snapshot_last", "delta", "circular_mean", "ratio"}
        and not metric.confirmed
    ):
        requirements.append("Confirm the metric definition, value grain and denominator/exposure in Meaning.")
    if (
        meaning
        and meaning.kind in {"circular", "coordinate"}
        and metric.aggregation in {"sum", "mean", "median", "weighted_mean"}
    ):
        reasons.append(
            "Linear summaries do not preserve circular or coordinate geometry. Use an explicitly supported domain summary."
        )
    if metric.aggregation == "ratio":
        seen = set(_seen or [])
        if metric.id in seen:
            return OperationDecision(status="disallowed", reasons=["Circular metric definition."])
        seen.add(metric.id)
        for index, mid in enumerate([metric.numerator, metric.denominator]):
            try:
                child = model.metric(mid or "")
            except ValueError as exc:
                reasons.append(str(exc))
                continue
            child_groups = [] if index == 1 and metric.denominator_scope == "active_population" else group_by
            check = decision(dataset, child, child_groups, time_field, rows, seen)
            reasons += check.reasons
            requirements += check.requirements
            warnings += check.warnings
    if meaning and metric.aggregation in {"sum", "average_per_entity"}:
        if meaning.kind in {
            "state",
            "rate",
            "ratio",
            "temperature",
            "cumulative",
            "circular",
            "coordinate",
            "composition",
            "index",
        }:
            reasons.append(
                "This quantity is not additive over recorded rows. Choose a snapshot, weighted mean, ratio, counter difference or other explicit definition."
            )
        elif not meaning.confirmed or meaning.kind not in {"flow", "amount", "count"}:
            requirements.append(
                "Confirm whether "
                + dataset.label(metric.field)
                + " is an additive amount/flow/count in Meaning."
            )
        elif meaning.kind == "count" and (frame[metric.field].dropna() < 0).any():
            reasons.append(
                "A declared count contains negative values. Resolve whether these are signed changes or invalid observations before totaling it."
            )
    if (
        meaning
        and metric.aggregation == "circular_mean"
        and (meaning.kind != "circular" or not meaning.confirmed)
    ):
        requirements.append("Confirm a circular quantity in degrees before using a circular mean.")
    if (
        meaning
        and metric.aggregation == "circular_mean"
        and meaning.unit.casefold() not in {"degree", "degrees", "deg", "°"}
    ):
        requirements.append(
            "The supported circular mean requires an explicitly declared degree unit; implicit angle-unit conversion is not applied."
        )
    if metric.entity:
        try:
            entity = model.entity(metric.entity)
        except ValueError as exc:
            return OperationDecision(status="disallowed", reasons=[str(exc)])
        if frame[entity.keys].isna().any().any():
            warnings.append("Rows with missing entity identity are excluded from entity metrics.")
        if any(dataset.field(fid).excluded for fid in entity.keys):
            reasons.append("An entity metric depends on an excluded identity field.")
        if metric.aggregation in {"sum", "mean", "median", "weighted_mean"}:
            grouped = frame.dropna(subset=entity.keys).groupby(entity.keys, dropna=False)
            if metric.field and grouped[metric.field].nunique(dropna=False).max() > 1:
                reasons.append(
                    "The value is not constant within the declared value entity. Choose the correct value grain."
                )
            if metric.weight and grouped[metric.weight].nunique(dropna=False).max() > 1:
                reasons.append("The weight is not constant within the declared value entity.")
        if metric.aggregation == "sum" and group_by:
            memberships = frame.dropna(subset=entity.keys + group_by).drop_duplicates(entity.keys + group_by)
            if (
                memberships.groupby(entity.keys, dropna=False).size() > 1
            ).any() and metric.allocation == "none":
                reasons.append(
                    "The value entity belongs to overlapping groups. Declare full-credit or equal allocation before totaling by these groups."
                )
    elif metric.aggregation in {"count_distinct", "average_per_entity", "snapshot_last", "delta"}:
        reasons.append("An explicit entity is required for this metric.")
    if metric.aggregation == "weighted_mean":
        if (
            not metric.weight
            or metric.weight not in fields
            or dataset.field(metric.weight).excluded
            or dataset.field(metric.weight).role != Role.MEASURE
            or not pd.api.types.is_numeric_dtype(frame[metric.weight])
        ):
            reasons.append("Choose a permitted numeric weight field.")
        elif (frame[metric.weight].dropna() < 0).any():
            reasons.append("Weights must be nonnegative; their meaning must be explicitly declared.")
    if metric.aggregation in {"snapshot_last", "delta"}:
        if not time_field:
            reasons.append("Snapshot and counter metrics require a time view.")
        if not meaning or not meaning.confirmed:
            requirements.append("Confirm the quantity meaning before interpreting observations over time.")
        elif metric.aggregation == "snapshot_last" and meaning.kind != "state":
            reasons.append("A last-snapshot metric requires a state quantity.")
        elif metric.aggregation == "delta" and meaning.kind != "cumulative":
            reasons.append("Counter differences require a cumulative quantity.")
    if meaning and metric.transform != "identity" and metric.transform not in meaning.allowed_transforms:
        requirements.append("Explicitly permit this transformation for the quantity in Meaning.")
    if metric.transform in {"difference", "percent_change"} and not time_field:
        reasons.append("Change transformations require an ordered time view.")
    if metric.transform == "log" and meaning and meaning.unit:
        try:
            registry = unit_registry()
            unit = registry.Unit(meaning.unit)
            # Celsius/Fahrenheit have offsets; ratios/logs depend on the reference origin.
            if registry.Quantity(0, unit).to_base_units().magnitude != 0:
                reasons.append("A logarithm of an offset quantity needs an explicit reference construction.")
        except (ValueError, TypeError, KeyError, PintError):
            requirements.append("Resolve the unit before applying a logarithm.")
    if meaning and meaning.currency and not meaning.basis:
        warnings.append(
            "Currency is declared but conversion/inflation basis is unspecified; comparisons remain as recorded."
        )
    if metric.aggregation in {"mean", "median"} and not metric.entity:
        warnings.append(
            "Each nonmissing recorded row is an observation; this is not an entity-level or duration-weighted summary."
        )
    if reasons:
        return OperationDecision(
            status="disallowed",
            reasons=list(dict.fromkeys(reasons)),
            warnings=list(dict.fromkeys(warnings)),
            rules=["SEM-VALID", "SEM-GRAIN", "SEM-AGG"],
        )
    if requirements:
        return OperationDecision(
            status="conditional",
            requirements=list(dict.fromkeys(requirements)),
            warnings=list(dict.fromkeys(warnings)),
            rules=["SEM-MEANING"],
        )
    return OperationDecision(
        status="allowed",
        warnings=list(dict.fromkeys(warnings)),
        rules=["SEM-VALID", "SEM-GRAIN", "SEM-AGG", "SEM-SCOPE"],
    )
