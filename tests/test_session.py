"""State, bounded requests and portable evidence; no UI implementation fixtures."""

from copy import deepcopy
import hashlib
from io import BytesIO
import json
import zipfile

import pytest

from firstlook.analysis import compare
from firstlook.data import load_table
from firstlook.evidence import export, inspect_bundle, readable_markdown
from firstlook.session import Session
from firstlook.types import Meaning, Request, TimeRule


def investigation():
    session = Session()
    session.load(
        load_table(
            b"order_id,segment,amount,date\n001,A,100,2025-01-01\n001,A,100,2025-01-02\n002,B,60,2025-01-03\n",
            "my-orders.csv",
        )
    )
    return session


def rewrite_archive(blob, changes, recompute=False):
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files.update(changes)
    if recompute:
        files["checksums.json"] = json.dumps(
            {
                name: hashlib.sha256(data).hexdigest()
                for name, data in files.items()
                if name != "checksums.json"
            }
        ).encode()
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def test_meaning_and_population_changes_invalidate_work_without_rewriting_saved_evidence():
    session = investigation()
    session.question = "How do recorded amounts differ?"
    session.run(Request("categories", "f001", "f002", metric="mean"))
    saved_id = session.save_result("These are recorded rows; I need to check order grain.")
    saved = deepcopy(session.record[0])
    context = session.context
    session.declare("f002", Meaning("additive", "f000", "GBP", "Once per order"))
    assert session.context != context and session.current is None
    assert session.record[0] == saved
    session.run(Request("categories", "f001", "f002", metric="sum"))
    assert sum(r["value"] for r in session.current.table) == 160
    session.set_rows([0, 1])
    assert session.current is None and session.rows == [0, 1]
    session.reset()
    assert session.rows is None and session.record[0] == saved
    session.update_note(saved_id, "I verified each order amount is repeated.")
    assert session.record[0]["result"] == saved["result"]
    assert "I verified each order amount" in readable_markdown(session)


def test_failed_or_stale_choices_and_provider_responses_do_not_partially_mutate_state():
    session = investigation()
    old_context = session.context
    before = deepcopy(session.__dict__)
    for fid, meaning in [("f001", Meaning("additive")), ("f002", Meaning("additive", "f002"))]:
        with pytest.raises(ValueError):
            session.declare(fid, meaning)
        assert session.meanings == before["meanings"] and session.current == before["current"]
    with pytest.raises(ValueError, match="valid last complete date"):
        session.set_time_rule("f003", TimeRule(True, True, "NaT"))
    assert not session.time_rules
    session.declare("f002", Meaning("additive", "f000"))
    with pytest.raises(ValueError, match="earlier view"):
        session.declare("f002", Meaning("nonadditive"), expected_context=old_context)
    assert session.meanings["f002"].kind == "additive"
    with pytest.raises(ValueError, match="value entity"):
        session.set_role("f000", "text")
    assert session.ds.field("f000").kind == "identifier"
    session.run(Request("distribution", "f002"))
    pending = session.begin_assistance("first", consent=True)
    session.question = "A changed question"
    assert not session.accept_assistance({"interpretation": "old"}, pending)
    assert not session.assistance and not session.provider_history
    current = session.begin_assistance("next", consent=True)
    assert session.accept_assistance({"interpretation": "current", "context": "untrusted"}, current)
    assert session.provider_history[-1]["context"] == current
    pending_whole = session.begin_assistance("whole-view", consent=True)
    session.comparison = compare(session.ds, session.current.request, [0, 1], session.meanings)
    assert not session.accept_assistance({"interpretation": "Only the whole view"}, pending_whole)
    session.set_rows([0, 1])
    assert not session.accept_prediction({"models": []}, old_context)
    assert not session.prediction


def test_request_consent_deduplication_and_dataset_budgets_survive_ordinary_edits():
    session = investigation()
    with pytest.raises(ValueError, match="sharing"):
        session.begin_assistance("first")
    assert not session.assistance_requests
    session.begin_assistance("first", consent=True)
    with pytest.raises(ValueError, match="already been attempted"):
        session.begin_assistance("first", consent=True)
    session.begin_prediction()
    session.declare("f002", Meaning("additive"))
    session.question = "Another question"
    session.set_rows([0, 1])
    for key in ["second", "third", "fourth"]:
        session.begin_assistance(key, consent=True)
    with pytest.raises(ValueError, match="four assistance"):
        session.begin_assistance("fifth", consent=True)
    with pytest.raises(ValueError, match="already used"):
        session.begin_prediction()
    replacement = load_table(b"quantity\n1\n2\n", "next.csv")
    session.load(replacement)
    assert session.ds.fingerprint == replacement.fingerprint
    assert not session.assistance_requests and not session.prediction_used
    assert not session.record and not session.meanings and session.rows is None
    assert session.question == "" and session.notes == "" and session.current is not None


def test_evidence_inspection_exact_source_replay_and_tamper_rejection():
    session = investigation()
    session.run(Request("distribution", "f002"))
    session.comparison = compare(session.ds, session.last_request, [0, 1], session.meanings)
    session.save_result("Check the complete distribution as well as the means.")
    session.run(Request("category_relationship", "f001", "f000", representation="share"))
    session.save_result()
    session.run(Request("time", "f003", metric="count", period="D", representation="share"))
    session.save_result()
    session.run(Request("distribution", "f002", representation="quantile"))
    session.save_result()
    session.run(Request("time", "f003", metric="count", period="D", representation="calendar"))
    session.save_result("<script>not executable</script> [literal note](https://untrusted.invalid)")
    session.prediction = {
        "target": "f002",
        "predictors": ["f001"],
        "split": "group",
        "split_field": "f000",
        "train_ids": [0, 1],
        "test_ids": [2],
        "models": [{"name": "Reference", "metric": "MAE", "score": 40.0}],
        "warnings": ["An illustrative saved prediction record."],
        "definition": "Fixed recorded holdout.",
    }
    without_source = export(session)
    inspected = inspect_bundle(without_source)
    assert not inspected["source_verified"] and len(inspected["record"]) == 5
    assert inspected["record"][0] == session.record[0]
    readable = inspected["readable_markdown"]
    assert "My First Look" in readable
    assert "### Selected population" in readable and "### Reference population" in readable
    assert "Population: 2 recorded rows" in readable and "Population: 1 recorded rows" in readable
    assert "Plotted values" in readable and "0.33333333" in readable
    assert "Plotted quantiles" in readable and "first 20 of 41 rows" in readable
    assert "Plotted weekday/hour cells" in readable and "Wednesday" in readable
    assert "| Reference | MAE | 40 |" in readable and "Holdout: group by order" in readable
    assert "f002" not in readable and "| row" not in readable.lower()
    assert "<script>" not in readable and "[literal note](https://untrusted.invalid)" not in readable
    assert "&lt;script&gt;" in readable and "\\[literal note\\]" in readable
    replayed = inspect_bundle(export(session, include_data=True))
    assert replayed["source_verified"] and "Recomputed" in replayed["verification"]
    assert inspect_bundle(without_source, session.ds.raw)["source_verified"]
    with pytest.raises(ValueError, match="fingerprint"):
        inspect_bundle(without_source, session.ds.raw.replace(b"100", b"101"))
    damaged = rewrite_archive(without_source, {"record.md": b"changed"})
    with pytest.raises(ValueError, match="checksum"):
        inspect_bundle(damaged)
    with zipfile.ZipFile(BytesIO(without_source)) as archive:
        payload = json.loads(archive.read("investigation.json"))
    payload["record"][0]["result"]["table"][0]["count"] += 1
    forged = rewrite_archive(
        without_source, {"investigation.json": json.dumps(payload).encode()}, recompute=True
    )
    with pytest.raises(ValueError, match="calculation identity"):
        inspect_bundle(forged)
    unsafe = rewrite_archive(without_source, {"../unsafe": b"x"}, recompute=True)
    with pytest.raises(ValueError, match="unsupported files|Unsafe"):
        inspect_bundle(unsafe)
