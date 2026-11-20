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
