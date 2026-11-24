"""Independent known-answer oracles for semantic grain, algebra, gaps and replay."""

import numpy as np
import pandas as pd
import pytest

from firstlook.challenges import automatic_challenges, challenge
from firstlook.discovery import Investigation, analyze, discover
from firstlook.evidence import export_bundle, import_bundle, recompute
from firstlook.ingest import from_frame
from firstlook.semantic.model import (
    add_metric,
    commit_model,
    configure_meaning,
    get_model,
    import_contract,
    proposal_candidate,
)
from firstlook.semantic.planner import metric_plan
from firstlook.semantic.policy import decision
from firstlook.semantic.profile import inspect_relationship
from firstlook.semantic_contracts import Entity, MetadataProposal, Metric
from firstlook.state import Workspace, pin
from firstlook.contracts import Role
from firstlook.semantic.profile import build_model
from firstlook.visualization.compiler import compile_chart, selected_rows


def retail():
    df = pd.DataFrame(
        {
            "line_id": [1, 2, 3, 4, 5, 6],
            "order_id": ["O1", "O1", "O2", "O3", "O3", "O3"],
            "category": ["A", "B", "A", "B", "C", "C"],
            "sales": [10.0, 30.0, 20.0, 15.0, 5.0, 20.0],
            "order_total": [40.0, 40.0, 20.0, 40.0, 40.0, 40.0],
            "price": [1.0, 3.0, 2.0, 3.0, 1.0, 4.0],
            "quantity": [10.0, 10.0, 10.0, 5.0, 5.0, 5.0],
            "order_date": pd.to_datetime(
                ["2024-01-01", "2024-01-01", "2024-01-03", "2024-01-04", "2024-01-04", "2024-01-04"]
            ),
        }
    )
    ds = from_frame(df, "retail.csv", raw=df.to_csv(index=False).encode())
    for name in ["sales", "order_total", "price", "quantity"]:
        ds.field(fid(ds, name)).role = Role.MEASURE
    ds.record.semantic_model = build_model(ds)
    return ds


def fid(ds, name):
    return next(f.id for f in ds.record.fields if f.name == name)


def eid(ds, name):
    return next(e.id for e in get_model(ds).entities if e.keys == [fid(ds, name)])


def run(ds, mid, groups=None, **kwargs):
    ctx = ds.context()
    return analyze(ds, ctx, metric_plan(ds, ctx, mid, groups, **kwargs))


def amount(ds, name="sales"):
    configure_meaning(ds, fid(ds, name), "flow")
    m = Metric(
        id="total_" + name, label="Recorded " + name, aggregation="sum", field=fid(ds, name), confirmed=True
    )
    add_metric(ds, m)
    return m


def test_quantities_are_proposals_and_sums_require_a_declared_definition():
    ds = retail()
    model = get_model(ds)
    sales = model.metric("m_total_" + fid(ds, "sales"))
    assert not model.meaning(sales.field).confirmed
    assert decision(ds, sales, []).status == "conditional"
    configure_meaning(ds, sales.field, "flow")
    assert decision(ds, sales, []).status == "conditional"
    sales = sales.model_copy(deep=True)
    sales.confirmed = True
    add_metric(ds, sales)
    assert run(ds, sales.id)[0].records[0]["value"] == 100


def test_row_mean_and_average_order_are_distinct_and_challenged():
    ds = retail()
    amount(ds)
    m = Metric(
        id="per_order",
        label="Sales per order",
        field=fid(ds, "sales"),
        aggregation="average_per_entity",
        entity=eid(ds, "order_id"),
        confirmed=True,
    )
    add_metric(ds, m)
    r, f = run(ds, m.id)
    assert r.records[0]["value"] == pytest.approx(100 / 3)
    assert r.records[0]["denominator"] == 3
    inv = Investigation(ds.context(), findings=[f], results={r.id: r})
    c = challenge(ds, inv, f, "semantic_unit")
    assert c.status == "changed" and c.result.records[0]["value"] == pytest.approx(100 / 6)


def test_overlapping_entity_incidence_does_not_become_composition():
    ds = retail()
    mid = "m_distinct_" + eid(ds, "order_id") + "_share"
    r, f = run(ds, mid, [fid(ds, "category")])
    assert sorted(row["value"] for row in r.records) == pytest.approx([1 / 3, 2 / 3, 2 / 3])
    assert r.metrics["sum_of_displayed_values"] == pytest.approx(5 / 3)
    assert r.metrics["composition"] is False and r.metrics["overlap_memberships"] == 2
    inv = Investigation(ds.context(), findings=[f], results={r.id: r})
    assert challenge(ds, inv, f, "semantic_reconciliation").status == "changed"
    assert challenge(ds, inv, f, "semantic_denominator").status == "changed"
    assert all(row["value"] == 1 for row in challenge(ds, inv, f, "semantic_denominator").result.records)


def test_partition_sales_share_closes_and_preserves_source_membership():
    ds = retail()
    m = amount(ds)
    share = Metric(
        id="share",
        label="Share of recorded sales",
        aggregation="ratio",
        numerator=m.id,
        denominator=m.id,
        confirmed=True,
    )
    add_metric(ds, share)
    r, f = run(ds, "share", [fid(ds, "category")])
    assert r.metrics["composition"] is True and sum(row["value"] for row in r.records) == pytest.approx(1)
    compiled = compile_chart(f.chart, r)
    expected = r.records[0]["row_ids"]
    assert (
        selected_rows(
            {"selection": {"selected": [{"series_index": 0, "data_indices": [0]}]}},
            compiled,
            set(ds.frame.index),
        )
        == expected
    )
    assert compiled.row_map[(0, 0)] == expected
    assert compiled.options["xAxis"]["max"] == 1


def test_repeated_order_amount_requires_entity_grain_and_attribution():
    ds = retail()
    amount(ds, "order_total")
    m = Metric(
        id="orders",
        label="Distinct order amount",
        aggregation="sum",
        field=fid(ds, "order_total"),
        entity=eid(ds, "order_id"),
        confirmed=True,
    )
    add_metric(ds, m)
    assert run(ds, m.id)[0].records[0]["value"] == 100
    with pytest.raises(ValueError, match="overlapping"):
        run(ds, m.id, [fid(ds, "category")])
    m.allocation = "equal"
    add_metric(ds, m)
    r, _ = run(ds, m.id, [fid(ds, "category")])
    assert sum(row["value"] for row in r.records) == pytest.approx(100)
    assert {row["label"]: row["value"] for row in r.records} == {"B": 40.0, "C": 20.0, "A": 40.0}


def test_entity_values_must_be_constant_and_other_recomposes_allocation():
    ds = retail()
    m = amount(ds)
    m.entity = eid(ds, "order_id")
    add_metric(ds, m)
    assert decision(ds, m, []).status == "disallowed"
    m = Metric(
        id="orders",
        label="Order value",
        aggregation="sum",
        field=fid(ds, "order_total"),
        entity=eid(ds, "order_id"),
        confirmed=True,
        allocation="equal",
    )
    configure_meaning(ds, m.field, "flow")
    add_metric(ds, m)
    r, _ = run(ds, m.id, [fid(ds, "category")], limit=2)
    assert len(r.records) == 2 and sum(row["value"] for row in r.records) == pytest.approx(100)


def test_weighted_mean_recomputes_components_and_rejects_negative_weights():
    ds = retail()
    configure_meaning(ds, fid(ds, "price"), "rate")
    m = Metric(
        id="weighted",
        label="Unit price weighted by quantity",
        aggregation="weighted_mean",
        field=fid(ds, "price"),
        weight=fid(ds, "quantity"),
        confirmed=True,
    )
    add_metric(ds, m)
    r, _ = run(ds, m.id)
    assert r.records[0]["value"] == pytest.approx(100 / 45)
    assert r.records[0]["weight_sum"] == 45
    ds.frame.loc[0, m.weight] = -1
    assert decision(ds, m, []).status == "disallowed"


def test_ratio_uses_sum_components_instead_of_average_ratios():
    ds = retail()
    s = amount(ds)
    q = amount(ds, "quantity")
    ratio = Metric(
        id="ratio",
        label="Revenue per unit",
        aggregation="ratio",
        numerator=s.id,
        denominator=q.id,
        denominator_scope="group",
        confirmed=True,
    )
    add_metric(ds, ratio)
    r, _ = run(ds, ratio.id)
    assert r.records[0]["value"] == pytest.approx(100 / 45)
    assert r.records[0]["value"] != pytest.approx(np.mean([1, 3, 2, 3, 1, 4]))
    assert r.metadata["proportion"] is False


def time_policy(ds, kind, gap="preserve", frequency="D", complete=False, max_gap=0, series=None):
    candidate = get_model(ds).model_copy(deep=True)
    p = candidate.time_policies[0]
    p.kind = kind
    p.gap_policy = gap
    p.expected_frequency = frequency
    p.confirmed = True
    p.coverage_complete = complete
    p.complete_through = "2024-01-04" if complete else None
    p.max_gap_periods = max_gap
    p.series = series or []
    commit_model(ds, candidate)
    return p.id


def test_missing_event_day_is_unknown_until_complete_recording_is_declared():
    ds = retail()
    m = amount(ds)
    date = fid(ds, "order_date")
    r, _ = run(ds, m.id, time_field=date, period="D")
    assert [row["value"] for row in r.records] == [40, None, 20, 40]
    time_policy(ds, "event", "zero", complete=True)
    r, _ = run(ds, m.id, time_field=date, period="D")
    assert [row["value"] for row in r.records] == [40, 0, 20, 40]
    assert r.records[1]["synthetic"] is True and r.records[1]["row_ids"] == []
    assert len(ds.frame) == 6
    r, _ = run(ds, m.id, time_field=date, period="MS")
    assert r.records[0]["value"] == 100


def test_unconfirmed_zero_policy_and_instant_zero_are_rejected_atomically():
    ds = retail()
    before = ds.context().id
    with pytest.raises(ValueError, match="Structural zero"):
        time_policy(ds, "instant", "zero", complete=True)
    assert ds.context().id == before
    with pytest.raises(ValueError, match="Structural zero"):
        time_policy(ds, "event", "zero", complete=False)


def meter(values=(100.0, 120.0, 150.0)):
    df = pd.DataFrame(
        {
            "meter_id": ["M1"] * 3,
            "reading_date": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-04"]),
            "meter_reading": values,
        }
    )
    ds = from_frame(df, "meter.csv", raw=df.to_csv(index=False).encode())
    ds.field(fid(ds, "meter_reading")).role = Role.MEASURE
    ds.record.semantic_model = build_model(ds)
    return ds


def test_irregular_counter_intervals_are_not_zero_daily_consumption():
    ds = meter()
    configure_meaning(ds, fid(ds, "meter_reading"), "cumulative", "kWh")
    m = Metric(
        id="delta",
        label="Measured increments",
        aggregation="delta",
        field=fid(ds, "meter_reading"),
        entity=eid(ds, "meter_id"),
        confirmed=True,
    )
    add_metric(ds, m)
    time_policy(ds, "cumulative")
    r, _ = run(ds, m.id, time_field=fid(ds, "reading_date"), period="D")
    assert [row["value"] for row in r.records] == [None, None, 20, 30]
    assert r.records[2]["row_ids"] == [0, 1] and r.records[3]["row_ids"] == [1, 2]
    r, _ = run(ds, m.id, time_field=fid(ds, "reading_date"), period="MS")
    assert r.records[0]["value"] == 50
    assert any("ending observation" in w for w in r.warnings)


def test_counter_reset_is_missing_and_stock_sums_are_blocked():
    ds = meter((100.0, 10.0, 30.0))
    configure_meaning(ds, fid(ds, "meter_reading"), "cumulative")
    m = Metric(
        id="delta",
        label="Increments",
        aggregation="delta",
        field=fid(ds, "meter_reading"),
        entity=eid(ds, "meter_id"),
        confirmed=True,
    )
    add_metric(ds, m)
    r, _ = run(ds, m.id, time_field=fid(ds, "reading_date"), period="D")
    assert [row["value"] for row in r.records] == [None, None, None, 20]
    configure_meaning(ds, m.field, "state")
    assert (
        decision(
            ds, Metric(id="bad", label="Sum of stocks", field=m.field, aggregation="sum", confirmed=True), []
        ).status
        == "disallowed"
    )


def test_last_snapshot_is_recomputed_per_period_not_sum_of_daily_stocks():
    ds = meter()
    configure_meaning(ds, fid(ds, "meter_reading"), "state")
    m = Metric(
        id="stock",
        label="Latest level",
        field=fid(ds, "meter_reading"),
        entity=eid(ds, "meter_id"),
        aggregation="snapshot_last",
        confirmed=True,
    )
    add_metric(ds, m)
    r, _ = run(ds, m.id, time_field=fid(ds, "reading_date"), period="MS")
    assert r.records[0]["value"] == 150


def test_explicit_null_is_not_filled_and_interpolation_is_bounded():
    ds = meter((100.0, None, 150.0))
    configure_meaning(ds, fid(ds, "meter_reading"), "state")
    m = Metric(
        id="state",
        label="State",
        field=fid(ds, "meter_reading"),
        entity=eid(ds, "meter_id"),
        aggregation="snapshot_last",
        confirmed=True,
    )
    add_metric(ds, m)
    time_policy(ds, "state", "forward_fill", max_gap=1, series=[fid(ds, "meter_id")])
    r, _ = run(ds, m.id, time_field=fid(ds, "reading_date"), period="D")
    assert [row["value"] for row in r.records] == [100, 100, None, 150]


def test_offset_units_and_unknown_units_do_not_enable_log():
    ds = retail()
    f = fid(ds, "price")
    configure_meaning(ds, f, "temperature", "degC")
    candidate = get_model(ds).model_copy(deep=True)
    candidate.meaning(f).allowed_transforms = ["identity", "log"]
    commit_model(ds, candidate)
    metric = Metric(
        id="log", label="Log temperature", aggregation="mean", field=f, transform="log", confirmed=True
    )
    assert decision(ds, metric, []).status == "disallowed"
    candidate = get_model(ds).model_copy(deep=True)
    candidate.meaning(f).unit = "invented_dimension"
    commit_model(ds, candidate)
    assert decision(ds, metric, []).status == "conditional"


def test_transform_occurs_after_aggregation_and_rejects_nonpositive_log():
    ds = retail()
    m = amount(ds)
    m.transform = "log"
    add_metric(ds, m)
    r, _ = run(ds, m.id)
    assert r.records[0]["value"] == pytest.approx(np.log(100))
    assert r.metadata["transform_stage"] == "after_aggregation"
    ds.frame[m.field] = -1
    with pytest.raises(ValueError, match="positive"):
        run(ds, m.id)


def test_hierarchy_exceptions_are_exact_and_cannot_be_confirmed_as_rollup():
    ds = retail()
    r = inspect_relationship(ds, fid(ds, "order_id"), fid(ds, "category"))
    assert r.violating_levels == 2 and not r.strict
    candidate = get_model(ds).model_copy(deep=True)
    r.confirmed = True
    r.relation = "hierarchy"
    candidate.relationships = [r]
    with pytest.raises(ValueError, match="one recorded parent"):
        commit_model(ds, candidate)


def test_semantic_context_changes_invalidate_old_plans_and_pins_keep_definition():
    ds = retail()
    m = amount(ds)
    ctx = ds.context()
    p = metric_plan(ds, ctx, m.id)
    r, f = analyze(ds, ctx, p)
    ws = Workspace(dataset=ds, investigation=Investigation(ctx, findings=[f], results={r.id: r}))
    pin(ws, f.id)
    old = ws.pins[0]["semantic_contract"]
    configure_meaning(ds, m.field, "state")
    ws.invalidate()
    assert old != get_model(ds).model_dump(mode="json") and ws.context().id != ctx.id
    with pytest.raises(ValueError, match="changed"):
        analyze(ds, ctx, p)


def test_contract_import_rejects_wrong_dataset_cycles_unknown_fields_and_invented_units():
    ds = retail()
    model = get_model(ds).model_copy(deep=True)
    model.dataset = "bad"
    with pytest.raises(ValueError, match="different dataset"):
        import_contract(ds, model.model_dump_json().encode())
    model = get_model(ds).model_copy(deep=True)
    model.metrics.append(
        Metric(
            id="cycle",
            label="Cycle",
            aggregation="ratio",
            numerator="cycle",
            denominator="m_rows",
            confirmed=True,
        )
    )
    with pytest.raises(ValueError, match="circular"):
        commit_model(ds, model)
    with pytest.raises(ValueError, match="invent"):
        proposal_candidate(
            ds, MetadataProposal(subject=fid(ds, "sales"), property="unit", value="USD", reason="Guess")
        )
    model = get_model(ds).model_copy(deep=True)
    model.entities.append(Entity(id="bad", label="Bad", keys=["unknown"]))
    with pytest.raises(ValueError, match="unknown field"):
        commit_model(ds, model)


def test_semantic_evidence_roundtrip_and_deterministic_checks_replay():
    ds = retail()
    m = amount(ds)
    add_metric(
        ds,
        Metric(
            id="avg",
            label="Sales per order",
            aggregation="average_per_entity",
            field=m.field,
            entity=eid(ds, "order_id"),
            confirmed=True,
        ),
    )
    ws = Workspace()
    ws.load(ds)
    ws.investigation = discover(ds)
    automatic_challenges(ds, ws.investigation)
    blob = export_bundle(ws, True)
    opened = import_bundle(blob)
    assert opened.dataset.record.semantic_model.revision == get_model(ds).revision
    assert all(item["status"] == "match" for item in recompute(opened))
    assert opened.investigation.semantic_decisions


def test_contextual_hierarchy_needs_its_disambiguating_fields():
    df = pd.DataFrame(
        {
            "city": ["Springfield", "Springfield", "Springfield", "Paris"],
            "state": ["IL", "IL", "MA", "TX"],
            "country": ["US", "US", "US", "US"],
            "region_code": ["C1", "C1", "C2", "C2"],
        }
    )
    ds = from_frame(df, "places.csv")
    city, state, region = [fid(ds, n) for n in ["city", "state", "region_code"]]
    assert not inspect_relationship(ds, city, state).strict
    scoped = inspect_relationship(ds, city, state, [region])
    assert scoped.strict and scoped.within == [region]
    candidate = get_model(ds).model_copy(deep=True)
    scoped.confirmed = True
    candidate.relationships = [scoped]
    commit_model(ds, candidate)


def test_declared_model_group_and_prediction_availability_apply_to_every_model():
    from firstlook.modeling import predictor_policy, run_model, suggested_model_plan

    rng = np.random.default_rng(10)
    df = pd.DataFrame(
        {
            "patient_id": np.repeat([f"P{i}" for i in range(30)], 10),
            "measurement": rng.normal(size=300),
            "outcome": rng.normal(size=300),
            "post_outcome_label": rng.choice(["A", "B", "C"], 300),
        }
    )
    ds = from_frame(df, "patients.csv")
    group = fid(ds, "patient_id")
    target = fid(ds, "outcome")
    after = fid(ds, "post_outcome_label")
    candidate = get_model(ds).model_copy(deep=True)
    candidate.model_group = group
    candidate.meaning(after).available_at_prediction = False
    commit_model(ds, candidate)
    ctx = ds.context(focus=target)
    assert suggested_model_plan(ds, ctx) == (target, "group", group)
    allowed, excluded = predictor_policy(ds, target, ds.frame)
    assert after not in allowed and "prediction time" in excluded[after]
    with pytest.raises(ValueError, match="requires a group holdout"):
        run_model(ds, ctx, target)
    result = run_model(ds, ctx, target, "group", group)
    assert not set(ds.frame.loc[result.train_ids, group]) & set(ds.frame.loc[result.test_ids, group])
    assert result.parameters["semantic_revision"] == get_model(ds).revision


def test_named_metric_question_resolves_the_recorded_algebra_and_ambiguous_average_does_not():
    from firstlook.questions import local_intent, run_question

    ds = retail()
    m = amount(ds)
    intent = local_intent(ds, "Recorded sales by category")
    assert intent.operation == "metric" and intent.metric_id == m.id
    inv = run_question(ds, Investigation(ds.context()), "Recorded sales by category")
    assert inv.results[inv.findings[0].result_id].plan.operation == "metric"
    assert local_intent(ds, "average sales by category").operation == "unsupported"


def test_contract_coverage_is_not_reused_for_an_arbitrary_row_selection():
    ds = retail()
    m = amount(ds)
    time_policy(ds, "event", "zero", complete=True)
    ctx = ds.context(rows=[0, 1, 3, 4, 5])
    r, _ = analyze(ds, ctx, metric_plan(ds, ctx, m.id, time_field=fid(ds, "order_date"), period="D"))
    assert [row["value"] for row in r.records] == [40, None, None, 40]
    assert any("whole upload" in w for w in r.warnings)


def test_ratio_respects_equal_allocation_of_an_entity_valued_component():
    ds = retail()
    configure_meaning(ds, fid(ds, "order_total"), "flow")
    total = Metric(
        id="orders",
        label="Allocated order value",
        aggregation="sum",
        field=fid(ds, "order_total"),
        entity=eid(ds, "order_id"),
        allocation="equal",
        confirmed=True,
    )
    add_metric(ds, total)
    add_metric(
        ds,
        Metric(
            id="share_orders",
            label="Allocated share",
            aggregation="ratio",
            numerator=total.id,
            denominator=total.id,
            confirmed=True,
        ),
    )
    r, _ = run(ds, "share_orders", [fid(ds, "category")])
    assert sum(row["value"] for row in r.records) == pytest.approx(1)
    assert sorted(row["value"] for row in r.records) == pytest.approx([0.2, 0.4, 0.4])


def test_week_boundaries_recompute_original_event_amounts():
    ds = retail()
    m = amount(ds)
    date = fid(ds, "order_date")
    ds.frame[date] = pd.to_datetime(
        ["2024-01-07", "2024-01-08", "2024-01-08", "2024-01-08", "2024-01-08", "2024-01-08"]
    )
    r, _ = run(ds, m.id, time_field=date, period="W")
    assert [row["value"] for row in r.records] == [10, 90]
    assert str(r.records[0]["x"]).startswith("2024-01-01")
    assert r.records[0]["row_ids"] == [0] and r.records[1]["row_ids"] == [1, 2, 3, 4, 5]


def test_zero_denominator_group_stays_undefined_without_erasing_other_groups():
    ds = retail()
    s = amount(ds)
    q = amount(ds, "quantity")
    ds.frame.loc[ds.frame[fid(ds, "category")] == "A", q.field] = 0
    ratio = Metric(
        id="rate",
        label="Rate",
        aggregation="ratio",
        numerator=s.id,
        denominator=q.id,
        denominator_scope="group",
        confirmed=True,
    )
    add_metric(ds, ratio)
    r, f = run(ds, ratio.id, [fid(ds, "category")])
    values = {row["label"]: row["value"] for row in r.records}
    assert values["A"] is None and values["B"] == pytest.approx(45 / 15)
    assert any("undefined" in warning for warning in r.warnings)
    compile_chart(f.chart, r)


def test_unknown_meaning_and_excluded_identity_cannot_authorize_metrics():
    ds = retail()
    configure_meaning(ds, fid(ds, "sales"), "unknown")
    m = Metric(id="unknown", label="Unknown total", aggregation="sum", field=fid(ds, "sales"), confirmed=True)
    assert decision(ds, m, []).status == "conditional"
    assert decision(ds, m, ["missing_field"]).status == "disallowed"
    ds.field(fid(ds, "order_id")).excluded = True
    with pytest.raises(ValueError, match="excluded"):
        run(ds, "m_distinct_" + eid(ds, "order_id"))


def test_multiple_state_series_roll_up_latest_values_without_summing_days():
    df = pd.DataFrame(
        {
            "meter_id": ["M1", "M1", "M2", "M2"],
            "reading_date": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-01", "2024-01-04"]),
            "level": [100.0, 120.0, 200.0, 230.0],
        }
    )
    ds = from_frame(df, "states.csv")
    ds.field(fid(ds, "level")).role = Role.MEASURE
    configure_meaning(ds, fid(ds, "level"), "state")
    m = Metric(
        id="stock",
        label="Last states",
        aggregation="snapshot_last",
        field=fid(ds, "level"),
        entity=eid(ds, "meter_id"),
        confirmed=True,
    )
    add_metric(ds, m)
    time_policy(ds, "state", "forward_fill", max_gap=3, series=[fid(ds, "meter_id")])
    r, _ = run(ds, m.id, time_field=fid(ds, "reading_date"), period="MS")
    assert r.records[0]["value"] == 350


def test_circular_mean_needs_angle_units_and_does_not_average_across_the_wrap():
    ds = retail()
    f = fid(ds, "price")
    ds.frame[f] = [350.0, 10.0, 350.0, 10.0, 350.0, 10.0]
    configure_meaning(ds, f, "circular", "degree")
    m = Metric(id="direction", label="Mean direction", aggregation="circular_mean", field=f, confirmed=True)
    add_metric(ds, m)
    value = run(ds, m.id)[0].records[0]["value"]
    assert min(value, 360 - value) < 1e-8
    assert (
        decision(
            ds, Metric(id="bad", label="Linear mean", aggregation="mean", field=f, confirmed=True), []
        ).status
        == "disallowed"
    )
    configure_meaning(ds, f, "circular", "radian")
    assert decision(ds, m, []).status == "conditional"


def test_role_corrections_keep_contract_references_coherent():
    from firstlook.semantics import semantic_table, apply_semantics
    from firstlook.semantic.model import validate_model

    ds = retail()
    date = fid(ds, "order_date")
    table = semantic_table(ds)
    table.loc[table.field == date, "role"] = "category"
    apply_semantics(ds, table)
    assert not get_model(ds).time_policies
    validate_model(ds, get_model(ds))
    table = semantic_table(ds)
    table.loc[table.field == date, "role"] = "timestamp"
    apply_semantics(ds, table)
    assert get_model(ds).time_policies[0].field == date
    validate_model(ds, get_model(ds))


def test_interactive_working_views_are_bounded_and_old_pins_are_standalone():
    ds = retail()
    m = amount(ds)
    inv = Investigation(ds.context())
    ws = Workspace(dataset=ds, investigation=inv)
    r, f = run(ds, m.id)
    inv.add_view(r, f)
    pin(ws, f.id)
    for limit in range(2, 22):
        r, f = run(ds, "m_rows", [fid(ds, "category")], limit=limit)
        inv.add_view(r, f)
    assert len(inv.findings) <= 18 and len(inv.results) <= 18
    assert ws.pins[0]["result"]["records"][0]["value"] == 100


def test_same_bytes_with_different_missing_policies_are_a_different_contract_scope():
    from firstlook.ingest import load_table

    raw = b"category\nA\nB\nNA\nC\n"
    original = load_table(raw, "same.csv")
    other = load_table(raw, "same.csv", missing_tokens=["", "NA"])
    assert original.record.fingerprint == other.record.fingerprint
    with pytest.raises(ValueError, match="different parsing"):
        import_contract(other, get_model(original).model_dump_json().encode())
