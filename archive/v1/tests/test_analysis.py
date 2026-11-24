import io

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from firstlook.challenges import challenge, eligible
from firstlook.contracts import ChartSpec
from firstlook.discovery import analyze, correlations, discover, plan_for
from firstlook.examples import load_example
from firstlook.ingest import InputError, from_frame, load_table
from firstlook.profiling import profile
from firstlook.semantics import apply_semantics, semantic_table
from firstlook.visualization.compiler import compile_chart, selected_rows, validate_chart


def test_ingestion_missing_zero_duplicate_names():
    ds = load_table("x,x,名称\n0,NA,a\n,2,b\n3,4,c\n".encode(), "test.csv")
    assert [f.name for f in ds.record.fields] == ["x", "x", "名称"]
    assert ds.frame.columns.is_unique
    assert ds.frame.iloc[0, 0] == 0
    assert pd.isna(ds.frame.iloc[1, 0])
    assert ds.frame.iloc[0, 1] == "NA"


@pytest.mark.parametrize("rows,columns", [(50_001, 1), (2, 81), (0, 2)])
def test_dimension_guards(rows, columns):
    with pytest.raises(InputError):
        from_frame(pd.DataFrame(np.zeros((rows, columns))), "large")


def test_upload_bytes_guard():
    with pytest.raises(InputError, match="25 MiB"):
        load_table(b"0" * (25 * 1024**2 + 1), "large.csv")


def test_parquet_and_nested():
    out = io.BytesIO()
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", None]}).to_parquet(out)
    ds = load_table(out.getvalue(), "table.parquet")
    assert ds.record.rows == 3
    with pytest.raises(InputError, match="Nested"):
        from_frame(pd.DataFrame({"a": [{"x": 1}]}), "nested")


def test_numerical_oracle():
    ds = from_frame(pd.DataFrame({"mass": [1.0, 2.0, 3.0, 4.0, np.nan]}), "oracle")
    p = profile(ds)["fields"]["f000"]
    assert p["count"] == 4 and p["missing"] == 1
    assert p["mean"] == 2.5 and p["median"] == 2.5
    assert p["std"] == pytest.approx(np.sqrt(5 / 3))
    assert p["quantiles"]["0.25"] == 1.75


def test_identifier_rejected_as_measure(dataset):
    plan = plan_for(dataset.context(), "distribution", ["f000"], "Invalid sum-like measure")
    with pytest.raises(ValueError, match="identifiers"):
        analyze(dataset, dataset.context(), plan)


def test_semantic_transaction_and_context(dataset):
    old = dataset.context().id
    table = semantic_table(dataset)
    table.loc[table.field == "f001", "role"] = "identifier"
    changed = apply_semantics(dataset, table)
    assert changed == ["f001"] and dataset.context().id != old
    invalid = semantic_table(dataset)
    invalid.loc[invalid.field == "f003", "role"] = "measure"
    before = dataset.record.model_dump()
    with pytest.raises(ValueError):
        apply_semantics(dataset, invalid)
    assert dataset.record.model_dump() == before


def test_ordinal_order():
    ds = from_frame(pd.DataFrame({"level": ["low", "high", "mid"] * 20}), "order")
    table = semantic_table(ds)
    table.loc[0, "role"] = "ordinal"
    table.loc[0, "order"] = "low | mid | high"
    apply_semantics(ds, table)
    ctx = ds.context()
    r, _ = analyze(ds, ctx, plan_for(ctx, "frequency", ["f000"], "Frequency"))
    assert [r["label"] for r in r.records] == ["low", "mid", "high"]


def test_zero_variance_is_not_correlation():
    assert correlations(pd.DataFrame({"x": [1] * 40, "y": range(40)}), "x", "y")["pearson"] is None


@settings(deadline=None)
@given(
    st.lists(
        st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=10,
        max_size=40,
    )
)
def test_correlation_order_invariance(values):
    df = pd.DataFrame({"x": values, "y": np.arange(len(values))})
    original = correlations(df, "x", "y")
    reversed_ = correlations(df.iloc[::-1], "x", "y")
    for key in ["pearson", "spearman"]:
        if original[key] is not None:
            assert original[key] == pytest.approx(reversed_[key], abs=1e-10)


def test_affine_unit_change(dataset):
    df = dataset.frame[["f001", "f002"]].copy()
    a = correlations(df, "f001", "f002")
    df.f001 = df.f001 * 1000 + 10
    assert correlations(df, "f001", "f002")["pearson"] == pytest.approx(a["pearson"])


def test_reversal_challenge(dataset, investigation):
    f = next(f for f in investigation.findings if f.family == "relationship")
    c = challenge(dataset, investigation, f, "subgroup")
    assert c.status == "changed"
    assert c.result.metrics["pooled"] > 0.7
    assert all(g["pearson"] < -0.6 for g in c.result.metrics["groups"])
    assert sum(g["n"] for g in c.result.metrics["groups"]) == 600


@pytest.mark.parametrize("op", ["extremes", "rank", "quantile_bin_summary"])
def test_association_checks(dataset, investigation, op):
    f = next(f for f in investigation.findings if f.family == "relationship")
    c = challenge(dataset, investigation, f, op)
    assert c.result and c.chart
    compile_chart(c.chart, c.result)
    if op == "extremes":
        assert c.result.support < 600
        assert len(c.result.metadata["excluded_row_ids"]) > 0


def test_resampling_requires_assumption(dataset, investigation):
    f = next(f for f in investigation.findings if f.family == "relationship")
    assert "resampling" not in eligible(dataset, investigation, f)


def test_null_fixture_does_not_invent_signal():
    inv = discover(load_example("null"))
    assert not any(f.family == "relationship" for f in inv.findings)
    assert all(f.claim_type == "descriptive" for f in inv.findings)


@pytest.mark.parametrize("key", ["reversal", "penguins", "bike", "null", "nonlinear"])
def test_every_gallery_chart_compiles(key):
    ds = load_example(key)
    inv = discover(ds)
    assert 0 < len(inv.findings) <= 12
    for f in inv.findings:
        assert f.chart.result_id == f.result_id
        compiled = compile_chart(f.chart, inv.results[f.result_id])
        assert compiled.options["series"]


def test_selection_maps_original_rows(dataset, investigation):
    f = next(f for f in investigation.findings if f.family == "relationship")
    compiled = compile_chart(f.chart, investigation.results[f.result_id])
    ids = selected_rows(
        {"selection": {"selected": [{"series_index": 0, "data_indices": [2, 4, 999999]}]}},
        compiled,
        set(dataset.frame.index),
    )
    assert ids == sorted(set(compiled.row_map[0, 2] + compiled.row_map[0, 4]))
    assert selected_rows({"selection": {"areas": [{}]}}, compiled, set()) == []


@pytest.mark.parametrize("change", ["stale", "zero", "log"])
def test_chart_hard_constraints(dataset, investigation, change):
    f = next(f for f in investigation.findings if f.chart.template == "histogram")
    s = f.chart.model_copy(deep=True)
    if change == "stale":
        s.context = "wrong"
    elif change == "zero":
        s.zero_baseline = False
    else:
        s.scale = "log"
    r = investigation.results[f.result_id]
    if change == "log":
        r = r.model_copy(update={"records": [{"x": 1, "value": 0}]})
    with pytest.raises(ValueError):
        validate_chart(s, r)


@pytest.mark.parametrize("template", ["bar", "dot", "histogram", "ecdf", "scatter", "box", "line", "heatmap"])
def test_template_contracts(template, dataset):
    from firstlook.contracts import ResultArtifact

    ctx = dataset.context()
    plan = plan_for(ctx, "distribution", ["f001"], "View")
    row = {
        "x": 1,
        "y": 2,
        "label": "A",
        "value": 3,
        "min": 1,
        "q1": 2,
        "median": 3,
        "q3": 4,
        "max": 5,
        "n": 6,
    }
    r = ResultArtifact(id=plan.id, plan=plan, records=[row], support=6)
    s = ChartSpec(
        id="view",
        result_id=r.id,
        context=ctx.id,
        template=template,
        x_label="X",
        y_label="Y",
        zero_baseline=template in {"bar", "histogram"},
        alt="Known data",
    )
    assert compile_chart(s, r).options["series"][0]["type"] in {
        "bar",
        "scatter",
        "line",
        "boxplot",
        "heatmap",
    }


def test_leading_zero_codes_and_parser_settings_change_context():
    raw = b"code,label\n001,NA\n002,A\n003,B\n"
    a = load_table(raw, "codes.csv")
    b = load_table(raw, "codes.csv", missing_tokens=["", "NA"])
    assert a.frame.iloc[0, 0] == "001"
    assert a.context().id != b.context().id


def test_cumulative_distribution_exact_and_monotone(dataset):
    result, finding = analyze(
        dataset, dataset.context(), plan_for(dataset.context(), "ecdf", ["f001"], "Cumulative")
    )
    assert finding.chart.template == "ecdf"
    assert result.records[-1]["value"] == 1.0
    assert all(a["value"] <= b["value"] for a, b in zip(result.records, result.records[1:]))
    assert {i for r in result.records for i in r["row_ids"]} == set(range(600))


def test_curved_relation_can_survive_a_weak_signed_correlation():
    ds = load_example("nonlinear")
    inv = discover(ds)
    assert abs(correlations(ds.frame, "f001", "f003")["pearson"]) < 0.3
    assert any(
        f.family == "quantile_bin_summary" and inv.results[f.result_id].plan.fields == ["f001", "f003"]
        for f in inv.findings
    )


def test_proposed_numeric_ordinal_order_is_numeric():
    ds = from_frame(pd.DataFrame({"month": list(range(1, 13)) * 4}), "months")
    assert ds.field("f000").order == [str(i) for i in range(1, 13)]


def test_empty_semantic_unit_stays_unknown(dataset):
    table = semantic_table(dataset)
    table.loc[table.field == "f001", "unit"] = None
    apply_semantics(dataset, table)
    assert dataset.field("f001").unit == ""
