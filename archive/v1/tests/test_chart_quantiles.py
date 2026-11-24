"""Independent numerical examples for the saved-quantile contrast display."""

from copy import deepcopy

import pytest

from firstlook.contracts import AnalysisPlan, ResultArtifact
from firstlook.visualization.quantiles import quantile_deviation


def parent_result():
    return ResultArtifact(
        id="saved-cumulative-view",
        plan=AnalysisPlan(
            id="saved-plan",
            operation="ecdf",
            fields=["measure"],
            context="saved-context",
            question="Distribution",
        ),
        # Deliberately unusable for deriving quantiles: only one compressed vertex.
        records=[{"x": 999.0, "value": 1.0, "row_ids": [17]}],
        support=240,
        missing=3,
        metadata={"unit": "kg", "ecdf_error": 0.02},
    )


def test_saved_shift_and_identical_quantiles_keep_exact_source_values():
    rows = [
        {"quantile": 0.0, "selected": 5.0, "reference": 2.0, "difference": 3.0},
        {"quantile": 0.5, "selected": 9.0, "reference": 6.0, "difference": 3.0},
        {"quantile": 1.0, "selected": 15.0, "reference": 12.0, "difference": 3.0},
    ]
    source = parent_result()
    derived, chart = quantile_deviation(source, rows)
    assert [r["value"] for r in derived.records] == [3.0, 3.0, 3.0]
    assert [r["x"] for r in derived.records] == [0.0, 0.5, 1.0]
    assert derived.support == 240 and derived.missing == 3
    assert derived.plan.context == chart.context == "saved-context"
    assert derived.plan.operation == "quantile_deviation_display"
    assert derived.metadata["derived_from"] == source.id
    assert derived.metadata["reference"] == "zero" and derived.metadata["display_only"]
    assert chart.template == "quantile_difference" and chart.zero_baseline
    assert chart.y_label == "Selected − Reference (kg)"
    assert all("row_ids" not in row and "row_id" not in row for row in derived.records)
    assert "chosen percentiles" in chart.alt and "matched records" in chart.alt
    from firstlook.visualization.review_assets import render_asset

    asset = render_asset(derived, chart)
    assert asset.records == derived.records
    assert asset.manifest["axis_domains"]["x"] == (0.0, 1.0)
    assert asset.manifest["reference"] == "zero" and not asset.manifest["sampled"]

    identical = [{**row, "selected": row["reference"], "difference": 0.0} for row in rows]
    zero, _ = quantile_deviation(source, identical)
    assert [r["value"] for r in zero.records] == [0.0, 0.0, 0.0]
    assert zero.id != derived.id


def test_group_quantiles_show_shape_changes_and_ties_without_mutating_parents():
    source = parent_result()
    rows = [
        {"quantile": 0.1, "first": 1.0, "second": 3.0, "difference": -2.0},
        {"quantile": 0.25, "first": 1.0, "second": 3.0, "difference": -2.0},
        {"quantile": 0.5, "first": 4.0, "second": 4.0, "difference": 0.0},
        {"quantile": 0.9, "first": 11.0, "second": 7.0, "difference": 4.0},
    ]
    original_source, original_rows = source.model_dump(mode="json"), deepcopy(rows)
    derived, chart = quantile_deviation(source, rows, "A", "B")
    assert [r["value"] for r in derived.records] == [-2.0, -2.0, 0.0, 4.0]
    assert [r["first"] for r in derived.records] == [1.0, 1.0, 4.0, 11.0]
    assert source.model_dump(mode="json") == original_source and rows == original_rows
    repeated, _ = quantile_deviation(source, rows, "A", "B")
    assert repeated.id == derived.id
    relabelled, _ = quantile_deviation(source, rows, "B", "A")
    assert relabelled.id != derived.id
    assert chart.y_label == "A − B (kg)"
    derived.records[0]["first"] = 0
    assert rows == original_rows


def test_tolerated_float_roundoff_preserves_the_stored_difference():
    rows = [{"quantile": 0.5, "first": 0.3, "second": 0.2, "difference": 0.1}]
    result, _ = quantile_deviation(parent_result(), rows)
    assert result.records[0]["value"] == 0.1
    assert result.records[0]["value"] != 0.3 - 0.2


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"quantile": float("nan"), "first": 1, "second": 0, "difference": 1}],
        [{"quantile": 1.1, "first": 1, "second": 0, "difference": 1}],
        [{"quantile": -0.1, "first": 1, "second": 0, "difference": 1}],
        [{"quantile": "0.5", "first": 1, "second": 0, "difference": 1}],
        [{"quantile": True, "first": 1, "second": 0, "difference": 1}],
        [{"quantile": 0.5, "first": float("inf"), "second": 0, "difference": 1}],
        [{"quantile": 0.5, "first": 1, "second": 0, "difference": float("inf")}],
        [{"quantile": 0.5, "first": 5, "second": 2, "difference": -3}],
        [{"quantile": 0.5, "first": 5, "difference": 3}],
        [
            {"quantile": 0.5, "first": 1, "second": 0, "difference": 1},
            {"quantile": 0.5, "first": 2, "second": 0, "difference": 2},
        ],
        [
            {"quantile": 0.75, "first": 1, "second": 0, "difference": 1},
            {"quantile": 0.25, "first": 2, "second": 0, "difference": 2},
        ],
    ],
)
def test_invalid_saved_quantile_tables_are_rejected(rows):
    with pytest.raises(ValueError):
        quantile_deviation(parent_result(), rows)
