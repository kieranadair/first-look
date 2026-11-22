"""Anchored cohort algebra and bounded, validated comparison bundles."""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from firstlook.contracts import clean, digest
from firstlook.discovery import analyze, plan_for
from firstlook.exploration_contracts import (
    CohortSelection,
    ComparisonBundle,
    ComparisonManifest,
    ComparisonSpec,
    ComparisonView,
)
from firstlook.numerics import cdf_distance
from firstlook.semantic.model import get_model
from firstlook.semantic.planner import metric_plan
from firstlook.semantics import dimensions, measures
from firstlook.visualization.compiler import axis_domains


def make_selection(
    ds,
    base,
    rows,
    source_result,
    mapping_hash,
    revision,
    policy="rows",
    entity=None,
    scope="Displayed mark members only",
):
    selected = sorted(set(int(i) for i in rows))
    if (
        not selected
        or not set(selected) <= set(base.row_ids)
        or base.id != ds.context(base.row_ids, base.focus, base.assumption).id
    ):
        raise ValueError("Select nonempty source members within the current anchored population.")
    members = selected
    if policy == "entities":
        keys = get_model(ds).entity(entity or "").keys
        frame = ds.frame.loc[base.row_ids]
        if frame.loc[selected, keys].isna().any().any():
            raise ValueError("Whole-entity selection needs recorded entity keys for every selected row.")
        wanted = set(frame.loc[selected, keys].itertuples(index=False, name=None))
        members = [
            int(i)
            for i, key in zip(frame.index, frame[keys].itertuples(index=False, name=None))
            if key in wanted
        ]
    return CohortSelection(
        base=base.model_copy(deep=True),
        source_result=source_result,
        mapping_hash=mapping_hash,
        selected_rows=selected,
        rows=sorted(members),
        policy=policy,
        entity=entity,
        revision=revision,
        selection_scope=scope,
    )


def preview(
    ws, rows, source_result, mapping_hash, policy="rows", entity=None, scope="Displayed mark members only"
):
    if ws.dataset is None or ws.replay:
        raise ValueError("Load an active dataset to preview a selection.")
    source = ws.investigation.results.get(source_result) if ws.investigation else None
    if source and source.metadata.get("definition", {}).get("aggregation") == "delta":
        raise ValueError(
            "Counter interval endpoints cannot be unioned into a row cohort; use an explicit recorded-row predicate instead."
        )
    selection = make_selection(
        ws.dataset,
        ws.context(),
        rows,
        source_result,
        mapping_hash,
        ws.cohort_revision + 1,
        policy,
        entity,
        scope,
    )
    ws.selection, ws.comparison = selection, None
    ws.cohort_revision = selection.revision
    return selection


def validate_bundle(bundle, ds=None):
    base = bundle.spec.selection.base
    selection = bundle.spec.selection
    selected, reference = set(selection.rows), set(bundle.spec.reference_rows)
    if (
        len(base.row_ids) != len(set(base.row_ids))
        or len(selection.selected_rows) != len(set(selection.selected_rows))
        or len(reference) != len(bundle.spec.reference_rows)
    ):
        raise ValueError("Comparison populations require distinct source-row identities.")
    if (
        len(selected) != len(selection.rows)
        or not selected
        or not selected <= set(base.row_ids)
        or not set(selection.selected_rows) <= selected
    ):
        raise ValueError("Invalid comparison cohort membership.")
    expected = set(base.row_ids) - selected if bundle.spec.reference == "remainder" else set(base.row_ids)
    if reference != expected or not reference:
        raise ValueError("The comparison reference does not match its declared base.")
    if {v.role for v in bundle.views} != {"Selected", "Reference"}:
        raise ValueError("Both named comparison roles are required.")
    for view in bundle.views:
        ctx = view.context
        if len(ctx.row_ids) != len(set(ctx.row_ids)):
            raise ValueError("A child context repeats source-row identities.")
        if (
            set(ctx.row_ids) != (selected if view.role == "Selected" else reference)
            or ctx.dataset != base.dataset
            or ctx.semantics != base.semantics
            or ctx.focus != base.focus
            or ctx.assumption != base.assumption
        ):
            raise ValueError("A child context is outside the declared comparison scope.")
        if (
            view.result.plan.context != ctx.id
            or view.finding.chart.context != ctx.id
            or view.finding.result_id != view.result.id
            or view.finding.chart.result_id != view.result.id
        ):
            raise ValueError("Mismatched comparison result/chart/context references.")
        if ds is not None and ctx.id != ds.context(ctx.row_ids, ctx.focus, ctx.assumption).id:
            raise ValueError("Comparison meanings or parsing no longer match the dataset.")
        if view.result.metadata.get("comparison_domains") != clean(bundle.manifest.domains):
            raise ValueError("The shared manifest and child encoding domains disagree.")
        plan = view.result.plan
        if plan.operation != bundle.spec.operation:
            raise ValueError("The child operation differs from the recorded comparison question.")
        if plan.operation == "metric" and (
            plan.params.get("metric") != bundle.spec.metric
            or plan.params.get("group_by") != bundle.spec.group_by
            or plan.params.get("denominator") != bundle.spec.denominator
            or plan.params.get("anchor") != base.model_dump(mode="json")
        ):
            raise ValueError(
                "The child metric, denominator or allocation reference differs from the comparison contract."
            )
        if plan.operation in {"ecdf", "frequency"} and plan.fields != [bundle.spec.measure]:
            raise ValueError("The child measure differs from the comparison contract.")
    for check in bundle.checks:
        parent = next((v for v in bundle.views if v.finding.id == check.parent_id), None)
        if (
            parent is None
            or (check.result and check.result.plan.context != parent.context.id)
            or (
                check.chart
                and (
                    check.result is None
                    or check.chart.result_id != check.result.id
                    or check.chart.context != parent.context.id
                )
            )
        ):
            raise ValueError("A comparison check has an invalid child context or result reference.")
    expected_id = digest([bundle.spec.model_dump(), bundle.manifest.model_dump()])
    if bundle.id != expected_id:
        raise ValueError("Comparison identity does not match its recorded definition.")


def build_comparison(
    ds,
    selection,
    operation,
    measure=None,
    metric=None,
    groups=None,
    reference="remainder",
    denominator="cohort",
    model=None,
):
    base = selection.base
    if operation != "metric" and denominator != "cohort":
        raise ValueError(
            "Cumulative proportions use their own nonmissing cohort; category frequency is a recorded count."
        )
    if base.id != ds.context(base.row_ids, base.focus, base.assumption).id:
        raise ValueError("This selection belongs to earlier meanings or data.")
    ref = sorted(set(base.row_ids) - set(selection.rows)) if reference == "remainder" else list(base.row_ids)
    if not ref:
        raise ValueError(
            "There is no reference remainder. Select fewer rows or compare with the whole population."
        )
    model_contract = get_model(ds)
    manifest = ComparisonManifest()
    groups = list(groups or [])
    if operation == "metric":
        definition = model_contract.metric(metric or "")
        if definition.aggregation in {"delta", "snapshot_last"} or definition.transform in {
            "zscore",
            "index",
            "percent_change",
        }:
            raise ValueError(
                "This cohort comparison does not support interval dependencies, snapshots or separately fitted transforms. Keep the original view or choose a scalar definition."
            )
        original, _ = analyze(ds, base, metric_plan(ds, base, metric, groups))
        fixed = [
            {"key": r["key"], "label": r["label"], "values": r["group_values"], "other": r["other"]}
            for r in original.records
        ]
        manifest.category_keys = [r["key"] for r in fixed]
        manifest.category_labels = [r["label"] for r in fixed]
        manifest.omitted_keys = original.metadata["omitted_keys"]
    elif operation == "ecdf":
        if measure not in measures(ds):
            raise ValueError("Choose a recorded measure for a distribution comparison.")
    elif operation == "frequency":
        if measure not in dimensions(ds):
            raise ValueError("Choose a categorical field for frequency comparison.")
        original, _ = analyze(
            ds, base, plan_for(base, "frequency", [str(measure)], "Reference category identities")
        )
        # Select the exact original named levels; Other membership stays anchored.
        levels = [r["label"] for r in original.records if not r.get("other")]
        fixed_remainder = any(r.get("other") for r in original.records)
        manifest.category_labels = [r["label"] for r in original.records]
    else:
        raise ValueError("Unsupported comparison operation.")
    views = []
    for role, rows in [("Selected", selection.rows), ("Reference", ref)]:
        ctx = ds.context(rows, base.focus, base.assumption)
        if operation == "metric":
            p = metric_plan(
                ds,
                ctx,
                metric,
                groups,
                fixed_groups=fixed,
                anchor=base.model_dump(mode="json"),
                denominator=denominator,
            )
        else:
            p = plan_for(
                ctx,
                operation,
                [str(measure)],
                f"{role}: {ds.label(measure)}",
                {"fixed_levels": levels, "fixed_remainder": fixed_remainder}
                if operation == "frequency"
                else None,
            )
        result, finding = analyze(ds, ctx, p)
        finding.chart.rules.append("EXP-COMP")
        result.metadata.update(
            comparison_role=role, comparison_color=manifest.colors[role], reference_population=base.id
        )
        views.append(ComparisonView(role=cast(Any, role), context=ctx, result=result, finding=finding))
    domains = [axis_domains(v.finding.chart, v.result) for v in views]
    for axis in {a for d in domains for a in d}:
        bounds = [d[axis] for d in domains if axis in d]
        manifest.domains[axis] = (min(d[0] for d in bounds), max(d[1] for d in bounds))
    for view in views:
        view.result.metadata["comparison_domains"] = clean(manifest.domains)
    overlap = None
    entity = selection.entity or (model_contract.metric(metric).entity if metric else None)
    if entity:
        keys = model_contract.entity(entity).keys
        left = set(ds.frame.loc[selection.rows, keys].dropna().itertuples(index=False, name=None))
        right = set(ds.frame.loc[ref, keys].dropna().itertuples(index=False, name=None))
        overlap = len(left & right)
    spec = ComparisonSpec(
        selection=selection,
        reference=reference,
        denominator=denominator,
        metric=metric,
        group_by=groups,
        measure=measure,
        operation=operation,
        reference_rows=ref,
        entity_overlap=overlap,
        row_overlap=len(set(selection.rows) & set(ref)),
    )
    summary = []
    exclusions = []
    if operation == "ecdf":
        arrays = [ds.frame.loc[v.context.row_ids, measure].dropna().to_numpy(dtype=float) for v in views]
        qa, qb = [np.quantile(a, manifest.quantile_grid) for a in arrays]
        summary = [
            {"quantile": q, "selected": float(a), "reference": float(b), "difference": float(a - b)}
            for q, a, b in zip(manifest.quantile_grid, qa, qb)
        ]
        exclusions.append(
            f"Full-source CDF distance: {cdf_distance(*arrays):.6g}; descriptive, not a population test."
        )
    elif operation == "metric":
        right = {r["key"]: r for r in views[1].result.records}
        for r in views[0].result.records:
            other = right[r["key"]]
            summary.append(
                {
                    "category": r["label"],
                    "selected": r["value"],
                    "reference": other["value"],
                    "difference": r["value"] - other["value"]
                    if r["value"] is not None and other["value"] is not None
                    else None,
                    "selected_valid_n": r["n"],
                    "reference_valid_n": other["n"],
                    "selected_members": r["member_rows"],
                    "reference_members": other["member_rows"],
                    "selected_denominator": r.get("denominator"),
                    "reference_denominator": other.get("denominator"),
                }
            )
    if overlap:
        exclusions.append(
            f"{overlap} entities occur in both populations. Disjoint rows are not necessarily independent entities."
        )
    if reference == "whole":
        exclusions.append("The selected cohort is included in the reference. These populations overlap.")
    model_slice = {}
    if model is not None:
        if model.context != base.id or set(model.train_ids) & set(model.test_ids):
            raise ValueError("The model run does not belong to this anchored context.")
        for role, rows in [("Selected", selection.rows), ("Reference", ref)]:
            ids = set(rows) & set(model.test_ids)
            predictions = [r for r in model.predictions if r["row_id"] in ids]
            model_slice[role] = {
                "heldout_rows": len(predictions),
                "row_ids": [r["row_id"] for r in predictions],
                "mean_recorded_error": float(np.mean([r["error"] for r in predictions]))
                if predictions
                else None,
            }
        model_slice.update(
            model_run=model.id,
            base_context=model.context,
            metric="MAE" if model.task == "regression" else "Error fraction",
            interpretation="Exploratory slice of the original recorded holdout; no refit or fresh validation",
        )
    bundle = ComparisonBundle(
        id=digest([spec.model_dump(), manifest.model_dump()]),
        spec=spec,
        manifest=manifest,
        views=views,
        summary=clean(summary),
        exclusions=exclusions,
        model_slice=clean(model_slice),
        dataset_record=ds.record.model_copy(deep=True),
        recorded_model=model.model_copy(deep=True) if model else None,
    )
    validate_bundle(bundle, ds)
    return bundle


def dataset_for_bundle(bundle, source):
    """Saved boards retain their own meanings and parse recipe, like standalone pins."""
    record = bundle.dataset_record
    if record is None:
        return source
    if record.fingerprint != source.record.fingerprint:
        raise ValueError("A comparison snapshot belongs to another source file.")
    from firstlook.ingest import Dataset, load_table
    from typing import Any, cast

    if source.raw is None:
        if source.frame.empty:
            import pandas as pd

            return Dataset(
                record.model_copy(deep=True),
                pd.DataFrame(columns=pd.Index([f.id for f in record.fields])),
                None,
            )
        if record.parser != source.record.parser:
            raise ValueError("The original bytes are needed for this saved parsing definition.")
        return Dataset(record.model_copy(deep=True), source.frame, None)
    ds = load_table(
        source.raw,
        "comparison-original.parquet" if source.raw.startswith(b"PAR1") else "comparison-original.csv",
        delimiter=str(record.parser.get("delimiter", ",")),
        encoding=str(record.parser.get("encoding", "utf-8-sig")),
        missing_tokens=cast(Any, record.parser.get("missing_tokens")),
    )
    if ds.record.rows != record.rows or ds.record.columns != record.columns:
        raise ValueError("A comparison's saved parsing dimensions do not match its source.")
    ds.record = record.model_copy(deep=True)
    from firstlook.semantic.model import validate_model

    if record.semantic_model:
        validate_model(ds, record.semantic_model)
    return ds


def validate_model_slice(bundle, models):
    if not bundle.model_slice:
        return
    run = next((m for m in models if m.id == bundle.model_slice.get("model_run")), bundle.recorded_model)
    if (
        run is None
        or run.context != bundle.spec.selection.base.id
        or bundle.model_slice.get("base_context") != run.context
        or set(run.train_ids) & set(run.test_ids)
        or not set(run.test_ids) <= set(bundle.spec.selection.base.row_ids)
    ):
        raise ValueError("A held-out comparison slice has no matching recorded model protocol.")
    for role, rows in [("Selected", bundle.spec.selection.rows), ("Reference", bundle.spec.reference_rows)]:
        saved = bundle.model_slice.get(role, {})
        ids = saved.get("row_ids", [])
        expected = {p["row_id"] for p in run.predictions if p["row_id"] in set(rows) & set(run.test_ids)}
        if len(ids) != len(set(ids)) or set(ids) != expected or saved.get("heldout_rows") != len(ids):
            raise ValueError("A held-out comparison slice has different test memberships.")
