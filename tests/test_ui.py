"""Two complete native journeys, rather than a matrix of every widget permutation."""

from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from firstlook.data import load_table
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


def test_welcome_and_own_data_start_are_useful_without_paid_work(monkeypatch):
    monkeypatch.setenv("FIRSTLOOK_PROVIDER_MODE", "offline")

    def forbidden(*args, **kwargs):
        raise AssertionError("Upload and ordinary reruns must not call providers.")

    monkeypatch.setattr("firstlook.ui.assist_view", forbidden)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    assert app.title[0].value == "Hi, I’m First Look."
    assert len(app.get("file_uploader")) == 1
    assert not app.get("download_button")
    app.session_state["investigation"] = own_data()
    app.run()
    assert not app.exception and app.title[0].value == "Your table is ready."
    assert app.session_state["investigation"].current.summary["n"] == 4
    app.switch_page("app_pages/investigate.py").run()
    assert not app.exception
    assert app.button(key="ask_assistance").disabled
    assert not app.session_state["investigation"].assistance_requests
    assert len(app.get("echarts_chart")) == 1


def test_consequential_choice_then_immutable_record_and_readable_export(monkeypatch):
    monkeypatch.setenv("FIRSTLOOK_PROVIDER_MODE", "offline")
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
