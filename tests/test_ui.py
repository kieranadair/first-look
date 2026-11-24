"""Two complete native journeys, rather than a matrix of every widget permutation."""

from copy import deepcopy
from concurrent.futures import Future
from pathlib import Path

from streamlit.testing.v1 import AppTest

from firstlook.data import load_table
from firstlook.analysis import compare
from firstlook.types import Request
from firstlook.session import Session

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def own_data():
    state = Session()
    state.load(
        load_table(
            b"order_id,segment,amount,other\n001,A,100,1\n001,A,100,2\n002,B,60,3\n003,B,40,4\n",
            "my-orders.csv",
        )
    )
    return state


def controlled_reviews(monkeypatch):
    calls = []

    def review(ds, result, packet, settings):
        calls.append(deepcopy(packet))
        return {
            "status": "suggestion",
            "interpretation": "A controlled review of the current evidence.",
            "records": [{"provider": "Terra"}, {"provider": "Jev"}],
            "suggestions": [],
            "errors": [],
        }

    class Immediate:
        def submit(self, fn, *args, **kwargs):
            future = Future()
            try:
                future.set_result(fn(*args, **kwargs))
            except Exception as exc:
                future.set_exception(exc)
            return future

    monkeypatch.setattr("firstlook.ui.assist_view", review)
    monkeypatch.setattr("firstlook.ui.executor", lambda: Immediate())
    return calls


def test_reviews_start_automatically_without_setup_and_reuse_unchanged_evidence(monkeypatch):
    calls = controlled_reviews(monkeypatch)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception and app.title[0].value == "Hi, I’m First Look."
    assert len(app.get("file_uploader")) == 1 and not calls
    app.session_state["investigation"] = own_data()
    app.run()
    assert not app.exception and app.title[0].value == "Your table is ready."
    assert len(calls) == 1
    app.run().switch_page("app_pages/investigate.py").run()
    assert not app.exception and len(calls) == 1
    assert app.session_state["investigation"].assistance["interpretation"]
    assert len(app.get("echarts_chart")) == 1
    assert all(w.key not in {"consent", "use_hosted"} for w in app.checkbox)
    assert all(w.key != "ask_assistance" for w in app.button)
    state = app.session_state["investigation"]
    first = deepcopy(state.last_request)
    state.run(Request("categories", "f001"))
    app.run().run()
    assert len(calls) == 2
    state = app.session_state["investigation"]
    state.run(first)
    app.run()
    assert len(calls) == 2 and app.session_state["investigation"].assistance
    state.comparison = compare(state.ds, first, [0, 1], state.meanings)
    app.run().run()
    assert len(calls) == 3 and calls[-1]["displayed_evidence"] == "comparison"
    assert not app.exception


def test_consequential_choice_then_immutable_record_and_readable_export(monkeypatch):
    controlled_reviews(monkeypatch)
    app = AppTest.from_file(str(APP), default_timeout=20)
    app.session_state["investigation"] = own_data()
    app.run().switch_page("app_pages/investigate.py").run()
    next(w for w in app.selectbox if w.label == "Look from another angle").select("categories").run()
    next(w for w in app.selectbox if w.label == "Look at").select("f001")
    next(w for w in app.selectbox if w.label == "Compare").select("sum")
    next(w for w in app.selectbox if w.label == "Value, for a numerical summary").select("f002")
    next(b for b in app.button if b.label == "Look at this").click().run()
    app.radio(key="quantity_choice").set_value("An amount repeated from an identifier").run()
    app.selectbox(key="quantity_entity").select("f000").run()
    app.button(key="confirm_meaning").click().run()
    assert not app.exception and "waiting" not in app.session_state
    state = app.session_state["investigation"]
    assert sum(row["value"] for row in state.current.table) == 200
    app.button(key="keep_view").click().run()
    saved = deepcopy(app.session_state["investigation"].record[0])
    app.switch_page("app_pages/record.py").run()
    assert not app.exception
    app.text_area[0].input("Amounts belong once to each order; category totals reflect that grain.")
    next(b for b in app.button if b.label == "Keep this interpretation").click().run()
    app.button(key="prepare_record").click().run()
    assert not app.exception
    state = app.session_state["investigation"]
    assert state.record[0]["result"] == saved["result"]
    downloads = app.session_state["downloads"]
    assert downloads["bundle"].startswith(b"PK")
    assert "once to each order" in downloads["markdown"]
    assert len(app.get("download_button")) == 2
