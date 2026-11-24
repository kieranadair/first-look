"""Independent source, temporal and event-task oracles; no paid model calls."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from firstlook.analytical_tasks import (
    TaskDefinition,
    AvailabilityRule,
    save_task,
    save_availability,
    availability_decision,
    current_task,
)
from firstlook.contracts import Role, digest
from firstlook.discovery import discover, analyze
from firstlook.evidence import export_bundle, import_bundle, recompute
from firstlook.event_tasks import (
    EventTaskSpec,
    EventTaskRun,
    prepare_event_task,
    event_dataset,
    event_preflight,
    evaluate_event_task,
    validate_event_source,
)
from firstlook.examples import load_example
from firstlook.ingest import load_table, from_frame
from firstlook.model_protocol import model_preflight
from firstlook.modeling import run_model
from firstlook.recording_process import report, recording_plan
from firstlook.semantic.model import get_model
from firstlook.source_inspection import inspection_rows
from firstlook.state import Workspace


def test_large_and_leading_zero_identifiers_survive_missing_cells():
    raw = b"customer_id,code,measure\n9007199254740992,001,1\n9007199254740993,002,2\n,003,3\n"
    ds = load_table(raw, "identifiers.csv")
    assert ds.frame.f000.dropna().tolist() == ["9007199254740992", "9007199254740993"]
    assert ds.frame.f001.tolist() == ["001", "002", "003"]
    assert ds.frame.f000.nunique() == 2
    assert ds.record.source_profile["fields"]["f000"]["large_integer_strings"] == 1
    assert ds.record.parser["inference_version"] == 2


def test_large_unlabelled_integer_strings_are_preserved_too():
    ds = load_table(b"x\n9007199254740992\n9007199254740993\nmissing\n", "large.csv")
    assert ds.frame.f000.nunique() == 3
    assert ds.frame.f000.iloc[1] == "9007199254740993"


def test_legacy_parquet_missing_token_behavior_is_not_rewritten():
    import io

    stream = io.BytesIO()
    pd.DataFrame({"category": ["NA", "A", "B"]}).to_parquet(stream, index=False)
    old = load_table(stream.getvalue(), "old.parquet", missing_tokens=["", "NA"], inference_version=1)
    new = load_table(stream.getvalue(), "new.parquet", missing_tokens=["", "NA"])
    assert old.frame.f000.iloc[0] == "NA"
    assert pd.isna(new.frame.f000.iloc[0])


def test_source_candidates_do_not_change_the_missing_policy():
    ds = load_table(
        b"marker,amount,record_date\nNA,0,1900-01-01\nunknown,-1,2024-01-01\nNull,999,2024-01-02\n,20,2024-01-03\n",
        "markers.csv",
    )
    assert ds.frame.f000.iloc[:3].tolist() == ["NA", "unknown", "Null"]
    assert ds.frame.f001.tolist() == [0, -1, 999, 20]
    assert ds.record.source_profile["fields"]["f002"]["placeholder_dates"] == [
        {"value": "1900-01-01", "count": 1}
    ]
    assert {r["value"] for r in ds.record.source_profile["fields"]["f000"]["markers"]} == {
        "NA",
        "unknown",
        "",
    }
    assert len(inspection_rows(ds)) == 3


def test_long_digit_identifiers_need_no_machine_integer_conversion():
    value = "9" * 5000
    ds = load_table(("customer_id\n" + value + "\n").encode(), "long-key.csv")
    assert ds.frame.f000.iloc[0] == value


def test_changing_decision_time_requires_availability_review_again():
    ds = model_table()
    save_task(
        ds,
        TaskDefinition(
            dataset=ds.record.fingerprint, purpose="prediction", target="f004", decision_time="After delivery"
        ),
    )
    save_availability(ds, AvailabilityRule(field="f002", status="known_at_anchor"))
    assert availability_decision(ds, "f002", ds.frame)[0] == "allowed"
    save_task(
        ds,
        TaskDefinition(
            dataset=ds.record.fingerprint,
            purpose="prediction",
            target="f004",
            decision_time="At order placement",
        ),
    )
    assert availability_decision(ds, "f002", ds.frame)[0] == "excluded"
    assert any(q.id == "q_availability_f002" for q in get_model(ds).clarifications)


def test_recorded_preflight_cannot_disagree_with_executed_membership():
    from firstlook.model_protocol import validate_recorded_protocol

    ds = model_table()
    run = run_model(ds, ds.context(), "f004")
    assert validate_recorded_protocol(run)
    bad = run.model_copy(deep=True)
    bad.parameters["readiness"]["train_ids"] = bad.train_ids[:-1]
    with pytest.raises(ValueError, match="disagree"):
        validate_recorded_protocol(bad)


def test_legacy_inference_and_context_are_replayable():
    from firstlook.semantic.profile import build_model

    ds = load_table(
        b"customer_id,amount\n9007199254740992,10\n9007199254740993,20\n,30\n", "old.csv", inference_version=1
    )
    assert ds.frame.f000.nunique() == 1
    ds.record.parser.pop("inference_version")
    ds.record.source_profile = {}
    ds.record.semantic_model = build_model(ds)
    ws = Workspace()
    ws.load(ds)
    ws.investigation = discover(ds, ws.context())
    imported = import_bundle(export_bundle(ws, True))
    assert imported.dataset.frame.f000.nunique() == 1
    assert imported.context().id == ws.context().id
    assert all(r["status"] == "match" for r in recompute(imported))


def model_table():
    rng = np.random.default_rng(821)
    dates = pd.date_range("2024-01-01", periods=300, tz="UTC")
    return from_frame(
        pd.DataFrame(
            {
                "anchor_timestamp": dates,
                "known_timestamp": dates + pd.Timedelta(1, unit="D"),
                "signal": rng.normal(size=300),
                "extra": rng.normal(size=300),
                "outcome": rng.normal(size=300),
            }
        ),
        "protocol.csv",
    )


def test_task_revisions_invalidate_context_and_roundtrip():
    ds = model_table()
    old = ds.context().id
    task = TaskDefinition(
        dataset=ds.record.fingerprint,
        purpose="prediction",
        question="Predict outcome at the anchor",
        target="f004",
        anchor_field="f000",
        decision_time="At the anchor",
    )
    save_task(ds, task)
    assert ds.context().id != old
    assert current_task(ds) == task
    assert any(q.property == "availability" for q in get_model(ds).clarifications)
    assert model_preflight(ds, ds.context(), "f004")["status"] == "blocked"
    save_availability(
        ds, AvailabilityRule(field="f002", status="known_at_anchor", evidence="Collection documentation")
    )
    ready = model_preflight(ds, ds.context(), "f004")
    assert ready["status"] == "ready_for_declared_protocol"
    assert ready["predictors"] == ["f002"]


def test_late_and_unknown_availability_cannot_become_predictors():
    ds = model_table()
    task = TaskDefinition(
        dataset=ds.record.fingerprint, purpose="prediction", target="f004", anchor_field="f000"
    )
    save_task(ds, task)
    save_availability(ds, AvailabilityRule(field="f002", status="after_timestamp", timestamp="f001"))
    status, reason = availability_decision(ds, "f002", ds.frame)
    assert status == "excluded" and "300" in reason
    assert model_preflight(ds, ds.context(), "f004")["status"] == "blocked"


def test_mutable_latest_values_require_historical_versions_for_prediction():
    ds = model_table()
    save_availability(ds, AvailabilityRule(field="f002", status="known_at_anchor", mutable=True))
    assert availability_decision(ds, "f002", ds.frame)[0] == "assumption"
    save_task(
        ds,
        TaskDefinition(
            dataset=ds.record.fingerprint,
            purpose="prediction",
            target="f004",
            decision_time="Before the outcome",
        ),
    )
    assert availability_decision(ds, "f002", ds.frame)[0] == "excluded"
    save_availability(
        ds, AvailabilityRule(field="f002", status="known_at_anchor", mutable=True, history_available=True)
    )
    assert availability_decision(ds, "f002", ds.frame)[0] == "allowed"


def test_preflight_and_fit_have_identical_memberships_and_model_projection():
    ds = model_table()
    ready = model_preflight(ds, ds.context(), "f004", "time", "f000")
    run = run_model(ds, ds.context(), "f004", "time", "f000")
    assert ready["train_ids"] == run.train_ids and ready["test_ids"] == run.test_ids
    assert ready["predictors"] == run.predictors
    assert ready["status"] == "diagnostic_with_assumptions"
    assert set(run.metrics) >= {"Dummy", "Median", "Linear", "Gradient boosting"}
    for rows in run.parameters["predictions_by_model"].values():
        assert [r["row_id"] for r in rows] == run.test_ids
    train_mean = ds.frame.loc[run.train_ids, "f004"].mean()
    train_median = ds.frame.loc[run.train_ids, "f004"].median()
    assert all(
        r["predicted"] == pytest.approx(train_mean) for r in run.parameters["predictions_by_model"]["Dummy"]
    )
    assert all(
        r["predicted"] == pytest.approx(train_median)
        for r in run.parameters["predictions_by_model"]["Median"]
    )


def test_final_test_targets_do_not_control_predictor_screening():
    ds = model_table()
    # A predictor that copies the target only in training must be screened in both cases.
    ds.frame.loc[:209, "f002"] = ds.frame.loc[:209, "f004"]
    before = model_preflight(ds, ds.context(), "f004", "time", "f000")
    ds.frame.loc[210:, "f004"] = 1000 + np.arange(90)
    after = model_preflight(ds, ds.context(), "f004", "time", "f000")
    assert "f002" not in before["predictors"]
    assert before["predictors"] == after["predictors"]


def test_forward_window_censoring_and_training_label_purge():
    ds = model_table()
    save_task(
        ds,
        TaskDefinition(
            dataset=ds.record.fingerprint,
            purpose="prediction",
            target="f004",
            anchor_field="f000",
            horizon_days=10,
            complete_through="2024-10-26T00:00:00Z",
        ),
    )
    save_availability(ds, AvailabilityRule(field="f002", status="known_at_anchor"))
    report = model_preflight(ds, ds.context(), "f004", "time", "f000")
    assert report["incomplete_window_rows"] == 10
    assert report["purged_training_rows"] == 9
    assert report["status"] == "diagnostic_with_assumptions"
    assert any("Training label availability" in a["reason"] for a in report["assumptions"])
    boundary = ds.frame.loc[report["test_ids"], "f000"].min()
    assert (ds.frame.loc[report["train_ids"], "f000"] + pd.Timedelta(10, unit="D") <= boundary).all()


def test_blocked_preflight_never_calls_a_provider():
    ds = model_table()
    save_task(
        ds,
        TaskDefinition(
            dataset=ds.record.fingerprint,
            purpose="prediction",
            target="f004",
            decision_time="Before the outcome",
        ),
    )

    class MustNotCall:
        def predict(self, *args):
            raise AssertionError("Provider called for an invalid task")

    with pytest.raises(ValueError, match="No eligible predictors"):
        run_model(ds, ds.context(), "f004", provider=MustNotCall())


def test_recording_coverage_uses_full_scoped_denominators():
    raw = b"record_date,value,group\n2024-01-01,1,A\n2024-01-01,,A\n2024-02-01,,B\n2024-02-01,,B\n,9,A\n"
    ds = load_table(raw, "coverage.csv")
    packet = report(ds, ds.context(), fields=["f001"])
    assert packet["active_rows"] == 5 and packet["undated_rows"] == 1
    assert [(r["rows"], r["missing"], r["missing_share"]) for r in packet["time"]] == [(2, 1, 0.5), (2, 2, 1)]
    assert packet["flags"][0]["range"] == 0.5
    subset = report(ds, ds.context([0, 1]), fields=["f001"])
    assert subset["active_rows"] == 2 and len(subset["time"]) == 1
    result, finding = analyze(ds, ds.context(), recording_plan(ds, ds.context(), ["f001"]))
    assert result.support == 4 and result.missing == 1
    assert {i for row in result.records for i in row["row_ids"]} == {0, 1, 2, 3}
    assert "not" in finding.observation


def small_events():
    data = pd.DataFrame(
        {
            "customer_id": ["A", "A", "A", "A", "A", "B"],
            "event_id": ["e1", "e2", "e2", "e3", "e4", "e5"],
            "event_timestamp": [
                "2024-01-05",
                "2024-01-12",
                "2024-01-12",
                "2024-01-20",
                "2024-01-22",
                "2024-01-14",
            ],
            "known_timestamp": [
                "2024-01-05",
                "2024-01-12",
                "2024-01-12",
                "2024-01-21",
                "2024-01-22",
                "2024-01-14",
            ],
        }
    )
    return load_table(data.to_csv(index=False).encode(), "events.csv")


def test_duplicate_source_labels_remain_distinct_in_coverage_encoding():
    ds = load_table(b"record_date,x,x\n2024-01-01,1,\n2024-01-02,,2\n", "duplicate-labels.csv")
    result, _ = analyze(ds, ds.context(), recording_plan(ds, ds.context(), ["f001", "f002"]))
    assert {r["y"] for r in result.records} == {"x [column 2]", "x [column 3]"}


@pytest.mark.parametrize("timezone", ["UTC", "America/New_York"])
def test_complete_calendar_date_uses_the_aware_observation_clock(timezone):
    from firstlook.semantic.model import commit_model
    from firstlook.semantic.planner import metric_plan

    ds = from_frame(
        pd.DataFrame(
            {"event_timestamp": pd.date_range("2024-01-01", periods=3, tz=timezone), "group": ["A", "B", "A"]}
        ),
        "clock.csv",
    )
    model = get_model(ds).model_copy(deep=True)
    policy = model.time_policies[0]
    policy.kind, policy.coverage_complete, policy.confirmed, policy.complete_through = (
        "event",
        True,
        True,
        "2024-01-03",
    )
    commit_model(ds, model)
    result, _ = analyze(
        ds, ds.context(), metric_plan(ds, ds.context(), "m_rows", time_field="f000", period="D")
    )
    assert [r["value"] for r in result.records] == [1, 1, 1]
    assert all(r["complete"] for r in result.records)


def test_event_example_supports_ordinary_discovery_and_recording_challenges():
    from firstlook.challenges import automatic_challenges

    ds = load_example("events")
    inv = discover(ds)
    assert inv.findings and any(f.family == "recording" for f in inv.findings)
    assert next(r for r in inv.coverage if r["family"] == "Data and meaning fitness")["computed"] >= 1
    automatic_challenges(ds, inv)
    assert sum(c.operation == "recording_process" for c in inv.challenges) == 1


def small_spec(ds, **changes):
    data = dict(
        dataset=ds.record.fingerprint,
        entity="f000",
        event_id="f001",
        event_time="f002",
        known_time="f003",
        lookback_days=20,
        horizon_days=10,
        reporting_delay_days=1,
        anchors=["2024-01-10", "2024-01-20", "2024-01-30"],
        complete_through="2024-02-09",
        coverage_confirmed=True,
    )
    data.update(changes)
    return EventTaskSpec(**data)


def test_event_oracle_strict_boundaries_delays_duplicates_and_past_population():
    ds = small_events()
    original = ds.record.model_dump()
    run = prepare_event_task(ds, ds.context(), small_spec(ds))
    a = [r for r in run.records if r["Entity"] == "A"]
    assert [r["Historical events"] for r in a] == [1, 2, 3]
    assert [r["Outcome"] for r in a] == [1, 1, 0]
    assert [r["Events in previous window"] for r in a] == [1, 1, 1]
    assert run.preparation["deduplicated_source_rows"] == 1
    assert [(r["Entity"], r["Anchor timestamp"]) for r in run.records][:1] == [
        ("A", "2024-01-10T00:00:00+00:00")
    ]
    assert run.memberships[0]["history_rows"] == [0]
    assert run.memberships[0]["outcome_rows"] == [1, 2, 3]
    assert 3 not in next(
        m["history_rows"]
        for m in run.memberships
        if m["entity"] == "A" and m["anchor"].startswith("2024-01-20")
    )
    assert ds.record.model_dump() == original
    assert validate_event_source(ds, run)


def test_event_count_uses_distinct_events_not_duplicate_rows():
    ds = small_events()
    run = prepare_event_task(ds, ds.context(), small_spec(ds, recipe="event_count"))
    assert [r["Outcome"] for r in run.records if r["Entity"] == "A"] == [2, 1, 0]
    assert event_dataset(run).field("f007").role == Role.MEASURE


def test_event_training_excludes_labels_not_yet_known_at_the_final_anchor():
    ds = small_events()
    run = prepare_event_task(ds, ds.context(), small_spec(ds))
    assert run.preparation["purged_training_rows"] == 2
    assert run.train_ids == [0]
    assert all(
        pd.Timestamp(run.records[i]["Anchor timestamp"]) + pd.Timedelta(11, unit="D")
        <= pd.Timestamp("2024-01-30", tz="UTC")
        for i in run.train_ids
    )


def test_observed_outcome_reporting_delay_cannot_exceed_the_attested_bound():
    ds = small_events()
    with pytest.raises(ValueError, match="reporting delays exceed"):
        prepare_event_task(ds, ds.context(), small_spec(ds, reporting_delay_days=0))


@pytest.mark.parametrize(
    "changes",
    [
        {"coverage_confirmed": False},
        {"known_time": None, "available_at_event": False},
        {"anchors": ["2024-01-10", "2024-01-15", "2024-01-30"]},
        {"lookback_days": 5},
    ],
)
def test_event_invalid_assumptions_and_overlapping_windows_rejected(changes):
    with pytest.raises(ValueError):
        small_spec(small_events(), **changes)


def test_incomplete_event_windows_are_omitted_not_negative_labels():
    ds = small_events()
    run = prepare_event_task(
        ds, ds.context(), small_spec(ds, anchors=["2024-01-10", "2024-01-20", "2024-01-30", "2024-02-09"])
    )
    assert len(run.preparation["censored_anchors"]) == 1
    assert all(not r["Anchor timestamp"].startswith("2024-02-09") for r in run.records)
    with pytest.raises(ValueError, match="three complete"):
        prepare_event_task(ds, ds.context(), small_spec(ds, complete_through="2024-02-01"))


def test_future_only_perturbation_cannot_change_past_features():
    ds = small_events()
    before = prepare_event_task(ds, ds.context(), small_spec(ds))
    altered = ds.frame.copy()
    altered.columns = [f.name for f in ds.record.fields]
    altered.loc[4, "event_timestamp"] = pd.Timestamp("2024-02-01")
    modified = from_frame(altered, "modified.csv")
    after = prepare_event_task(modified, modified.context(), small_spec(modified))

    def first_a(r):
        return next(
            {k: v for k, v in row.items() if k != "Outcome"}
            for row in r.records
            if row["Entity"] == "A" and row["Anchor timestamp"].startswith("2024-01-10")
        )

    assert first_a(before) == first_a(after)


def test_event_conflicting_identity_cannot_be_deduplicated():
    ds = small_events()
    ds.frame.loc[2, "f000"] = "Different entity"
    with pytest.raises(ValueError, match="different entities"):
        prepare_event_task(ds, ds.context(), small_spec(ds))


def test_unknown_knowledge_time_excludes_a_feature_event_but_not_its_observed_outcome():
    ds = small_events()
    ds.frame.loc[4, "f003"] = pd.NaT
    run = prepare_event_task(ds, ds.context(), small_spec(ds))
    a = [r for r in run.records if r["Entity"] == "A"]
    assert a[1]["Outcome"] == 1  # The Jan 22 event is observed even though its knowledge time is unknown.
    assert a[2]["Historical events"] == 2  # It cannot be used as a known historical feature.
    assert run.preparation["unknown_availability_source_rows"] == 1


def test_unassignable_events_cannot_silently_create_negative_labels():
    ds = small_events()
    ds.frame.loc[4, "f002"] = pd.NaT
    with pytest.raises(ValueError, match="silently dropped"):
        prepare_event_task(ds, ds.context(), small_spec(ds))


def test_tampered_event_table_and_memberships_are_rejected():
    ds = small_events()
    run = prepare_event_task(ds, ds.context(), small_spec(ds))
    payload = run.model_dump(mode="json")
    payload["records"][0]["Historical events"] = 100
    with pytest.raises(ValueError, match="changed"):
        EventTaskRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["memberships"][0]["history_rows"] = [9999]
    with pytest.raises(ValueError, match="invalid source"):
        EventTaskRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["records"][0]["Outcome"] = 0
    payload["table_hash"] = digest(payload["records"])
    payload["id"] = digest([run.source_context.id, run.spec.model_dump(), payload["table_hash"]])
    with pytest.raises(ValueError, match="disagree"):
        validate_event_source(ds, EventTaskRun.model_validate(payload))


def test_event_evidence_roundtrip_with_and_without_source():
    ds = small_events()
    ws = Workspace()
    ws.load(ds)
    ws.investigation = discover(ds, ws.context())
    run = prepare_event_task(ds, ws.context(), small_spec(ds))
    ws.event_runs = [run.model_dump(mode="json")]
    for include in [False, True]:
        imported = import_bundle(export_bundle(ws, include))
        assert imported.event_runs[0]["id"] == run.id
        assert event_dataset(imported.event_runs[0]).context().id == run.derived_context.id
        if include:
            assert all(r["status"] == "match" for r in recompute(imported))


def test_event_model_uses_last_anchor_and_keeps_all_comparators():
    ds = load_example("events")
    fields = {f.name: f.id for f in ds.record.fields}
    spec = EventTaskSpec(
        dataset=ds.record.fingerprint,
        entity=fields["customer_id"],
        event_id=fields["event_id"],
        event_time=fields["event_timestamp"],
        known_time=fields["available_timestamp"],
        anchors=["2024-04-01", "2024-05-01", "2024-05-31"],
        horizon_days=30,
        reporting_delay_days=2,
        lookback_days=90,
        complete_through="2024-08-27T23:59:59Z",
        coverage_confirmed=True,
    )
    run = prepare_event_task(ds, ds.context(), spec)
    assert event_preflight(run)["status"] == "ready_for_declared_protocol"
    result = evaluate_event_task(run)
    assert result.model.test_ids == run.test_ids
    assert all(result.records[i]["Anchor timestamp"].startswith("2024-05-31") for i in run.test_ids)
    assert "Previous window" in result.model.metrics
    with pytest.raises(ValueError, match="already"):
        evaluate_event_task(result)


def test_event_state_preserves_reference_and_resets_on_semantic_change():
    from firstlook.comparison import make_selection

    ws = Workspace()
    ws.load(load_example("penguins"))
    ws.investigation = discover(ws.dataset, ws.context())
    ws.event_runs = [{"id": "saved"}]
    ws.event_prepare_count = 1
    ws.selection = make_selection(
        ws.dataset, ws.context(), ws.context().row_ids[:40], "predicate", "mapping", 1
    )
    ws.begin_filtered()
    assert not ws.event_runs
    ws.return_to_anchor()
    assert ws.event_runs == [{"id": "saved"}] and ws.event_prepare_count == 1
    ws.invalidate()
    assert not ws.event_runs and ws.event_prepare_count == 0


def test_native_task_availability_models_and_recording_pages():
    ws = Workspace()
    ws.load(load_example("penguins"))
    ws.investigation = discover(ws.dataset, ws.context())
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    app.switch_page("app_pages/meaning.py").run()
    assert not app.exception
    assert "Task & availability" in [t.label for t in app.tabs]
    app.switch_page("app_pages/models.py").run()
    assert not app.exception
    assert any("Before fitting" in m.value for m in app.markdown)
    app.switch_page("app_pages/event_lab.py").run()
    assert not app.exception


def test_native_prepared_event_task_and_offline_evidence_inspection():
    ds = small_events()
    ws = Workspace()
    ws.load(ds)
    ws.investigation = discover(ds, ws.context())
    ws.event_runs = [prepare_event_task(ds, ws.context(), small_spec(ds)).model_dump(mode="json")]
    ws = import_bundle(export_bundle(ws, False))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    app.switch_page("app_pages/event_lab.py").run()
    assert not app.exception
    assert any("derived records" in m.value.lower() for m in app.markdown)
