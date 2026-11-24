"""Streamlit state and navigation assertions; no image capture or live providers."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from firstlook.challenges import automatic_challenges
from firstlook.discovery import discover
from firstlook.examples import load_example
from firstlook.state import Workspace


def test_landing_example_and_semantic_form():
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30
    ).run()
    assert not app.exception
    assert len([b for b in app.button if b.label == "Explore example"]) == 3
    app.button(key="example_reversal").click().run()
    assert not app.exception
    assert app.metric[0].value == "600"
    assert len(app.get("data_editor")) == 1
    assert any(b.label == "Investigate this dataset" for b in app.button)


def test_all_work_areas_and_evidence_export():
    ws = Workspace()
    ws.load(load_example("reversal"))
    ws.investigation = discover(ws.dataset)
    automatic_challenges(ws.dataset, ws.investigation)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    assert not app.exception
    for page in ["app_pages/discover.py", "app_pages/challenge.py", "app_pages/evidence.py"]:
        app.switch_page(page).run()
        assert not app.exception
    leading = next((b for b in app.button if b.label == "Pin the leading observation"), None)
    if leading:
        leading.click().run()
    app.button(key="prepare_export").click().run()
    assert not app.exception
    assert app.session_state["prepared_bundle"].startswith(b"PK")


def test_context_change_invalidates_results_and_retains_evidence():
    from firstlook.state import pin

    ws = Workspace()
    ws.load(load_example("reversal"))
    ws.investigation = discover(ws.dataset)
    pin(ws, ws.investigation.findings[0].id)
    ctx = ws.context().id
    ws.rows = list(range(100))
    ws.invalidate()
    assert ws.context().id != ctx and ws.investigation is None
    assert ws.pins and ws.pins[0]["context"]["row_ids"] == list(range(600))


def test_meaning_workspace_confirm_define_and_run_metric():
    from firstlook.contracts import Role
    from firstlook.ingest import from_frame
    import pandas as pd

    df = pd.DataFrame(
        {
            "order_id": ["A", "A", "B", "C"],
            "category": ["Office", "Home", "Office", "Home"],
            "sales": [10.0, 30.0, 20.0, 40.0],
        }
    )
    ws = Workspace()
    ws.load(from_frame(df, "orders.csv", raw=df.to_csv(index=False).encode()))
    ws.dataset.field("f002").role = Role.MEASURE
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    app.switch_page("app_pages/meaning.py").run()
    assert not app.exception
    assert [t.label for t in app.tabs] == ["Decisions", "Metrics", "Structure & time", "Contract", "What if?"]
    quantity = next(s for s in app.selectbox if s.label == "What kind of quantity?")
    quantity.select("flow")
    next(b for b in app.button if b.label == "Confirm quantity meaning").click().run()
    assert not app.exception
    contract = app.session_state["workspace"].dataset.record.semantic_model
    assert contract.meaning("f002").confirmed
    app.selectbox(key="metric_existing").select("m_total_f002").run()
    app.button(key="confirm_existing_metric").click().run()
    assert not app.exception
    app.multiselect(key="metric_groups").set_value(["f001"]).run()
    app.button(key="compute_metric").click().run()
    assert not app.exception
    inv = app.session_state["workspace"].investigation
    assert inv.findings[0].family == "metric"
    assert sum(r["value"] for r in inv.results[inv.findings[0].result_id].records) == 100
    assert any(c.operation == "semantic_reconciliation" for c in inv.challenges)


def test_comparison_has_adjacent_visible_evidence_and_return_action():
    from firstlook.comparison import build_comparison, preview

    ws = Workspace()
    ws.load(load_example("semantic"))
    ws.investigation = discover(ws.dataset)
    ids = ws.dataset.frame.index[ws.dataset.frame["f004"].eq("Furniture")].tolist()
    preview(ws, ids, "predicate", "mapping")
    ws.comparison = build_comparison(ws.dataset, ws.selection, "ecdf", measure="f006")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run().switch_page("app_pages/compare.py").run()
    assert not app.exception and len(app.get("echarts_chart")) == 3
    assert any("Differences across" in m.value for m in app.markdown)
    assert not any("chart" in e.label.lower() for e in app.expander)
    app.button(key="filter_cohort").click().run()
    assert not app.exception and ws.rows == ids and ws.investigation is None
    app.switch_page("app_pages/discover.py").run()
    app.button(key="global_reset").click().run()
    assert not app.exception and ws.rows is None and ws.investigation is not None
    app.switch_page("app_pages/models.py").run()
    assert not app.exception


def test_changed_cohort_rejects_completed_earlier_comparison(monkeypatch):
    from types import SimpleNamespace
    from firstlook.comparison import build_comparison, preview
    import firstlook.ui.runtime as runtime

    ws = Workspace()
    ws.load(load_example("semantic"))
    ws.investigation = discover(ws.dataset)
    preview(ws, list(range(30)), "predicate", "mapping")
    old = build_comparison(ws.dataset, ws.selection, "ecdf", measure="f006")
    old_revision = ws.selection.revision
    preview(ws, list(range(40)), "predicate", "mapping")
    ws.job_id, ws.job_kind, ws.job_revision = "controlled", "comparison", old_revision
    job = SimpleNamespace(state="completed", context=ws.context().id, result=old)
    manager = SimpleNamespace(get=lambda *a: job, forget=lambda *a: None)
    monkeypatch.setattr(runtime, "manager", lambda: manager)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run()
    assert not app.exception and ws.comparison is None and ws.job_id is None


def test_recorded_models_show_related_diagnostics_without_reopening_configuration():
    from firstlook.modeling import run_model, diagnostic_findings

    ws = Workspace()
    ws.load(load_example("semantic"))
    ws.investigation = discover(ws.dataset)
    ws.model = run_model(ws.dataset, ws.context(), "f006", "group", "f001")
    diagnostic_findings(ws.dataset, ws.investigation, ws.model)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run().switch_page("app_pages/models.py").run()
    assert not app.exception and len(app.get("echarts_chart")) == 2
    assert len(app.get("multiselect")) == 0
    assert any("TRAIN /" in caption.value for caption in app.caption)
