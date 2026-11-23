"""Independent geometry, quantity-binding and native selection oracles."""

import pytest

from firstlook.contracts import AnalysisPlan, ChartSpec, ResultArtifact
from firstlook.visualization.compiler import (
    axis_domains,
    categorical_order,
    color_domain,
    compile_chart,
    encoded_records,
    heatmap_colors,
    selected_rows,
    series_colors,
)
from firstlook.visualization.layout import LEFT, RIGHT, TOP, chart_dimensions, plot_bottom


def view(template, records, *, metadata=None, metrics=None, params=None, zero=None, value_field="value"):
    plan = AnalysisPlan(
        id="result",
        operation="fixture",
        fields=["f000"],
        context="context",
        question="Known values",
        params=params or {},
    )
    result = ResultArtifact(
        id=plan.id,
        plan=plan,
        records=records,
        support=10,
        metadata=metadata or {},
        metrics=metrics or {},
    )
    spec = ChartSpec(
        id="chart",
        result_id=result.id,
        context=plan.context,
        template=template,
        x_label="X",
        y_label="Y",
        alt="Known fixture",
        zero_baseline=template in {"bar", "histogram", "facet"} if zero is None else zero,
        value_field=value_field,
    )
    return spec, result


def native_grid(options, actual_width):
    """Evaluate the documented ECharts merge rules, not a screenshot heuristic."""
    matched = [m for m in options["media"] if "query" in m and actual_width >= m["query"]["minWidth"]]
    chosen = matched or [m for m in options["media"] if "query" not in m]
    grid = dict(options["grid"])
    for media in chosen:
        grid.update(media["option"]["grid"])
    return grid


@pytest.mark.parametrize("requested_height", [280, 320, 370, 450])
def test_square_plot_area_survives_native_width_capping(requested_height):
    spec, result = view("scatter", [{"x": 10, "y": 1000, "row_id": 1}, {"x": 20, "y": 2000, "row_id": 2}])
    width, height = chart_dimensions(spec, result, requested_height)
    assert isinstance(width, int)
    compiled = compile_chart(spec, result, width=width, height=height)
    # Deliberately test widths between the media thresholds as well as above it.
    for actual_width in range(180, width + 40, 3):
        grid = native_grid(compiled.options, actual_width)
        assert grid["width"] == grid["height"] > 0
        assert grid["containLabel"] is False and grid["outerBoundsMode"] == "none"
        assert grid["left"] + grid["width"] + RIGHT <= actual_width
        assert grid["top"] + grid["height"] + plot_bottom("scatter") <= height
    assert width - LEFT - RIGHT == height - TOP - plot_bottom("scatter")
    # Square panel does not force unrelated quantities to have equal units.
    assert compiled.options["xAxis"]["max"] < compiled.options["yAxis"]["min"]


def test_identity_reference_has_equal_units_and_no_fake_selectable_members():
    spec, result = view(
        "scatter",
        [{"x": 10, "y": 95, "row_id": 3}, {"x": 20, "y": 105, "row_id": 4}],
        metadata={"reference": "identity"},
    )
    compiled = compile_chart(spec, result)
    domain = axis_domains(spec, result)
    assert domain["x"] == domain["y"]
    line = compiled.options["series"][0]["markLine"]
    assert line["silent"] and line["lineStyle"]["type"] == "dashed"
    points = line["data"][0]
    assert all(point["coord"][0] == point["coord"][1] for point in points)
    assert list(compiled.row_map.values()) == [[3], [4]]


def test_residual_reference_is_zero_even_when_every_error_is_positive():
    spec, result = view("scatter", [{"x": 10, "y": 2}, {"x": 20, "y": 4}], metadata={"reference": "zero"})
    compiled = compile_chart(spec, result)
    assert compiled.options["yAxis"]["min"] == 0
    assert compiled.options["series"][0]["markLine"]["data"] == [{"yAxis": 0, "name": "Zero residual"}]


def test_generic_dot_and_correlation_domains_are_different_contracts():
    spec, result = view("dot", [{"label": "A", "value": 100}, {"label": "B", "value": 150}])
    assert axis_domains(spec, result)["x"][0] > 1
    spec, result = view("dot", [{"label": "r", "value": 0.2}], metadata={"correlation": True})
    assert axis_domains(spec, result)["x"] == (-1, 1)


def test_every_facet_bar_has_zero_and_comparison_cannot_remove_it():
    spec, result = view(
        "facet",
        [
            {"facet": group, "label": label, "value": value}
            for group in ["A", "B", "C", "D"]
            for label, value in [("a", 4), ("b", 8)]
        ],
    )
    compiled = compile_chart(spec, result, height=420)
    assert len(compiled.options["grid"]) == 4
    assert all(axis["min"] == 0 for axis in compiled.options["xAxis"])
    assert compiled.options["grid"][0]["top"] == compiled.options["grid"][1]["top"]
    assert compiled.options["grid"][2]["top"] > compiled.options["grid"][0]["top"]
    result.metadata["comparison_domains"] = {"x": (2, 10)}
    with pytest.raises(ValueError, match="include zero"):
        compile_chart(spec, result)
    with pytest.raises(ValueError, match="zero baseline"):
        compile_chart(spec.model_copy(update={"zero_baseline": False}), result)


def histogram():
    return [
        {"x": 0.5, "left": 0.0, "right": 1.0, "value": 3, "row_ids": [1, 2, 3]},
        {"x": 1.5, "left": 1.0, "right": 2.0, "value": 1, "row_ids": [4]},
    ]


def test_histogram_bars_cover_recorded_intervals_and_keep_selection_membership():
    spec, result = view("histogram", histogram(), metrics={"median": 0.75, "q1": 0.3, "q3": 1.1})
    compiled = compile_chart(spec, result)
    series = compiled.options["series"][0]
    assert compiled.options["xAxis"]["type"] == "value"
    assert series["barWidth"] == "100%" and series["barCategoryGap"] == "0%"
    assert series["markLine"]["data"] == [{"xAxis": 0.75}]
    assert series["markArea"]["data"] == [[{"xAxis": 0.3}, {"xAxis": 1.1}]]
    assert compiled.options["xAxis"]["min"] <= 0 and compiled.options["xAxis"]["max"] >= 2
    assert selected_rows(
        {"selection": {"selected": [{"series_index": 0, "data_indices": [1]}]}}, compiled, {1, 2, 3, 4}
    ) == [4]
    # The single-bin fallback in ECharts is 80% of the numeric-axis span.
    one = result.model_copy(update={"records": histogram()[:1]})
    single = compile_chart(spec, one)
    span = single.options["xAxis"]["max"] - single.options["xAxis"]["min"]
    percent = float(single.options["series"][0]["barWidth"].rstrip("%"))
    assert 0.8 * span * percent / 100 == pytest.approx(1.0)


def test_frequency_polygon_is_recorded_midpoints_without_invented_zero_tails():
    spec, result = view("frequency_polygon", histogram())
    compiled = compile_chart(spec, result)
    assert compiled.options["series"][0]["type"] == "line"
    assert compiled.options["series"][0]["smooth"] is False
    assert len(compiled.options["dataset"][0]["source"]) == 2
    assert list(compiled.row_map.values()) == [[1, 2, 3], [4]]
    invalid = histogram()
    invalid[1].update(right=3.0, x=2.0)
    with pytest.raises(ValueError, match="equal-width"):
        compile_chart(spec, result.model_copy(update={"records": invalid}))


@pytest.mark.parametrize("problem", ["midpoint", "gap"])
def test_large_numeric_origin_does_not_hide_wrong_histogram_geometry(problem):
    base = 1_000_000_000_000.0
    rows = [
        {"x": base + 0.5, "left": base, "right": base + 1, "value": 2},
        {"x": base + 1.5, "left": base + 1, "right": base + 2, "value": 3},
    ]
    if problem == "midpoint":
        rows[0]["x"] = base + 0.25
    else:
        rows[1].update(x=base + 2.0, left=base + 1.5, right=base + 2.5)
    spec, result = view("histogram", rows)
    with pytest.raises(ValueError, match="midpoint|contiguous"):
        compile_chart(spec, result)


def test_group_frequency_polygons_keep_series_local_members_and_shared_bins():
    first = [{**row, "group": "Group 1"} for row in histogram()]
    second = [
        {**row, "group": "Group 3", "row_ids": [5 + i], "value": 0.5} for i, row in enumerate(histogram())
    ]
    spec, result = view("frequency_polygon", first + second)
    compiled = compile_chart(spec, result)
    lines = compiled.options["series"]
    assert len(lines) == 2 and all(line["type"] == "line" and line["smooth"] is False for line in lines)
    assert len({line["itemStyle"]["color"] for line in lines}) == 2
    assert compiled.row_map[0, 1] == [4] and compiled.row_map[1, 1] == [6]
    assert [frame["source"].x.tolist() for frame in compiled.options["dataset"]] == [[0.5, 1.5], [0.5, 1.5]]
    assert "markArea" not in lines[0] and "markLine" not in lines[0]
    shifted = [dict(row) for row in second]
    for row in shifted:
        row.update(x=row["x"] + 1, left=row["left"] + 1, right=row["right"] + 1)
    with pytest.raises(ValueError, match="same recorded bin"):
        compile_chart(spec, result.model_copy(update={"records": first + shifted}))


def test_quantile_difference_uses_quantile_domain_and_zero_reference():
    spec, result = view("quantile_difference", [{"x": 0.1, "value": 10}, {"x": 0.9, "value": 20}])
    compiled = compile_chart(spec, result)
    assert (compiled.options["xAxis"]["min"], compiled.options["xAxis"]["max"]) == (0, 1)
    assert compiled.options["yAxis"]["min"] == 0
    assert compiled.options["series"][0]["markLine"]["data"] == [{"yAxis": 0}]
    zeros = result.model_copy(update={"records": [{"x": 0.5, "value": 0}]})
    assert axis_domains(spec, zeros)["y"][0] < axis_domains(spec, zeros)["y"][1]
    mixed = result.model_copy(update={"records": [{"x": 0.1, "value": -5}, {"x": 0.9, "value": 2}]})
    # A boundary marker needs padding on both sides, even with zero included.
    assert axis_domains(spec, mixed)["y"][0] < -5
    assert axis_domains(spec, mixed)["y"][1] > 2


def test_signed_heatmap_has_symmetric_zero_colour_domain_and_explicit_order():
    records = [{"x": "B", "y": "late", "value": -4}, {"x": "A", "y": "early", "value": 2}]
    spec, result = view("heatmap", records, metadata={"normalization": "residual"})
    compiled = compile_chart(spec, result)
    assert color_domain(result) == (-4, 4)
    assert compiled.options["visualMap"]["min"] == -compiled.options["visualMap"]["max"]
    assert compiled.options["visualMap"]["inRange"]["color"] == heatmap_colors(result)
    assert compiled.options["xAxis"]["data"] == categorical_order(result, "x") == ["B", "A"]
    assert compiled.options["yAxis"]["data"] == ["late", "early"]
    assert compiled.options["yAxis"]["inverse"] is True
    assert compiled.options["visualMap"]["text"] == ["4", "-4"]


def test_density_uses_numeric_bin_indices_and_square_area_after_record_reordering():
    spec, result = view(
        "density",
        [{"x": 1, "y": 1, "value": 3, "row_ids": [3]}, {"x": 0, "y": 0, "value": 2, "row_ids": [2]}],
        metadata={"numeric_grid": {"x_edges": [10, 20, 30], "y_edges": [100, 200, 300]}},
    )
    width, height = chart_dimensions(spec, result, 300)
    compiled = compile_chart(spec, result, width=width, height=height)
    frame = compiled.options["dataset"][0]["source"]
    # Cell index one remains the upper/right bin, even when it is listed first.
    assert frame.iloc[0].x == frame.iloc[0].y == 1
    assert compiled.options["xAxis"]["data"] == ["10–20", "20–30"]
    for actual_width in [240, 300, width]:
        grid = native_grid(compiled.options, actual_width)
        assert grid["width"] == grid["height"]


def test_group_colours_survive_series_order_change():
    rows = [{"x": 1, "y": 1, "group": "North"}, {"x": 2, "y": 2, "group": "South"}]
    spec, result = view("scatter", rows)
    before = compile_chart(spec, result).options["series"]
    after = compile_chart(spec, result.model_copy(update={"records": rows[::-1]})).options["series"]
    assert {s["name"]: s["itemStyle"]["color"] for s in before} == {
        s["name"]: s["itemStyle"]["color"] for s in after
    }


@pytest.mark.parametrize("dark", [False, True])
def test_group_colour_collisions_are_resolved_and_declared_universe_survives_subsets(dark):
    # Group 1 and Group 3 collide in the original eight-slot label hash.
    rows = [{"x": i, "value": i + 1, "group": label} for i, label in enumerate(["Group 1", "Group 3"])]
    spec, result = view("line", rows, metadata={"series_order": ["Group 1", "Group 3"]})
    colors = series_colors(result, dark)
    assert len(set(colors.values())) == 2
    reversed_result = result.model_copy(update={"records": rows[::-1]})
    assert series_colors(reversed_result, dark) == colors
    subset = result.model_copy(update={"records": rows[1:]})
    assert series_colors(subset, dark) == colors
    assert compile_chart(spec, subset, dark).options["series"][0]["itemStyle"]["color"] == colors["Group 3"]
    eight = result.model_copy(
        update={
            "records": [{"x": i, "value": i + 1, "group": f"Group {i}"} for i in range(8)],
            "metadata": {},
        }
    )
    assert len(set(series_colors(eight, dark).values())) == 8


def concentration():
    rows = [
        {"label": "A", "key": "a", "amount": 8, "share": 0.8, "value": 0.8, "row_ids": [10]},
        {"label": "B", "key": "b", "amount": 2, "share": 0.2, "value": 1.0, "row_ids": [11]},
        {"label": "Zero", "key": "z", "amount": 0, "share": 0, "value": 1.0, "row_ids": [12]},
    ]
    spec, result = view(
        "treemap",
        rows,
        value_field="amount",
        metadata={
            "partwhole_verified": True,
            "full_original_parts": True,
            "definition": {"aggregation": "sum", "transform": "identity"},
        },
        metrics={"total": 10},
        params={"recipe": "concentration"},
    )
    result.plan.operation = "exploration"
    return spec, result


def test_treemap_encodes_original_amounts_and_accounts_for_native_virtual_root():
    spec, result = concentration()
    compiled = compile_chart(spec, result)
    assert [r["value"] for r in result.records] == [0.8, 1, 1]
    assert [r["value"] for r in encoded_records(spec, result)] == [8, 2, 0]
    assert [r["value"] for r in compiled.options["series"][0]["data"]] == [8, 2, 0]
    assert [r["id"] for r in compiled.options["series"][0]["data"]] == ["a", "b", "z"]
    assert compiled.row_map == {(0, 0): [], (0, 1): [10], (0, 2): [11], (0, 3): [12]}
    assert selected_rows(
        {"selection": {"selected": [{"series_index": 0, "data_indices": [2]}]}}, compiled, {10, 11, 12}
    ) == [11]
    with pytest.raises(ValueError, match="original amounts"):
        compile_chart(spec.model_copy(update={"value_field": "value"}), result)
    result.metadata["partwhole_verified"] = False
    with pytest.raises(ValueError, match="validated complete"):
        compile_chart(spec, result)


def test_amount_bars_and_long_category_scroller_keep_original_indices():
    spec, result = concentration()
    bars = spec.model_copy(update={"template": "bar", "zero_baseline": True})
    compiled = compile_chart(bars, result)
    assert compiled.options["xAxis"]["max"] >= 8
    spec, result = view("bar", [{"label": str(i), "value": 20 - i, "row_ids": [i]} for i in range(20)])
    compiled = compile_chart(spec, result, height=300)
    assert compiled.options["dataZoom"][0]["filterMode"] == "none"
    assert compiled.row_map[0, 19] == [19]
