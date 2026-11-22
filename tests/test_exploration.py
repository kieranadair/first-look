"""Known-answer and metamorphic cases for exploration; no providers or image capture."""

from bisect import bisect_right
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from firstlook.comparison import build_comparison, make_selection, preview, validate_bundle
from firstlook.contracts import Role
from firstlook.discovery import Investigation, analyze, discover, plan_for
from firstlook.evidence import export_bundle, import_bundle, recompute
from firstlook.ingest import from_frame
from firstlook.modeling import eligible_targets
from firstlook.numerics import compressed_ecdf, cdf_distance
from firstlook.semantic.model import add_metric, commit_model, configure_meaning, get_model
from firstlook.semantic.planner import metric_plan
from firstlook.semantic.profile import build_model
from firstlook.semantic_contracts import Entity, Metric, TimePolicy
from firstlook.state import Workspace
from firstlook.visualization.compiler import axis_domains, compile_chart, selected_rows
from firstlook.visualization.review_assets import render_asset


def data(frame):
    ds = from_frame(frame, "fixture.csv", raw=frame.to_csv(index=False).encode())
    for f in ds.record.fields:
        if pd.api.types.is_numeric_dtype(ds.frame[f.id]):
            f.role = Role.MEASURE
    ds.record.semantic_model = build_model(ds)
    return ds


def total(ds, field="f001", mid="amount"):
    configure_meaning(ds, field, "flow")
    add_metric(ds, Metric(id=mid, label=mid, aggregation="sum", field=field, confirmed=True))
    return mid


def recipe(ds, name, fields, **params):
    ctx = ds.context()
    return analyze(ds, ctx, plan_for(ctx, "exploration", fields, name, {"recipe": name, **params}))


@pytest.mark.parametrize("distinct", [1199, 1200, 1201, 5000])
def test_cdf_bound_uses_independent_threshold_oracle(distinct):
    original = list(range(distinct)) + [distinct - 2] * 1000
    x, p, bound, _ = compressed_ecdf(original)
    errors = []
    original.sort()
    for threshold in set(original):
        position = bisect_right(x, threshold) - 1
        displayed = p[position] if position >= 0 else 0
        errors.append(abs(bisect_right(original, threshold) / len(original) - displayed))
    assert bound == pytest.approx(max(errors))
    assert len(x) <= 1200 and x[0] == 0 and x[-1] == distinct - 1
    assert np.all(np.diff(p) >= 0) and p[-1] == 1


def test_high_mass_tie_is_retained_and_error_is_small():
    values = list(range(1201)) + [1199] * 48799
    x, p, error, _ = compressed_ecdf(values)
    assert 1199 in x and error < 0.001
    assert p[list(x).index(1199)] == pytest.approx(0.99998)


def test_source_cdf_distance_and_unit_invariance():
    a, b = [0, 0, 0, 10], [0, 5, 5, 5]
    expected = max(abs(sum(v <= t for v in a) / 4 - sum(v <= t for v in b) / 4) for t in set(a + b))
    assert cdf_distance(a, b) == expected
    assert cdf_distance(np.array(a) * 17 + 2, np.array(b) * 17 + 2) == expected
    assert cdf_distance(b, a) == expected


def test_metric_rank_follows_value_not_row_frequency():
    ds = data(
        pd.DataFrame(
            {
                "category": ["Frequent"] * 40 + ["Medium"] * 4 + ["Rare"],
                "amount": [1] * 40 + [10] * 4 + [1000],
            }
        )
    )
    mid = total(ds)
    r, _ = analyze(ds, ds.context(), metric_plan(ds, ds.context(), mid, ["f000"], limit=2))
    assert [(v["label"], v["value"]) for v in r.records] == [("Rare", 1000), ("Other recorded groups", 80)]
    assert len(set(v["key"] for v in r.records)) == 2


def test_display_scope_distinguishes_statistics_and_marks():
    ds = data(pd.DataFrame({"x": np.arange(6000), "y": np.arange(6000) ** 2}))
    r, f = analyze(ds, ds.context(), plan_for(ds.context(), "relationship", ["f000", "f001"], "pairs"))
    assert r.metadata["analysis_scope"]["statistical_rows"] == 6000
    assert r.metadata["analysis_scope"]["displayed_marks"] == 5000 and r.metadata["sampled"]
    assert r.warnings and compile_chart(f.chart, r).options["xAxis"]["min"] <= 0


def test_variance_only_structure_is_proposed_and_quartiles_are_rendered():
    x = np.repeat(np.arange(1, 201), 2)
    ds = data(pd.DataFrame({"x": x, "y": x * np.tile([-1, 1], 200)}))
    inv = discover(ds)
    f = next(f for f in inv.findings if f.family == "quantile_bin_summary")
    result = inv.results[f.result_id]
    assert [r["value"] for r in result.records] == [0] * 5
    assert [r["q3"] - r["q1"] for r in result.records] == [40.5, 120.5, 200.5, 280.5, 360.5]
    assert len(compile_chart(f.chart, result).options["series"]) == 3


def test_explicit_focus_is_applied_before_numeric_field_cap():
    rng = np.random.default_rng(31)
    frame = pd.DataFrame(rng.normal(size=(200, 45)), columns=[f"v{i}" for i in range(45)])
    frame["v44"] = frame["v0"] * 3
    ds = data(frame)
    inv = discover(ds, ds.context(focus="f044"))
    assert any(
        r.get("fields") == ["f000", "f044"] or r.get("fields") == ["f044", "f000"] for r in inv.candidate_log
    )
    assert next(r for r in inv.coverage if r["family"] == "Numeric relationships")["outside_budget"] > 0


def test_group_comparison_uses_full_cdf_and_quantile_values():
    ds = data(
        pd.DataFrame(
            {"group": ["A"] * 100 + ["B"] * 100, "value": list(range(100)) + list(np.arange(100) * 2)}
        )
    )
    r, f = recipe(ds, "group_shape", ["f000", "f001"], levels=["A", "B"])
    assert r.metrics["cdf_distance"] == cdf_distance(range(100), np.arange(100) * 2)
    assert r.metrics["quantiles"][2]["difference"] == -49.5
    assert len(compile_chart(f.chart, r).options["series"]) == 2
    reversed_result, _ = recipe(ds, "group_shape", ["f000", "f001"], levels=["B", "A"])
    assert reversed_result.metrics["quantiles"][2]["difference"] == 49.5


@pytest.mark.parametrize("mode", ["count", "whole", "within_x", "within_y", "residual"])
def test_crosstab_denominators_are_independent_known_answers(mode):
    pairs = [("A", "C")] * 10 + [("A", "D")] * 30 + [("B", "C")] * 20 + [("B", "D")] * 40 + [(None, "D")]
    ds = data(pd.DataFrame(pairs, columns=["first", "second"]))
    r, f = analyze(
        ds,
        ds.context(),
        plan_for(ds.context(), "category_relationship", ["f000", "f001"], mode, {"normalization": mode}),
    )
    first = r.records[0]
    denominator = {"count": 1, "whole": 100, "within_x": 40, "within_y": 30, "residual": 1}[mode]
    expected = (10 - 12) / np.sqrt(12) if mode == "residual" else 10 / denominator
    assert first["value"] == pytest.approx(expected) and first["denominator"] == denominator
    assert r.support == 100 and r.missing == 1
    assert len(render_asset(r, f.chart).records) == 4


def test_density_counts_every_pair_and_preserves_complete_cells():
    ds = data(pd.DataFrame({"x": [0, 0, 1, 2, 3] * 10, "y": [0, 1, 1, 2, 3] * 10}))
    r, f = recipe(ds, "density", ["f000", "f001"], bins=4)
    assert len(r.records) == 16 and sum(c["value"] for c in r.records) == 50
    assert sorted(i for c in r.records for i in c["row_ids"]) == list(range(50))
    assert len(compile_chart(f.chart, r).options["dataset"][0]["source"]) == 16
    assert len(render_asset(r, f.chart).records) == 16
    with pytest.raises(ValueError, match="complete"):
        render_asset(r, f.chart, max_points=8)


def test_influence_keeps_all_rows_and_reports_model_specific_diagnostic():
    x = np.arange(50)
    y = x + np.sin(x)
    y[-1] += 100
    ds = data(pd.DataFrame({"x": x, "y": y}))
    r, _ = recipe(ds, "influence", ["f000", "f001"])
    assert r.metrics["largest_influence_row"] == 49
    assert r.support == 50 and len(ds.frame) == 50
    assert len({row["row_id"] for row in r.records}) == 50


def test_histogram_sensitivity_preserves_observation_memberships():
    ds = data(pd.DataFrame({"x": np.arange(100)}))
    r, _ = recipe(ds, "histogram_sensitivity", ["f000"], bins=10, origin=0.5)
    assert sum(v["value"] for v in r.records) == 100
    assert sorted(i for v in r.records for i in v["row_ids"]) == list(range(100))


def test_concentration_is_over_original_nonnegative_parts():
    ds = data(pd.DataFrame({"category": ["A", "B", "C"], "amount": [60, 30, 10]}))
    mid = total(ds)
    r, _ = recipe(ds, "concentration", ["f000", "f001"], metric=mid, groups=["f000"])
    assert [v["value"] for v in r.records] == [0.6, 0.9, 1]
    assert r.metrics["original_parts"] == 3
    ds.frame.loc[0, "f001"] = -60
    with pytest.raises(ValueError, match="nonnegative"):
        recipe(ds, "concentration", ["f000", "f001"], metric=mid, groups=["f000"])


def test_facets_have_a_complete_grid_and_shared_domain():
    ds = data(pd.DataFrame({"facet": ["A", "A", "B"], "item": ["X", "Y", "X"], "value": [1, 2, 5]}))
    mid = total(ds, "f002")
    r, f = recipe(ds, "categorical_facets", ["f002", "f000", "f001"], metric=mid, groups=["f000", "f001"])
    assert (
        len(r.records) == 4
        and next(v for v in r.records if v["facet"] == "B" and v["label"] == "Y")["value"] is None
    )
    compiled = compile_chart(f.chart, r)
    assert len(compiled.options["grid"]) == 2
    assert compiled.options["xAxis"][0]["max"] == compiled.options["xAxis"][1]["max"]
    assert len(render_asset(r, f.chart).records) == 4


def orders():
    ds = data(
        pd.DataFrame(
            {
                "order": ["O1", "O1", "O2", "O3"],
                "category": ["A", "B", "A", "B"],
                "amount": [10.0, 30.0, 20.0, 40.0],
            }
        )
    )
    ds.field("f000").role = Role.ID
    model = get_model(ds).model_copy(deep=True)
    model.entities = [Entity(id="order", label="Order", keys=["f000"], confirmed=True)]
    commit_model(ds, model)
    mid = total(ds, "f002")
    add_metric(
        ds,
        Metric(
            id="share", label="Share", aggregation="ratio", numerator=mid, denominator=mid, confirmed=True
        ),
    )
    return ds


def test_row_selection_and_entity_closure_are_distinct_and_anchored():
    ds = orders()
    base = ds.context([0, 2, 3])
    rows = make_selection(ds, base, [0], "predicate", "hash", 1)
    entity = make_selection(ds, base, [0], "predicate", "hash", 2, "entities", "order")
    assert rows.rows == entity.rows == [0]  # O1's other line is outside the anchor.
    whole = make_selection(ds, ds.context(), [0], "predicate", "hash", 3, "entities", "order")
    assert whole.rows == [0, 1]


def test_preview_compare_filter_return_preserves_investigation_and_allowances():
    ws = Workspace()
    ws.load(orders())
    ws.investigation = discover(ws.dataset)
    original = ws.investigation
    ws.model_count, ws.followups = 1, 3
    preview(ws, [0, 2], "predicate", "hash")
    assert ws.investigation is original and ws.rows is None and ws.model_count == 1 and ws.followups == 3
    ws.begin_filtered()
    assert ws.rows == [0, 2] and ws.investigation is None
    ws.return_to_anchor()
    assert ws.rows is None and ws.investigation is original and ws.model_count == 1 and ws.followups == 3


def test_comparison_freezes_categories_and_denominator_scope():
    ds = orders()
    selection = make_selection(ds, ds.context(), [0, 2], "predicate", "hash", 1)
    anchored = build_comparison(
        ds, selection, "metric", metric="share", groups=["f001"], denominator="anchored"
    )
    within = build_comparison(ds, selection, "metric", metric="share", groups=["f001"], denominator="cohort")
    a = {r["label"]: r["value"] for r in anchored.views[0].result.records}
    c = {r["label"]: r["value"] for r in within.views[0].result.records}
    assert a["A"] == 0.3 and c["A"] == 1
    assert [r["key"] for r in anchored.views[0].result.records] == [
        r["key"] for r in anchored.views[1].result.records
    ]
    assert axis_domains(anchored.views[0].finding.chart, anchored.views[0].result) == axis_domains(
        anchored.views[1].finding.chart, anchored.views[1].result
    )
    validate_bundle(anchored, ds)


def test_multi_context_comparison_roundtrip_and_fresh_process(tmp_path):
    ws = Workspace()
    ws.load(orders())
    ws.investigation = discover(ws.dataset)
    preview(ws, [0, 2], "predicate", "hash")
    bundle = build_comparison(ws.dataset, ws.selection, "ecdf", measure="f002")
    ws.comparison = bundle
    ws.comparisons = [bundle.model_copy(deep=True)]
    blob = export_bundle(ws, True)
    restored = import_bundle(blob)
    assert restored.comparisons[0] == bundle
    assert all(v["status"] == "match" for v in recompute(restored))
    target = tmp_path / "comparison.zip"
    target.write_bytes(blob)
    process = subprocess.run(
        [sys.executable, "-m", "firstlook.replay", "recompute", str(target)], capture_output=True, text=True
    )
    assert process.returncode == 0 and '"different"' not in process.stdout, process.stderr
    tampered = bundle.model_copy(deep=True)
    tampered.views[0].context.row_ids.append(3)
    with pytest.raises(ValueError):
        validate_bundle(tampered, ws.dataset)


def time_data():
    ds = data(
        pd.DataFrame({"date": pd.date_range("2024-01-01", periods=5), "amount": [2.0, 4.0, 8.0, 16.0, 32.0]})
    )
    mid = total(ds)
    model = get_model(ds).model_copy(deep=True)
    model.time_policies = [
        TimePolicy(
            id="daily",
            field="f000",
            kind="event",
            expected_frequency="D",
            coverage_complete=True,
            complete_through="2024-01-05",
            confirmed=True,
        )
    ]
    model.metric(mid).time_policy = "daily"
    commit_model(ds, model)
    return ds, mid


def test_complete_trailing_windows_have_independent_known_values():
    ds, mid = time_data()
    r, _ = recipe(
        ds, "temporal", ["f001", "f000"], metric=mid, time_field="f000", mode="smooth", period="D", window=3
    )
    smooth = [v["value"] for v in r.records if v["group"].startswith("Trailing")]
    assert smooth[:2] == [None, None] and smooth[2:] == pytest.approx([14 / 3, 28 / 3, 56 / 3])
    assert [v["value"] for v in r.records if v["group"] == "Recorded period"] == [2, 4, 8, 16, 32]


def test_unknown_coverage_blocks_smoothing_and_partial_calendar():
    ds, mid = time_data()
    model = get_model(ds).model_copy(deep=True)
    model.time_policies[0].coverage_complete = False
    model.time_policies[0].complete_through = None
    commit_model(ds, model)
    with pytest.raises(ValueError, match="complete"):
        recipe(ds, "temporal", ["f001", "f000"], metric=mid, time_field="f000", mode="smooth", period="D")
    with pytest.raises(ValueError, match="complete"):
        recipe(ds, "temporal", ["f001", "f000"], metric=mid, time_field="f000", mode="calendar", period="D")


def test_geometry_is_not_silently_offered_as_a_scalar_prediction_target():
    from firstlook.modeling import suggested_model_plan

    ds = data(pd.DataFrame({"bearing": np.linspace(0, 359, 220), "amount": np.arange(220)}))
    configure_meaning(ds, "f000", "circular")
    assert "f000" not in eligible_targets(ds)
    assert suggested_model_plan(ds, ds.context(focus="f000")) is None
    with pytest.raises(ValueError, match="geometry"):
        recipe(ds, "density", ["f000", "f001"])


def test_chart_selection_uses_visible_members_only():
    ds = data(pd.DataFrame({"x": np.arange(40), "y": np.arange(40) ** 2}))
    r, f = recipe(ds, "density", ["f000", "f001"], bins=4)
    compiled = compile_chart(f.chart, r)
    ids = selected_rows(
        {"selection": {"selected": [{"series_index": 0, "data_indices": [0]}]}}, compiled, set(range(40))
    )
    assert ids == r.records[0]["row_ids"]


def test_entity_allocation_stays_anchored_while_cohort_denominator_changes():
    ds = data(
        pd.DataFrame(
            {
                "order": ["A", "A", "B", "B"],
                "category": ["X", "Y", "X", "Y"],
                "total": [100.0, 100.0, 200.0, 200.0],
            }
        )
    )
    ds.field("f000").role = Role.ID
    model = get_model(ds).model_copy(deep=True)
    model.entities = [Entity(id="order", label="Order", keys=["f000"], confirmed=True)]
    commit_model(ds, model)
    configure_meaning(ds, "f002", "flow")
    add_metric(
        ds,
        Metric(
            id="allocated",
            label="Allocated order amount",
            aggregation="sum",
            field="f002",
            entity="order",
            allocation="equal",
            confirmed=True,
        ),
    )
    selection = make_selection(ds, ds.context(), [0, 2], "predicate", "hash", 1)
    bundle = build_comparison(
        ds, selection, "metric", metric="allocated", groups=["f001"], denominator="cohort"
    )
    selected = {r["label"]: r["value"] for r in bundle.views[0].result.records}
    assert selected["X"] == 150 and selected["Y"] is None
    assert bundle.spec.entity_overlap == 2 and bundle.spec.row_overlap == 0


def test_real_other_label_does_not_collide_with_synthetic_remainder():
    ds = data(pd.DataFrame({"category": ["Other recorded groups", "A", "B"], "value": [100.0, 20.0, 10.0]}))
    mid = total(ds)
    r, f = analyze(ds, ds.context(), metric_plan(ds, ds.context(), mid, ["f000"], limit=2))
    assert r.records[0]["label"] == r.records[1]["label"]
    assert r.records[0]["key"] != r.records[1]["key"]
    compiled = compile_chart(f.chart, r)
    assert compiled.options["dataset"][0]["source"].position.tolist() == [0, 1]
    assert compiled.options["yAxis"]["data"] == ["Other recorded groups", "Other recorded groups (pooled)"]


def test_model_comparison_slice_is_original_test_membership_only():
    from firstlook.contracts import ModelRun
    from firstlook.comparison import validate_model_slice

    ds = orders()
    selection = make_selection(ds, ds.context(), [0, 2], "predicate", "hash", 1)
    run = ModelRun(
        id="recorded",
        context=ds.context().id,
        target="f002",
        predictors=["f001"],
        task="regression",
        split="random",
        train_ids=[0, 1],
        test_ids=[2, 3],
        metrics={},
        predictions=[
            {"row_id": 2, "actual": 20.0, "predicted": 18.0, "error": 2.0},
            {"row_id": 3, "actual": 40.0, "predicted": 45.0, "error": 5.0},
        ],
        provider="controlled",
    )
    bundle = build_comparison(ds, selection, "ecdf", measure="f002", model=run)
    assert bundle.model_slice["Selected"]["row_ids"] == [2]
    assert bundle.model_slice["Selected"]["mean_recorded_error"] == 2
    validate_model_slice(bundle, [run])
    bundle.model_slice["Selected"]["row_ids"].append(0)
    with pytest.raises(ValueError, match="memberships"):
        validate_model_slice(bundle, [run])


def test_counter_endpoint_selection_is_refused_by_core_preview():
    ds = orders()
    r, f = analyze(ds, ds.context(), metric_plan(ds, ds.context(), "amount", ["f001"]))
    r.metadata["definition"]["aggregation"] = "delta"
    ws = Workspace(dataset=ds, investigation=Investigation(ds.context(), findings=[f], results={r.id: r}))
    with pytest.raises(ValueError, match="interval"):
        preview(ws, [0, 2], r.id, "mapping")


def test_future_recipe_is_never_silently_executed_as_current():
    ds = data(pd.DataFrame({"x": np.arange(40)}))
    with pytest.raises(ValueError, match="recipe version"):
        analyze(ds, ds.context(), plan_for(ds.context(), "ecdf", ["f000"], "future", {"recipe_version": 99}))


def test_calendar_phase_preserves_full_cycles_and_original_dates():
    frame = pd.DataFrame(
        {"date": pd.date_range("2023-01-01", periods=24, freq="MS"), "amount": np.arange(1, 25, dtype=float)}
    )
    ds = data(frame)
    mid = total(ds)
    model = get_model(ds).model_copy(deep=True)
    model.time_policies = [
        TimePolicy(
            id="monthly",
            field="f000",
            kind="event",
            expected_frequency="MS",
            coverage_complete=True,
            complete_through="2024-12-31",
            confirmed=True,
        )
    ]
    model.metric(mid).time_policy = "monthly"
    commit_model(ds, model)
    r, _ = recipe(
        ds, "temporal", ["f001", "f000"], metric=mid, time_field="f000", mode="calendar", period="MS"
    )
    assert r.metrics["complete_cycles"] == 2
    assert [v["x"] for v in r.records] == list(range(1, 13)) * 2
    assert r.records[0]["date"].startswith("2023-01-01")


def test_common_baseline_is_same_date_and_preserves_original_values():
    frame = pd.DataFrame(
        {"date": pd.date_range("2024-01-01", periods=3), "a": [2.0, 4.0, 8.0], "b": [10.0, 15.0, 20.0]}
    )
    ds = data(frame)
    total(ds, "f001", "a")
    total(ds, "f002", "b")
    model = get_model(ds).model_copy(deep=True)
    for meaning in model.meanings:
        if meaning.field in {"f001", "f002"}:
            meaning.unit = "kilogram"
    model.time_policies = [
        TimePolicy(
            id="daily",
            field="f000",
            kind="event",
            expected_frequency="D",
            coverage_complete=True,
            complete_through="2024-01-03",
            confirmed=True,
        )
    ]
    commit_model(ds, model)
    r, _ = recipe(
        ds,
        "temporal",
        ["f001", "f002", "f000"],
        metric="a",
        metrics=["a", "b"],
        time_field="f000",
        mode="index",
        period="D",
        baseline="2024-01-01",
    )
    assert [v["value"] for v in r.records] == [100, 200, 400, 100, 150, 200]
    assert [v["original_value"] for v in r.records] == [2, 4, 8, 10, 15, 20]
    with pytest.raises(ValueError, match="reference date"):
        recipe(
            ds,
            "temporal",
            ["f001", "f002", "f000"],
            metric="a",
            metrics=["a", "b"],
            time_field="f000",
            mode="index",
            period="D",
            baseline="2020-01-01",
        )


def test_matched_comparison_model_conditions_preserve_both_children():
    import copy
    from firstlook.contracts import NarrativeSynthesis, ProposalBatch, HypothesisProposal
    from firstlook.investigation import review_comparison

    ds = orders()
    selection = make_selection(ds, ds.context(), [0, 2], "predicate", "hash", 1)
    bundle = build_comparison(ds, selection, "ecdf", measure="f002")

    class Controlled:
        records = []

        def propose(self, packet, images):
            self.packet, self.images = packet, images
            return ProposalBatch(
                proposals=[
                    HypothesisProposal(
                        question="Inspect counts behind the cumulative curve",
                        operation="binning",
                        finding_id=bundle.views[0].finding.id,
                        fields=["f002"],
                        reason="Check another representation of the same source values",
                    )
                ]
            )

        def synthesize(self, packet):
            return NarrativeSynthesis(
                interpretation="The distributional contrast is descriptive and needs business context.",
                evidence_ids=[bundle.views[0].finding.id],
            )

    visual, text = Controlled(), Controlled()
    a = review_comparison(ds, copy.deepcopy(bundle), visual, visual=True)
    b = review_comparison(ds, copy.deepcopy(bundle), text, visual=False)
    assert visual.packet.model_dump() == text.packet.model_dump()
    assert len(visual.images) == 2 and not text.images
    assert (
        len(a.checks) == len(b.checks) == 1 and a.checks[0].result.plan.context == bundle.views[0].context.id
    )


def test_jev_can_choose_an_eligible_missing_perspective_without_extra_call():
    from firstlook.contracts import DecisionRecord
    from firstlook.investigation import prioritize

    ds = data(pd.DataFrame({"x": np.arange(40, dtype=float)}))
    inv = discover(ds)

    class Controlled:
        def choose(self, state, options, instructions):
            choice = next((i for i in options if i.startswith("task:")), "none")
            return DecisionRecord(
                provider="controlled",
                requested_model="test",
                state_hash="state",
                options=list(options),
                choice=choice,
                accepted=choice != "none",
            )

    prioritize(inv, Controlled(), ds)
    assert inv.results[inv.findings[0].result_id].plan.operation == "ecdf"


def test_saved_comparison_keeps_its_meanings_after_current_definition_changes():
    ws = Workspace()
    ws.load(orders())
    ws.investigation = discover(ws.dataset)
    preview(ws, [0, 2], "predicate", "hash")
    old = build_comparison(ws.dataset, ws.selection, "metric", metric="share", groups=["f001"])
    ws.comparisons = [old]
    configure_meaning(ws.dataset, "f002", "state")
    ws.invalidate()
    assert ws.comparisons == [old] and ws.comparison is None
    ws.investigation = discover(ws.dataset)
    restored = import_bundle(export_bundle(ws, True))
    assert restored.comparisons[0].spec.selection.base.id != restored.context().id
    assert all(item["status"] == "match" for item in recompute(restored))


@pytest.mark.parametrize("mode", ["count", "proportion", "density"])
def test_histogram_quantity_has_correct_mass_and_area(mode):
    ds = data(pd.DataFrame({"value": np.arange(100, dtype=float)}))
    r, _ = recipe(ds, "histogram_sensitivity", ["f000"], bins=10, origin=0.5, normalization=mode)
    assert sum(v["count"] for v in r.records) == 100
    if mode == "density":
        assert sum(v["value"] * (v["right"] - v["left"]) for v in r.records) == pytest.approx(1)
    else:
        assert sum(v["value"] for v in r.records) == pytest.approx(100 if mode == "count" else 1)


def test_temporal_native_and_review_share_recorded_time_domain():
    ds, mid = time_data()
    r, f = recipe(
        ds, "temporal", ["f001", "f000"], metric=mid, time_field="f000", mode="aggregation", period="D"
    )
    domain = axis_domains(f.chart, r)["x"]
    assert domain[0] < pd.Timestamp("2024-01-01").timestamp() * 1000 < domain[1]
    assert compile_chart(f.chart, r).options["xAxis"]["min"] == domain[0]
    assert render_asset(r, f.chart).manifest["axis_domains"]["x"] == domain


def test_named_example_comparison_reopens_its_original_parser():
    from firstlook.examples import load_example
    from firstlook.comparison import dataset_for_bundle

    ds = load_example("semantic")
    selected = make_selection(ds, ds.context(), list(range(40)), "predicate", "mapping", 1)
    board = build_comparison(ds, selected, "ecdf", measure="f006")
    restored = dataset_for_bundle(board, ds)
    assert restored.frame.equals(ds.frame)


def test_constant_cdf_renders_jump_and_extensions_without_inventing_members():
    ds = data(pd.DataFrame({"value": [7.0] * 40}))
    r, f = analyze(ds, ds.context(), plan_for(ds.context(), "ecdf", ["f000"], "constant"))
    chart = compile_chart(f.chart, r)
    plotted = chart.options["dataset"][0]["source"]
    assert plotted.value.tolist() == [0, 1, 1]
    assert plotted.endpoint_extension.tolist() == [True, False, True]
    assert chart.row_map[0, 0] == [] and chart.row_map[0, 1] == list(range(40))
    asset = render_asset(r, f.chart)
    assert [v["value"] for v in asset.records] == [0, 1, 1]
    assert asset.manifest["cdf_endpoint_extensions"]


def test_named_metric_question_records_requested_time_resolution():
    from firstlook.questions import local_intent, run_question

    ds, mid = time_data()
    intent = local_intent(ds, "Show daily amount")
    assert intent.time_field == "f000" and intent.period == "D"
    assert local_intent(ds, "Show the trend of amount").time_field == "f000"
    inv = run_question(ds, Investigation(ds.context()), "Show daily amount")
    r = inv.results[inv.findings[0].result_id]
    assert r.plan.params["period"] == "D" and [row["value"] for row in r.records] == [2, 4, 8, 16, 32]


def test_period_question_requires_unambiguous_timestamp():
    from firstlook.questions import local_intent

    ds = data(
        pd.DataFrame(
            {
                "created": pd.date_range("2024-01-01", periods=5),
                "delivered": pd.date_range("2024-01-02", periods=5),
                "amount": np.arange(5, dtype=float),
            }
        )
    )
    total(ds, "f002")
    intent = local_intent(ds, "Show daily amount")
    assert intent.operation == "unsupported" and "timestamp" in intent.clarification
    grouped = data(
        pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5),
                "region": ["A", "B", "A", "B", "A"],
                "amount": np.arange(5, dtype=float),
            }
        )
    )
    total(grouped, "f002")
    assert local_intent(grouped, "Show daily amount by region").operation == "unsupported"
