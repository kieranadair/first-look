"""Independent, small numerical oracles for consequential analytical choices."""

from copy import deepcopy
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from firstlook.analysis import analyze, compare
from firstlook.charts import options
from firstlook.data import load_table, profile, starting_requests
from firstlook.types import ChoiceRequired, Dataset, Field, Meaning, Request, TimeRule


def table(text):
    return load_table(text.encode(), "my-table.csv")


def test_upload_preserves_exact_values_and_labels_and_rejects_invalid_inputs(monkeypatch):
    ds = table(
        "customer_id,big,measure,measure,marker\n001,9007199254740993,1,2,NA\n002,9007199254740994,3,,NULL\n"
    )
    assert ds.frame["f000"].tolist() == ["001", "002"]
    assert ds.frame["f001"].tolist() == ["9007199254740993", "9007199254740994"]
    assert ds.field("f001").kind == "identifier"
    assert ds.label("f002") == "measure (column 3)"
    assert ds.label("f003") == "measure (column 4)"
    assert ds.frame["f004"].tolist() == ["NA", "NULL"]
    assert pd.isna(ds.frame.loc[1, "f003"])
    explicit = load_table(ds.raw, ds.name, missing_tokens=["NULL"])
    assert explicit.frame.loc[0, "f004"] == "NA" and pd.isna(explicit.frame.loc[1, "f004"])
    assert table("value\n1\nuncertain\n").frame["f000"].tolist() == ["1", "uncertain"]
    packed = BytesIO()
    pd.DataFrame({"value": [1, 2]}).to_parquet(packed, index=False)
    assert load_table(packed.getvalue(), "mine.parquet").frame["f000"].tolist() == [1, 2]
    packed = BytesIO()
    pd.DataFrame({"big": [9007199254740993, 9007199254740994]}).to_parquet(packed, index=False)
    exact = load_table(packed.getvalue(), "precise.parquet")
    assert exact.frame["f000"].tolist() == ["9007199254740993", "9007199254740994"]
    assert exact.field("f000").kind == "identifier"
    assert table("value\n1\n\n3\n").field("f000").missing == 1
    for invalid in [b"", b"PAR1broken", b"a\n"]:
        with pytest.raises(ValueError):
            load_table(invalid, "invalid.csv")
    monkeypatch.setattr("firstlook.data.MAX_BYTES", 5)
    with pytest.raises(ValueError, match="25 MiB"):
        load_table(b"value\n1\n", "large.csv")


def test_full_source_profiles_and_useful_initial_views_include_missingness():
    ds = table("amount,segment,other\n0,A,\n2,A,\n4,B,\n6,B,\n100,B,\n")
    facts = profile(ds)
    assert facts["rows"] == 5 and facts["missing"] == 5
    assert facts["fields"]["f000"]["mean"] == 22.4
    assert facts["fields"]["f000"]["median"] == 4
    assert [r.view for r in starting_requests(ds)] == ["distribution", "categories", "groups"]
    empty = Dataset(
        "empty-values",
        "missing-source",
        pd.DataFrame({"n": [np.nan, np.nan]}),
        [Field("n", "Quantity", "number", missing=2)],
    )
    assert starting_requests(empty)[0].view == "missingness"
    assert profile(empty)["fields"]["n"]["mean"] is None
    assert analyze(empty, Request("missingness")).summary["missing_cells"] == 2


def test_histogram_and_quantiles_use_all_nonmissing_source_values():
    ds = table("value,other\n0,a\n1,b\n2,c\n3,d\n4,e\n,f\n")
    result = analyze(ds, Request("distribution", "f000"))
    assert result.summary == {
        "n": 5,
        "missing": 1,
        "min": 0.0,
        "q1": 1.0,
        "median": 2.0,
        "mean": 2.0,
        "q3": 3.0,
        "max": 4.0,
    }
    assert result.omitted == 1 and result.meta["eligible_rows"] == [0, 1, 2, 3, 4]
    assert sum(r["count"] for r in result.table) == 5
    assert [r["count"] for r in result.table] == [2, 3]
    assert sum(r["share"] for r in result.table) == pytest.approx(1)
    assert result.meta["quantiles"][20] == {"probability": 0.5, "value": 2.0}
    quantiles = options(ds, analyze(ds, Request("distribution", "f000", representation="quantile")))
    assert quantiles["series"][0]["data"][20] == [2.0, 0.5]
    constant = table("quantity\n7\n7\n7\n")
    assert sum(r["count"] for r in analyze(constant, Request("distribution", "f000")).table) == 3


def test_additivity_and_value_grain_are_permissions_with_different_numerical_answers():
    ds = table("order_id,segment,amount\n001,A,100\n001,A,100\n002,B,60\n")
    req = Request("categories", "f001", "f002", metric="sum")
    with pytest.raises(ChoiceRequired, match="can be added"):
        analyze(ds, req)
    row_amount = analyze(ds, req, {"f002": Meaning("additive")})
    entity_amount = analyze(ds, req, {"f002": Meaning("additive", "f000")})
    assert sum(r["value"] for r in row_amount.table) == 260
    assert sum(r["value"] for r in entity_amount.table) == 160
    assert row_amount.context != entity_amount.context
    with pytest.raises(ChoiceRequired):
        analyze(ds, req, {"f002": Meaning("nonadditive")})
    changed = deepcopy(ds)
    changed.frame.loc[1, "f002"] = 101
    with pytest.raises(ChoiceRequired, match="varies within"):
        analyze(changed, req, {"f002": Meaning("additive", "f000")})
    mean = analyze(ds, Request("categories", "f001", "f002", metric="mean"))
    assert mean.table[0]["value"] == 100
    missing_entity = table("order_id,segment,amount\n001,A,100\n,A,30\n")
    identified = analyze(missing_entity, req, {"f002": Meaning("additive", "f000")})
    assert identified.table[0]["value"] == 100
    assert identified.meta["eligible_rows"] == [0] and identified.omitted == 1


def test_group_denominators_and_overlapping_entities_require_explicit_attribution():
    ds = table("order_id,category,amount,exposure\n001,A,100,2\n001,B,100,2\n002,A,60,1\n")
    counts = analyze(ds, Request("categories", "f001", metric="distinct", entity="f000"))
    assert {r["label"]: r["share"] for r in counts.table} == {"A": 1.0, "B": 0.5}
    assert not counts.meta["composition"] and counts.warnings
    req = Request("categories", "f001", "f002", metric="sum")
    meanings = {"f002": Meaning("additive", "f000")}
    with pytest.raises(ChoiceRequired) as blocked:
        analyze(ds, req, meanings)
    assert blocked.value.evidence["overlapping_entities"] == 1
    req.attribution = "equal"
    shared = analyze(ds, req, meanings)
    assert {r["label"]: r["value"] for r in shared.table} == {"A": 110.0, "B": 50.0}
    assert shared.meta["composition"]
    req.attribution = "full"
    full = analyze(ds, req, meanings)
    assert sum(r["value"] for r in full.table) == 260 and not full.meta["composition"]
    weighted = analyze(ds, Request("categories", "f001", "f002", metric="weighted_mean", weight="f003"))
    assert next(r["value"] for r in weighted.table if r["label"] == "A") == pytest.approx(260 / 3)
    invalid = deepcopy(ds)
    invalid.frame.loc[0, "f003"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        analyze(invalid, weighted.request)
    missing_group = table("value,segment\n1,A\n,B\n3,A\n")
    grouped = analyze(missing_group, Request("groups", "f000", group="f001"))
    absent = [r for r in grouped.table if r["label"] == "B"]
    assert absent and all(r["n"] == 0 and r["share"] is None for r in absent)


def test_relationship_separates_pooled_and_within_group_support_without_changing_source():
    ds = table("x,y,segment\n1,11,A\n2,12,A\n3,13,A\n10,1,B\n11,2,B\n12,3,B\n,4,B\n")
    original = ds.frame.copy(deep=True)
    result = analyze(ds, Request("relationship", "f000", "f001", group="f002"))
    assert result.summary["n"] == 6 and result.summary["correlation"] < -0.9
    assert [r["correlation"] for r in result.meta["group_stats"]] == pytest.approx([1, 1])
    assert result.meta["eligible_rows"] == list(range(6)) and result.omitted == 1
    assert [r["row"] for r in result.table] == list(range(6))
    chart = options(ds, result)
    assert chart["grid"]["width"] == chart["grid"]["height"]
    assert chart["grid"]["containLabel"] is False
    assert chart["grid"]["outerBoundsMode"] == "none"
    pd.testing.assert_frame_equal(ds.frame, original)


def test_time_absence_and_recorded_null_are_distinct_and_coverage_is_explicit():
    ds = table("date,amount\n2025-01-01,5\n2025-01-03,\n2025-01-05,2\n")
    meanings = {"f001": Meaning("additive")}
    req = Request("time", "f000", "f001", metric="sum", period="D")
    recorded = analyze(ds, req, meanings)
    assert [r["value"] for r in recorded.table] == [5.0, None, None, None, 2.0]
    assert [r["observed"] for r in recorded.table] == [True, False, True, False, True]
    req.zero_fill = True
    with pytest.raises(ChoiceRequired):
        analyze(ds, req, meanings)
    rules = {"f000": TimeRule(True, True, "2025-01-04")}
    filled = analyze(ds, req, meanings, time_rules=rules)
    assert [r["value"] for r in filled.table] == [5.0, 0, None, 0, 2.0]
    with pytest.raises(ChoiceRequired):
        analyze(ds, req, meanings, rows=[0, 2], time_rules=rules)
    req.period = "MS"
    partial = analyze(ds, req, meanings, time_rules={"f000": TimeRule(True, True, "2025-02-15")})
    assert partial.table[-1]["value"] is None, "A partial calendar month is not verified complete."
    req.zero_fill = False
    req.period = "D"
    assert options(ds, analyze(ds, req, meanings))["series"][0]["connectNulls"] is False
    req.zero_fill, req.representation = True, "calendar"
    with pytest.raises(ValueError, match="[Cc]alendar|heatmap|phase"):
        analyze(ds, req, meanings, time_rules=rules)


def test_selected_and_reference_are_matched_with_shared_domains_and_fixed_memberships():
    ds = table("x,y,group\n0,10,A\n1,20,A\n10,30,B\n11,40,B\n")
    original = ds.frame.copy(deep=True)
    distribution = compare(ds, Request("distribution", "f000"), [0, 1])
    assert distribution.selected.rows == [0, 1] and distribution.reference.rows == [2, 3]
    assert distribution.selected.meta["edges"] == distribution.reference.meta["edges"]
    assert [r["count"] for r in distribution.selected.table] == [2, 0]
    assert [r["count"] for r in distribution.reference.table] == [0, 2]
    unequal = compare(ds, Request("distribution", "f000"), [0])
    assert unequal.selected.meta["comparison_measure"] == "within-population share"
    assert unequal.selected.meta["y_bounds"] == unequal.reference.meta["y_bounds"]
    selected_chart = options(ds, unequal.selected)
    reference_chart = options(ds, unequal.reference)
    assert selected_chart["yAxis"]["max"] == reference_chart["yAxis"]["max"]
    assert [p[1] for p in selected_chart["series"][0]["data"]] == [r["share"] for r in unequal.selected.table]
    assert [p[1] for p in reference_chart["series"][0]["data"]] == [
        r["share"] for r in unequal.reference.table
    ]
    pairs = compare(ds, Request("relationship", "f000", "f001"), [0, 1])
    assert pairs.selected.meta["x_bounds"] == pairs.reference.meta["x_bounds"] == [0, 11]
    assert pairs.selected.meta["y_bounds"] == pairs.reference.meta["y_bounds"] == [10, 40]
    overlap = compare(ds, Request("distribution", "f000"), [0, 1], reference_rows=[1, 2, 3])
    assert "overlapping" in overlap.definition
    pd.testing.assert_frame_equal(ds.frame, original)


def test_conditional_representations_preserve_denominators_and_reject_false_composition():
    ds = table(
        "order_id,segment,status,amount,other\n001,A,Open,100,2\n001,B,Open,100,4\n002,A,Closed,60,6\n"
    )
    small = analyze(ds, Request("category_relationship", "f001", "f002", representation="share"))
    for group in ["A", "B"]:
        assert sum(r["share"] for r in small.table if r["group"] == group) == pytest.approx(1)
    assert all(a["max"] == 1 for a in options(ds, small)["xAxis"])
    counts = analyze(ds, Request("categories", "f001", representation="treemap"))
    assert sum(r["value"] for r in options(ds, counts)["series"][0]["data"]) == 3
    with pytest.raises(ValueError, match="partition"):
        incidence = analyze(
            ds, Request("categories", "f001", metric="distinct", entity="f000", representation="treemap")
        )
        options(ds, incidence)
    ranked = analyze(ds, Request("multivariate", group="f001", fields=["f003", "f004"], metric="mean"))
    assert [r["label"] for r in ranked.table] == ["B", "A"]
    assert len(options(ds, ranked)["series"]) == 2
