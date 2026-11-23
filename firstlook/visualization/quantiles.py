"""Display saved quantile contrasts without treating them as paired observations."""

from __future__ import annotations

import math
from numbers import Real

from firstlook.contracts import AnalysisPlan, ChartSpec, ResultArtifact, digest


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    return float(value)


def quantile_deviation(
    result: ResultArtifact,
    rows: list[dict],
    first_label: str = "Selected",
    second_label: str = "Reference",
) -> tuple[ResultArtifact, ChartSpec]:
    """Turn an existing full-source quantile table into a display-only contrast.

    ``rows`` must contain the recorded matched estimates, using either the
    comparison-board or two-group-shape schema. Their stored differences are
    retained, not recalculated from compressed curve vertices. Support and
    missingness describe the parent artifact; callers retain responsibility for
    displaying each comparison population's separate counts.
    """
    if not rows:
        raise ValueError("A quantile deviation display needs recorded quantiles.")
    if not first_label.strip() or not second_label.strip():
        raise ValueError("Both quantile populations need a label.")

    records = []
    previous = -math.inf
    for row in rows:
        try:
            quantile = _finite_number(row["quantile"], "Quantile")
            first_key, second_key = (
                ("selected", "reference") if "selected" in row or "reference" in row else ("first", "second")
            )
            first = _finite_number(row[first_key], "First quantile estimate")
            second = _finite_number(row[second_key], "Second quantile estimate")
            difference = _finite_number(row["difference"], "Quantile difference")
        except KeyError as exc:
            raise ValueError(
                "Each row needs a percentile, two matched estimates and their difference."
            ) from exc
        if not 0 <= quantile <= 1 or quantile <= previous:
            raise ValueError("Quantiles must be distinct, increasing and within [0, 1].")
        expected = first - second
        if not math.isfinite(expected) or not math.isclose(
            difference, expected, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("The saved difference must equal the first quantile minus the second.")
        records.append({"x": quantile, "value": difference, "first": first, "second": second})
        previous = quantile

    units = next(
        (
            value
            for key in ("units", "unit")
            if isinstance(value := result.metadata.get(key), str) and value.strip()
        ),
        "",
    )
    identity = digest(
        ["quantile_deviation_display", result.id, result.plan.context, records, first_label, second_label]
    )
    plan = AnalysisPlan(
        id=identity,
        operation="quantile_deviation_display",
        fields=list(result.plan.fields),
        context=result.plan.context,
        question=f"How do the recorded quantiles of {first_label} and {second_label} differ?",
        params={"source_result_id": result.id, "display_only": True},
    )
    derived = ResultArtifact(
        id=identity,
        plan=plan,
        records=records,
        support=result.support,
        missing=result.missing,
        metrics={"displayed_quantiles": len(records)},
        warnings=[
            "Differences are shown only at the saved percentiles. They do not describe paired-record changes or an inferential interval."
        ],
        metadata={
            "derived_from": result.id,
            "source_result_id": result.id,
            "display_only": True,
            "estimator": "linear; full source values",
            "quantile_grid": [row["x"] for row in records],
            "display_interpolation": "none; markers at the saved percentiles only",
            "reference": "zero",
            "first_label": first_label,
            "second_label": second_label,
            "units": units,
            "selection_semantics": "Summary quantiles have no source-row membership.",
        },
    )
    chart = ChartSpec(
        id=digest([identity, "quantile_difference", units]),
        result_id=identity,
        context=result.plan.context,
        template="quantile_difference",
        x_label="Quantile probability (0–1)",
        y_label=f"{first_label} − {second_label}" + (f" ({units})" if units else ""),
        units=units,
        zero_baseline=True,
        rules=["VALID-01", "SOURCE-01", "SUPPORT-01", "SCALE-01", "EXP-SHAPE"],
        alt=(
            f"{first_label} minus {second_label} quantile estimates at {len(records)} chosen percentiles. "
            "The horizontal zero reference means equal quantiles. Markers show only the saved percentiles, "
            "not differences throughout the full continuous distribution or changes in matched records."
        ),
    )
    return derived, chart
