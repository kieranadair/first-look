"""Preparation is useful before confirmation and cannot manufacture analytical permissions."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from firstlook.contracts import Role
from firstlook.discovery import discover, analyze
from firstlook.evidence import export_bundle, import_bundle, read_bundle
from firstlook.ingest import from_frame
from firstlook.preparation import (
    apply_preparation,
    build_preparation,
    candidate_bundle,
    change_id,
    change_state,
    prepare_grain_answer,
    preparation_readiness,
    selection_closure,
    validate_preparation_evidence,
)
from firstlook.preparation_connected import (
    enrich_preparation,
    preparation_packet,
    preparation_sources,
    reconcile_interpretation,
)
from firstlook.preparation_contracts import PreparationDraft, PreparationInterpretation
from firstlook.preparation_templates import export_template, import_template
from firstlook.providers.base import ProviderError
from firstlook.semantic.model import configure_meaning, get_model
from firstlook.semantic.planner import metric_plan
from firstlook.state import Workspace


@pytest.fixture
def orders():
    frame = pd.DataFrame(
        {
            "order_id": ["A", "A", "B", "B", "C", "C"],
            "customer_id": ["U", "U", "V", "V", "W", "W"],
            "category": ["Office", "Home", "Office", "Home", "Office", "Home"],
            "sales": [10.0, 30.0, 20.0, 40.0, 10.0, 20.0],
            "shipping_charge": [5.0, 5.0, 7.0, 7.0, 9.0, 9.0],
            "quantity": [1, 3, 2, 4, 1, 2],
            "unit_price": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
            "order_date": pd.to_datetime(
                ["2026-01-01", "2026-01-01", "2026-01-03", "2026-01-03", "2026-01-05", "2026-01-05"]
            ),
        }
    )
    return from_frame(frame, "orders.csv", raw=frame.to_csv(index=False).encode())


def quantity_change(draft, fid):
    return next(c for c in draft.changes if c.kind == "quantity" and c.subject == fid)


def test_upload_draft_preserves_meaning_and_exposes_ready_operations(orders):
    before = orders.context().id
    draft = build_preparation(orders)
    assert orders.context().id == before
    assert not any(m.confirmed for m in get_model(orders).meanings)
    assert any(c.payload.get("aggregation") == "weighted_mean" for c in draft.changes)
    assert preparation_readiness(orders)["ready"]
    assert draft.telemetry["rows_checked"] == 6
    assert not any(q.get("property") == "availability" for q in draft.decisions)
    assert len(draft.changes) <= 140


def test_repeated_values_have_independent_numerical_oracles_and_source_memberships(orders):
    draft = build_preparation(orders, "shipping charge")
    witness = next(w for w in draft.evidence if w["fields"] == ["f000", "f004"])
    assert witness["row_sum"] == 42
    assert witness["once_per_entity_sum"] == 21
    assert witness["relative_difference"] == 0.5
    assert witness["valid_rows"] == 6 and witness["entities"] == 3
    assert all(orders.frame.at[r["source_row"], "f004"] == r["f004"] for r in witness["rows"])
    assert not any(
        c.suggested and c.payload.get("aggregation") == "sum" and c.payload.get("field") == "f004"
        for c in draft.changes
    )
    validate_preparation_evidence(orders, draft)


def test_one_explicit_answer_expands_dependencies_and_applies_once(orders):
    draft = build_preparation(orders)
    question = next(q for q in draft.decisions if q.get("entity") == "e_f000" and q["subject"] == "f004")
    draft, mid = prepare_grain_answer(orders, draft, question["id"], True)
    selected = selection_closure(draft, [mid])
    assert {c.kind for c in selected} == {"quantity", "metric", "entity"}
    before = orders.context().id
    apply_preparation(orders, draft, [mid])
    assert orders.context().id != before
    assert draft.telemetry["apply_transactions"] == 1
    assert get_model(orders).meaning("f004").confirmed
    metric_id = next(c.subject for c in selected if c.kind == "metric")
    result, _ = analyze(orders, orders.context(), metric_plan(orders, orders.context(), metric_id))
    assert float(result.records[0]["value"]) == 21
    assert not any(q.get("entity") and q["subject"] == "f004" for q in draft.decisions)
    assert len([a for a in get_model(orders).assertions if a.property == "prepared_bundle"]) == 1
    with pytest.raises(ValueError, match="already"):
        apply_preparation(orders, draft, [mid])


def test_stale_conflicting_edits_block_but_unrelated_edits_merge(orders):
    draft = build_preparation(orders)
    sales = quantity_change(draft, "f003")
    shipping = quantity_change(draft, "f006")
    configure_meaning(orders, "f003", "amount", "USD")
    assert change_state(orders, draft, sales) == "stale"
    assert change_state(orders, draft, shipping) == "ready"
    before = orders.context().id
    with pytest.raises(ValueError, match="changed"):
        apply_preparation(orders, draft, [sales.id, shipping.id])
    assert orders.context().id == before
    apply_preparation(orders, draft, [shipping.id])
    assert get_model(orders).meaning("f003").unit == "USD"
    assert get_model(orders).meaning("f006").confirmed


def test_bad_bundle_rolls_back_fields_and_contract(orders):
    draft = build_preparation(orders)
    metric = next(
        c
        for c in draft.changes
        if c.kind == "metric" and c.payload.get("aggregation") == "sum" and c.payload.get("field") == "f003"
    )
    quantity_change(draft, "f003").payload["kind"] = "state"
    before = orders.record.model_dump(mode="json")
    with pytest.raises(ValueError, match="not additive"):
        apply_preparation(orders, draft, [metric.id])
    assert orders.record.model_dump(mode="json") == before
    assert draft.applied == []


def test_exact_source_and_parser_scope_required(orders):
    draft = build_preparation(orders)
    other = from_frame(pd.DataFrame({"a": [1, 2, 3]}), "other.csv")
    with pytest.raises(ValueError, match="source bytes"):
        candidate_bundle(other, draft, [draft.changes[0].id])
    orders.record.parser["missing_tokens"] = ["", "NA"]
    with pytest.raises(ValueError, match="parsing"):
        candidate_bundle(orders, draft, [draft.changes[0].id])


def test_connected_explanation_yields_bundle_with_literal_evidence(orders):
    notes = "Each row is an order line. Sales is a line amount recorded in USD."
    draft = build_preparation(orders, "compare sales", preparation_sources(notes))
    response = PreparationInterpretation(
        summary="Order-line amounts and recorded identities; observation coverage remains unresolved.",
        quantities=[
            {
                "meaning": {"field": "f003", "kind": "flow", "currency": "USD"},
                "reason": "The supplied notes define line sales.",
                "evidence": [{"source": "notes", "quote": "Sales is a line amount recorded in USD."}],
            }
        ],
        grain={
            "description": "One order line",
            "entity": None,
            "reason": "Explicit row meaning.",
            "evidence": [{"source": "notes", "quote": "Each row is an order line."}],
        },
        selections=[
            {"candidate": change_id("metric", "m_total_f003"), "reason": "Sum the declared line amounts."}
        ],
    )
    result = reconcile_interpretation(orders, draft, response)
    assert not quantity_change(result, "f003").issue
    assert not get_model(orders).meaning("f003").confirmed
    apply_preparation(orders, result, [change_id("metric", "m_total_f003"), change_id("grain", "table")])
    assert get_model(orders).grain == "One order line"
    assert get_model(orders).meaning("f003").currency == "USD"
    assert get_model(orders).metric("m_total_f003").confirmed


@pytest.mark.parametrize(
    "quote,unit",
    [
        ("This passage does not exist", ""),
        ("Sales is a line amount.", "invented_unit"),
        ("Sales is a line amount.", "m"),
    ],
)
def test_models_cannot_invent_source_passages_or_units(orders, quote, unit):
    draft = build_preparation(orders, sources={"notes": "Sales is a line amount."})
    response = PreparationInterpretation(
        summary="A tentative interpretation.",
        quantities=[
            {
                "meaning": {"field": "f003", "kind": "flow", "unit": unit},
                "reason": "Candidate meaning.",
                "evidence": [{"source": "notes", "quote": quote}],
            }
        ],
    )
    result = reconcile_interpretation(orders, draft, response)
    c = quantity_change(result, "f003")
    assert c.issue
    with pytest.raises(ValueError):
        apply_preparation(orders, result, [c.id])


def test_provider_failure_keeps_local_draft_and_cancellation_skips_calls(orders):
    def fail(_):
        raise ProviderError("Provider unavailable")

    provider = SimpleNamespace(preparation=fail, records=[])
    draft = build_preparation(orders)
    enriched = enrich_preparation(orders, draft, provider)
    assert enriched.changes == draft.changes and "Provider unavailable" in enriched.errors
    assert enrich_preparation(orders, draft, provider, cancelled=lambda: True).errors == []


def test_source_limits_and_packet_omit_free_text_values(orders):
    with pytest.raises(ValueError, match="12,000"):
        preparation_sources(dictionary="x" * 12001)
    with pytest.raises(ValueError, match="16,000"):
        preparation_sources("x" * 9000, "y" * 9000)
    orders.field("f002").role = Role.TEXT
    packet = preparation_packet(orders, build_preparation(orders))
    assert "examples" not in next(f for f in packet["fields"] if f["id"] == "f002")
    assert len(json.dumps(packet)) <= 42000


def confirmed_orders(orders):
    draft = build_preparation(orders)
    ids = [change_id("quantity", "f003"), change_id("metric", "m_total_f003"), change_id("entity", "e_f000")]
    apply_preparation(orders, draft, ids)
    return orders


def test_templates_remap_column_positions_and_never_confirm_on_import(orders):
    confirmed_orders(orders)
    template = export_template(orders, "Orders export")
    original = pd.DataFrame({f.name: orders.frame[f.id].values for f in reversed(orders.record.fields)})
    newer = from_frame(original, "new-month.csv")
    draft = import_template(newer, template)
    sales = next(f.id for f in newer.record.fields if f.name == "sales")
    imported = next(
        c for c in draft.changes if c.kind == "quantity" and c.subject == sales and c.origin == "template"
    )
    assert not get_model(newer).meaning(sales).confirmed
    assert imported.payload["kind"] == "flow"
    metric = next(
        c
        for c in draft.changes
        if c.kind == "metric"
        and c.origin == "template"
        and c.payload.get("aggregation") == "sum"
        and c.payload.get("field") == sales
    )
    apply_preparation(newer, draft, [metric.id])
    assert get_model(newer).meaning(sales).confirmed
    assert not draft.telemetry["template"]["coverage_transferred"]


def test_template_type_drift_cannot_bind_old_position_to_different_field(orders):
    confirmed_orders(orders)
    template = export_template(orders)
    frame = pd.DataFrame(
        {"category": ["A", "B", "C"], "sales": ["bad", "worse", "unknown"], "another": [1, 2, 3]}
    )
    newer = from_frame(frame, "changed.csv")
    draft = import_template(newer, template)
    assert any("Physical type changed: sales" in e for e in draft.errors)
    assert not any(c.kind == "quantity" and c.origin == "template" for c in draft.changes)
    assert not any(
        c.kind == "metric" and c.origin == "template" and c.payload.get("aggregation") == "sum"
        for c in draft.changes
    )


def test_templates_exclude_time_coverage_and_availability_even_if_forged(orders):
    confirmed_orders(orders)
    raw = json.loads(export_template(orders))
    assert not any(d["kind"] in {"time", "availability", "task"} for d in raw["declarations"])
    raw["declarations"].append(
        {"kind": "availability", "subject": "f003", "payload": {"status": "known_at_anchor"}}
    )
    with pytest.raises(ValueError, match="cannot transfer"):
        import_template(orders, json.dumps(raw).encode())


def test_evidence_replays_preparation_and_verifies_source_examples(orders):
    ws = Workspace()
    ws.load(orders)
    ws.investigation = discover(orders, ws.context())
    bundle = export_bundle(ws, True)
    assert "profiles/preparation.json" in read_bundle(bundle)
    restored = import_bundle(bundle)
    assert restored.preparation == ws.preparation
    assert import_bundle(export_bundle(ws, False)).dataset.frame.empty
    tampered = deepcopy(ws.preparation)
    tampered["evidence"][0]["rows"][0][tampered["evidence"][0]["fields"][-1]] = 99999
    with pytest.raises(ValueError, match="disagrees"):
        validate_preparation_evidence(orders, tampered)


def test_native_review_context_reuse_and_atomic_apply(orders):
    ws = Workspace()
    ws.load(orders)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    app.switch_page("app_pages/preparation.py").run()
    assert not app.exception
    app.button(key="check_prepared_bundle").click().run()
    assert not app.exception
    assert app.success
    app.button(key="apply_prepared_bundle").click().run()
    assert not app.exception
    assert ws.preparation["applied"]
    app.segmented_control(key="preparation_mode").set_value("Context & documents").run()
    assert not app.exception
    app.text_input(key="preparation_goal").set_value("Compare sales")
    app.text_area(key="preparation_notes").set_value("Each row is an order line.")
    next(b for b in app.button if b.label == "Prepare this understanding").click().run()
    assert not app.exception and ws.preparation_inputs["notes"] == "Each row is an order line."
    app.segmented_control(key="preparation_mode").set_value("Reuse & record").run()
    assert not app.exception
    assert len(app.get("download_button")) == 2


def test_background_draft_preserves_concurrent_manual_declarations(orders):
    from firstlook.ui.runtime import accept_preparation

    ws = Workspace()
    ws.load(orders)
    draft = build_preparation(orders)
    draft.request = "controlled-request"
    configure_meaning(orders, "f003", "amount", "USD")
    accept_preparation(ws, draft.model_dump(mode="json"))
    assert get_model(orders).meaning("f003").unit == "USD"
    assert (
        change_state(orders, PreparationDraft.model_validate(ws.preparation), quantity_change(draft, "f003"))
        == "stale"
    )
    validate_preparation_evidence(orders, ws.preparation_history[0])


def test_preparation_request_deduplication_and_budget_survive_semantic_edits(orders, monkeypatch):
    from firstlook.ui import runtime
    from firstlook.config import Settings

    ws = Workspace()
    ws.load(orders)
    submitted = []
    manager = SimpleNamespace(submit=lambda *args: submitted.append(args) or "controlled-job")
    monkeypatch.setattr(runtime, "manager", lambda: manager)
    monkeypatch.setattr(runtime, "settings", lambda: Settings(openai_api_key="controlled-test-key"))
    monkeypatch.setattr(runtime, "st", SimpleNamespace(session_state={"external_ok": True}))
    runtime.start_preparation(ws)
    ws.job_id = None
    with pytest.raises(ValueError, match="already been attempted"):
        runtime.start_preparation(ws)
    for i in range(2):
        ws.preparation_inputs["notes"] = "New context " + str(i)
        runtime.start_preparation(ws)
        ws.job_id = None
    ws.invalidate()
    ws.preparation_inputs["notes"] = "Another context"
    with pytest.raises(ValueError, match="three connected"):
        runtime.start_preparation(ws)
    assert len(submitted) == 3


def test_undo_is_scoped_and_reusable_definitions_survive_matching_uploads(orders):
    from firstlook.ui.runtime import apply_prepared_bundle, undo_preparation

    ws = Workspace()
    ws.load(orders)
    before = get_model(orders).meaning("f003").model_dump()
    apply_prepared_bundle(ws, [change_id("quantity", "f003"), change_id("metric", "m_total_f003")])
    assert get_model(orders).meaning("f003").confirmed
    saved = export_template(orders, "Orders")
    undo_preparation(ws)
    assert get_model(orders).meaning("f003").model_dump() == before
    assert any(a.property == "undo_preparation" for a in get_model(orders).assertions)
    ws.preparation_templates = [{"name": "Orders", "data": saved}]
    df = pd.DataFrame({f.name: orders.frame[f.id].values for f in orders.record.fields})
    df["sales"] *= 2
    newer = from_frame(df, "new.csv", raw=df.to_csv(index=False).encode())
    ws.load(newer)
    assert ws.preparation["telemetry"]["template"]["name"] == "Orders"
    assert not get_model(newer).meaning("f003").confirmed


def test_parquet_embedded_dictionary_is_supplied_metadata_not_instructions():
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq
    from firstlook.ingest import load_table

    schema = pa.schema(
        [
            pa.field(
                "sales", pa.float64(), metadata={b"description": b"Amount on each line", b"currency": b"USD"}
            )
        ],
        metadata={b"description": b"One row per order line"},
    )
    table = pa.Table.from_pydict({"sales": [10.0, 20.0, 30.0]}, schema=schema)
    out = io.BytesIO()
    pq.write_table(table, out)
    ws = Workspace()
    ws.load(load_table(out.getvalue(), "orders.parquet"))
    assert "Amount on each line" in ws.preparation_inputs["dictionary"]
    assert "currency: USD" in ws.preparation["sources"]["dictionary"]
    assert not any(m.confirmed for m in get_model(ws.dataset).meanings)


def test_temporal_preparation_uses_its_declared_time_field():
    df = pd.DataFrame(
        {
            "account_id": ["A", "A", "B", "B", "C", "C"],
            "reading_date": pd.to_datetime(["2026-01-01", "2026-01-02"] * 3),
            "balance": [10.0, 12.0, 20.0, 18.0, 15.0, 16.0],
        }
    )
    ds = from_frame(df, "balances.csv")
    draft = build_preparation(ds)
    metric = next(
        c for c in draft.changes if c.kind == "metric" and c.payload.get("aggregation") == "snapshot_last"
    )
    apply_preparation(ds, draft, [metric.id])
    readiness = preparation_readiness(ds)
    assert next(m for m in readiness["ready"] if m["id"] == metric.subject)["time_field"] == "f001"
    result, _ = analyze(
        ds, ds.context(), metric_plan(ds, ds.context(), metric.subject, time_field="f001", period="D")
    )
    assert result.records[-1]["value"] == 46


def test_template_hierarchy_drift_is_explicit_and_blocked():
    df = pd.DataFrame(
        {"sku_id": ["p", "p", "q", "q"], "category": ["A", "A", "B", "B"], "sales": [10.0, 20.0, 30.0, 40.0]}
    )
    ds = from_frame(df, "catalog.csv")
    draft = build_preparation(ds)
    rel = next(c for c in draft.changes if c.kind == "relationship")
    apply_preparation(ds, draft, [rel.id])
    template = export_template(ds)
    df.loc[1, "category"] = "C"
    newer = from_frame(df, "new-catalog.csv")
    reused = import_template(newer, template)
    rel = next(c for c in reused.changes if c.kind == "relationship" and c.origin == "template")
    assert "violates" in rel.issue
    with pytest.raises(ValueError, match="violates"):
        apply_preparation(newer, reused, [rel.id])


def test_visual_preparation_has_matched_tables_and_bounded_images():
    from firstlook.preparation_connected import preparation_visuals
    from firstlook.examples import load_example

    ds = load_example("penguins")
    views, images = preparation_visuals(ds, build_preparation(ds))
    assert len(views) == len(images) == 2
    assert all(png.startswith(b"\x89PNG") for png in images)
    assert all(v["matched_records"] and v["plan"]["context"] == ds.context().id for v in views)


def test_local_overview_remains_available_during_connected_preparation(orders, monkeypatch):
    from firstlook.ui import runtime

    ws = Workspace()
    ws.load(orders)
    ws.job_id, ws.job_kind = "preparation-in-progress", "preparation"
    manager = SimpleNamespace(
        get=lambda *args: SimpleNamespace(state="running", stage="Preparing connected meaning")
    )
    monkeypatch.setattr(runtime, "manager", lambda: manager)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    assert not app.exception
    next(b for b in app.button if b.label == "Investigate this dataset").click().run()
    assert not app.exception and ws.investigation is not None
    assert ws.job_id == "preparation-in-progress" and ws.job_kind == "preparation"
