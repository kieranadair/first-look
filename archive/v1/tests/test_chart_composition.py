"""Known-area and eligibility oracles, independent of either rendering engine."""

import copy

import pytest

from firstlook.contracts import AnalysisPlan, ChartSpec, ResultArtifact
from firstlook.visualization.composition import amount_records, treemap_rectangles


def source():
    return ResultArtifact(
        id="parts",
        plan=AnalysisPlan(
            id="parts",
            operation="exploration",
            fields=["category", "amount"],
            context="context",
            question="Contribution",
            params={"recipe": "concentration"},
        ),
        support=4,
        metrics={"total": 100},
        records=[
            {
                "label": label,
                "key": label,
                "amount": amount,
                "share": amount / 100,
                "value": cumulative,
                "row_ids": [i],
            }
            for i, (label, amount, cumulative) in enumerate(
                [("A", 60, 0.6), ("B", 30, 0.9), ("C", 10, 1.0), ("D", 0, 1.0)]
            )
        ],
        metadata={
            "partwhole_verified": True,
            "full_original_parts": True,
            "definition": {"aggregation": "sum", "transform": "identity"},
        },
    )


def test_amount_binding_preserves_the_original_cumulative_evidence_and_all_members():
    result = source()
    before = copy.deepcopy(result.model_dump())
    parts = amount_records(result)
    assert [r["value"] for r in parts] == [60, 30, 10, 0]
    assert sum(r["value"] for r in parts) == result.metrics["total"]
    assert [r["cumulative_share"] for r in parts] == [0.6, 0.9, 1, 1]
    assert [r["row_ids"] for r in parts] == [[0], [1], [2], [3]]
    assert result.model_dump() == before


def test_review_treemap_uses_original_amounts_and_preserves_zero_parts():
    from firstlook.visualization.review_assets import render_asset

    result = source()
    chart = ChartSpec(
        id="treemap",
        result_id=result.id,
        context=result.plan.context,
        template="treemap",
        value_field="amount",
        x_label="Contribution",
        y_label="Part",
        alt="Validated contribution amounts",
    )
    original = copy.deepcopy(result.model_dump())
    asset = render_asset(result, chart)
    assert [row["value"] for row in asset.records] == [60, 30, 10, 0]
    assert [row["cumulative_share"] for row in asset.records] == [0.6, 0.9, 1, 1]
    assert asset.manifest["value_field"] == "amount" and not asset.manifest["sampled"]
    assert result.model_dump() == original


@pytest.mark.parametrize(
    "fault", ["unproved", "partial", "mean", "transformed", "negative", "wrong_total", "wrong_share", "other"]
)
def test_area_rejects_invalid_or_unproved_part_whole_quantities(fault):
    r = source()
    if fault == "unproved":
        r.metadata.pop("partwhole_verified")
    elif fault == "partial":
        r.missing = 1
    elif fault == "mean":
        r.metadata["definition"]["aggregation"] = "mean"
    elif fault == "transformed":
        r.metadata["definition"]["transform"] = "log"
    elif fault == "negative":
        r.records[0]["amount"] = -60
    elif fault == "wrong_total":
        r.metrics["total"] = 200
    elif fault == "wrong_share":
        r.records[0]["share"] = 0.7
    elif fault == "other":
        r.records[0]["other"] = True
    with pytest.raises(ValueError):
        amount_records(r)


def test_rectangle_areas_match_exact_parts_without_overlap_or_inventing_zero_area():
    values = [60, 30, 10, 0]
    boxes = treemap_rectangles(values)
    for value, (x, y, w, h) in zip(values, boxes):
        assert w * h == pytest.approx(value / 100)
        assert 0 <= x <= x + w <= 1 and 0 <= y <= y + h <= 1
    for i, (x, y, w, h) in enumerate(boxes):
        for a, b, c, d in boxes[i + 1 :]:
            overlap = max(0, min(x + w, a + c) - max(x, a)) * max(0, min(y + h, b + d) - max(y, b))
            assert overlap == pytest.approx(0, abs=1e-12)
    assert sum(w * h for _, _, w, h in boxes) == pytest.approx(1)
