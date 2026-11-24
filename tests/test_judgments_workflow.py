"""Independent typed-response, source-membership and semantic-scope oracles."""

import copy
from types import SimpleNamespace

import httpx2
import numpy as np
import pandas as pd
import pytest
from typesafe_sdk import TypeSafeClient, RetryPolicy

from firstlook.config import Settings
from firstlook.contracts import Role, NarrativeSynthesis, digest
from firstlook.discovery import discover
from firstlook.examples import load_example
from firstlook.ingest import from_frame
from firstlook.judgments import JudgmentBatch, JudgmentSpec, decode_answer
from firstlook.providers.base import ProviderError
from firstlook.providers.typesafe import JevProvider
from firstlook.text_features import TextFeatureSpec, code_text, feature_summary, evaluate_features


def batch(state, specs, values=None, context="ctx", purpose="Controlled"):
    values = values or {}
    answers = {}
    for s in specs:
        value = values.get(
            s.id,
            0.9 if s.kind == "noul" else next(iter(s.options)) if s.kind == "choice" else len(s.levels) - 1,
        )
        if s.kind == "noul":
            raw = {"type": "noul", "noul": value}
        elif s.kind == "choice":
            raw = {
                "type": "choice",
                "choice": value,
                "confidence": 0.8,
                "probabilities": {k: 1.0 if k == value else 0.0 for k in s.options},
            }
        else:
            raw = {
                "type": "score",
                "score": value,
                "confidence": 0.8,
                "legend": {str(i): v for i, v in enumerate(s.levels)},
                "probabilities": {str(i): 1.0 if i == value else 0.0 for i in range(len(s.levels))},
            }
        answers[s.id] = decode_answer(s, raw)
    return JudgmentBatch(
        id=digest([state, [s.model_dump() for s in specs]]),
        purpose=purpose,
        context=context,
        requested_model="controlled",
        resolved_model="controlled",
        state=state,
        state_hash=digest(state),
        definitions=specs,
        answers=answers,
    )


def specs():
    return [
        JudgmentSpec(id="fits", kind="noul", purpose="Applicability", question="Does the item fit?"),
        JudgmentSpec(
            id="subject",
            kind="choice",
            purpose="Subject",
            question="Which subject is named?",
            options={"penguin": "A penguin", "bicycle": "A bicycle"},
        ),
        JudgmentSpec(
            id="relevance",
            kind="score",
            purpose="Relevance",
            question="How relevant is it?",
            levels=["Unrelated", "Related context", "Directly addresses the question"],
        ),
    ]


def test_real_sdk_mixed_batch_records_transmitted_state_and_question_policies():
    requests = []
    definitions = specs()
    expected = batch({"goal": "penguins"}, definitions)

    def reply(request):
        import json

        requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "model": "resolved-controlled",
                "usage": {"input_tokens": 15, "output_tokens": 12},
                "answers": {k: v.raw for k, v in expected.answers.items()},
            },
        )

    client = TypeSafeClient(
        api_key="controlled-test-key",
        model="jev-latest",
        retry=RetryPolicy(max_retries=0),
        http_client=httpx2.Client(transport=httpx2.MockTransport(reply)),
    )
    provider = JevProvider(Settings(typesafe_api_key="controlled-test-key"), client)
    record = provider.judge({"goal": "penguins"}, definitions, context="ctx", purpose="SDK boundary")
    assert record.answers["fits"].value is True and record.answers["subject"].value == "penguin"
    assert record.answers["relevance"].value == 1.0
    assert record.state == requests[0]["state"] and "chart_policy" not in requests[0]["state"]
    assert {q["type"] for q in requests[0]["questions"].values()} == {"noul", "choice", "score"}
    assert all(record.trust_boundary in q["instructions"] for q in requests[0]["questions"].values())
    assert record.usage["input_tokens"] == 15 and record.resolved_model == "resolved-controlled"
    assert JudgmentBatch.model_validate_json(record.model_dump_json()) == record
    tampered = record.model_dump()
    tampered["answers"]["fits"]["value"] = False
    with pytest.raises(ValueError):
        JudgmentBatch.model_validate(tampered)


@pytest.mark.parametrize("p,status", [(0.1, "no"), (0.5, "unresolved"), (0.9, "yes")])
def test_noul_unknown_band_is_neither_false_nor_transport_failure(p, status):
    answer = decode_answer(specs()[0], {"type": "noul", "noul": p})
    assert answer.status == status
    if status == "unresolved":
        assert answer.value is None


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "noul", "noul": float("nan")},
        {"type": "noul", "noul": True},
        {"type": "choice", "choice": "invented", "probabilities": {"invented": 1.0}},
    ],
)
def test_invalid_or_wrong_type_answers_are_rejected(raw):
    with pytest.raises(ValueError):
        decode_answer(specs()[0], raw)


def test_bimodal_scores_remain_unresolved_and_ordinal_scores_are_not_effect_sizes():
    s = specs()[2]
    raw = {
        "type": "score",
        "legend": {"1": "Unrelated", "2": "Related context", "3": "Directly addresses the question"},
        "probabilities": {"1": 0.5, "2": 0.0, "3": 0.5},
    }
    assert decode_answer(s, raw).status == "unresolved"
    raw["probabilities"] = {"1": 0.0, "2": 0.0, "3": 1.0}
    assert decode_answer(s, raw).value == 1.0


def test_missing_sdk_answer_is_error_and_question_budget_is_enforced():
    provider = JevProvider(
        Settings(typesafe_api_key="controlled-test-key"),
        SimpleNamespace(system_one=lambda **kw: SimpleNamespace(answers={}, model="test", usage={})),
        max_questions=3,
    )
    with pytest.raises(ProviderError):
        provider.judge({}, specs(), context="ctx", purpose="Missing answers")
    assert provider.calls == 1 and not provider.records
    with pytest.raises(ProviderError, match="budget"):
        provider.judge({}, specs(), context="ctx", purpose="Exceeded budget")


def text_data(n=240):
    ds = from_frame(
        pd.DataFrame(
            {
                "record_id": range(n),
                "note": [
                    "The parcel arrived crushed" if i % 3 == 0 else "I ordered the wrong size"
                    for i in range(n)
                ],
                "exposure": np.arange(n) % 17,
                "outcome": [5 * (i % 3 == 0) + i % 7 for i in range(n)],
            }
        ),
        "text.csv",
    )
    ds.record.fields[0].role = Role.ID
    ds.record.fields[1].role = Role.TEXT
    ds.record.fields[2].role = ds.record.fields[3].role = Role.MEASURE
    return ds


def feature():
    return TextFeatureSpec(
        key="damage",
        label="Physical damage",
        question="Does the note explicitly describe physical damage?",
        yes="The parcel or item is described as physically damaged.",
        no="The text describes an ordering preference without physical damage.",
    )


class Coder:
    calls = 0

    def judge(self, state, definitions, *, context, purpose):
        self.calls += 1
        values = {
            s.id: 0.9 if "crushed" in state["texts"][s.question.split("`")[1].split(".")[1]] else 0.1
            for s in definitions
        }
        return batch(state, definitions, values, context, purpose)


def test_text_coding_deduplicates_inputs_but_keeps_every_source_membership():
    ds = text_data()
    before = ds.frame.copy(deep=True)
    coder = Coder()
    run = code_text(ds, ds.context(), "f001", [feature()], 240, coder)
    assert coder.calls == 1 and len(run.records) == 240
    summary = feature_summary(run)[0]
    assert summary["Yes"] == 80 and summary["No"] == 160 and summary["Classified coverage"] == 1
    assert run.source_rows == list(range(240))
    pd.testing.assert_frame_equal(ds.frame, before)


def test_missing_and_overlong_text_are_not_negative_observations():
    ds = text_data(4)
    ds.frame.loc[1, "f001"] = None
    ds.frame.loc[2, "f001"] = "x" * 2001
    ds.frame.loc[3, "f001"] = ""
    run = code_text(ds, ds.context(), "f001", [feature()], 4, Coder())
    assert [r["features"]["damage"]["status"] for r in run.records] == [
        "yes",
        "missing",
        "too_long",
        "missing",
    ]
    assert all(r["features"]["damage"]["value"] is None for r in run.records[1:])


def test_frozen_feature_models_share_holdout_and_cannot_use_unavailable_text():
    from firstlook.semantic.model import get_model

    ds = text_data()
    run = code_text(ds, ds.context(), "f001", [feature()], 240, Coder())
    result = evaluate_features(ds, ds.context(), run, "f003", "random", None, True)
    assert result["baseline"]["test_ids"] == result["augmented"]["test_ids"]
    assert result["baseline"]["train_ids"] == result["augmented"]["train_ids"]
    assert not set(result["baseline"]["predictors"]) & set(result["feature_fields"])
    assert set(result["feature_fields"]) <= set(result["augmented"]["predictors"])
    get_model(ds).meaning("f001").available_at_prediction = False
    unavailable_run = code_text(ds, ds.context(), "f001", [feature()], 240, Coder())
    with pytest.raises(ValueError):
        evaluate_features(ds, ds.context(), unavailable_run, "f003", "random", None, True)


class Interpreter:
    def judge(self, state, definitions, *, context, purpose):
        values = {"applicable": 0.9, "causal": 0.1, "within_group": 0.9, "task": "relationship"}
        for name, field, label in [
            ("measure", "measures", "body_mass_g"),
            ("other_measure", "measures", "flipper_length_mm"),
            ("group", "groups", "species"),
        ]:
            values[name] = next(k for k, v in state[field].items() if v["name"] == label)
        return batch(state, definitions, values, context, purpose)


def test_prepared_question_is_inspected_then_executed_with_explicit_subgroup():
    from firstlook.question_workflow import prepare_question, execute_prepared

    ds = load_example("penguins")
    inv = discover(ds)
    before = len(inv.results)
    review = prepare_question(
        ds, inv.context, "Are heavier penguins larger, or is this different between species?", Interpreter()
    )
    assert review["status"] == "ready for confirmation" and len(inv.results) == before
    execute_prepared(ds, inv, review)
    assert inv.question_history[-1]["executed"]
    assert inv.challenges[-1].operation == "subgroup"
    assert inv.results[inv.findings[0].result_id].plan.fields == ["f004", "f005"]
    inv.context = ds.context(list(range(100)))
    with pytest.raises(ValueError, match="earlier context"):
        execute_prepared(ds, inv, review)


def test_hypothetical_quantity_does_not_confirm_or_mutate_original_contract():
    from firstlook.clarifications import hypothetical_quantity
    from firstlook.semantic.model import get_model, add_metric
    from firstlook.semantic_contracts import Metric

    ds = text_data()
    add_metric(ds, Metric(id="total", label="Outcome total", aggregation="sum", field="f003"))
    before = copy.deepcopy(ds.record.model_dump())
    flow = hypothetical_quantity(ds, ds.context(), "total", "flow")
    state = hypothetical_quantity(ds, ds.context(), "total", "state")
    assert flow["result"]["records"][0]["value"] == ds.frame.f003.sum()
    assert state["eligibility"]["status"] == "disallowed" and state["result"] is None
    assert ds.record.model_dump() == before and not get_model(ds).metric("total").confirmed


def test_claim_support_and_scope_are_separate_and_unknown_evidence_is_rejected():
    from firstlook.claim_review import review_synthesis

    synthesis = NarrativeSynthesis(
        interpretation="The pooled relationship deserves a within-group check.", evidence_ids=["known"]
    )
    items = {"known": {"context": "ctx", "observation": "Pooled association only; subgroups not checked"}}

    class Reviewer:
        def judge(self, state, specifications, *, context, purpose):
            return batch(
                state,
                specifications,
                {s.id: 0.1 if s.id.endswith("_scope") else 0.9 for s in specifications},
                context,
                purpose,
            )

    review = review_synthesis(synthesis, items, "ctx", Reviewer())
    assert review["claims"][0]["status"] == "flagged" and "omitted" in review["display_text"]
    synthesis.evidence_ids = ["invented"]
    with pytest.raises(ProviderError):
        review_synthesis(synthesis, items, "ctx")


def test_candidate_relevance_ranking_is_explainable_and_never_changes_permissions():
    from firstlook.recommendations import rank_candidates

    candidates = [
        {
            "id": s,
            "alias": s,
            "question": s,
            "definition": "Existing eligible numerical view",
            "family": s,
            "support": 100,
            "cost": 0,
        }
        for s in ["distribution", "relationship"]
    ]

    class Rater:
        def judge(self, state, definitions, *, context, purpose):
            return batch(state, definitions, {definitions[0].id: 0, definitions[1].id: 2}, context, purpose)

    ranked, record = rank_candidates(candidates, "Relationship", "ctx", Rater())
    assert ranked[0]["id"] == "relationship" and ranked[0]["relevance"] == 1
    assert ranked[1]["relevance"] == 0 and record.context == "ctx"


def test_text_evidence_roundtrip_inspects_without_calls_and_validates_frozen_answers():
    from firstlook.state import Workspace
    from firstlook.evidence import export_bundle, import_bundle, recompute

    ds = text_data()
    run = code_text(ds, ds.context(), "f001", [feature()], 240, Coder())
    ws = Workspace()
    ws.load(ds)
    ws.investigation = discover(ds)
    ws.text_runs = [run.model_dump(mode="json")]
    restored = import_bundle(export_bundle(ws, True))
    assert restored.text_runs == ws.text_runs
    assert all(r["status"] == "match" for r in recompute(restored))
    data_free = import_bundle(export_bundle(ws, False))
    assert data_free.dataset.frame.empty and data_free.text_runs == ws.text_runs
    ws.text_runs[0]["definitions"][0]["question"] = "Does the record describe a different condition?"
    with pytest.raises(ValueError):
        import_bundle(export_bundle(ws, True))


def test_new_pages_show_frozen_coverage_and_recorded_definitions_without_providers():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from firstlook.state import Workspace

    ds = text_data()
    ws = Workspace()
    ws.load(ds)
    ws.investigation = discover(ds)
    ws.text_runs = [code_text(ds, ds.context(), "f001", [feature()], 240, Coder()).model_dump(mode="json")]
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run().switch_page("app_pages/text_lab.py").run()
    assert not app.exception and len(app.get("echarts_chart")) == 1
    assert any("Model-coded interpretations" in c.value for c in app.caption)
    app.switch_page("app_pages/judgments.py").run()
    assert (
        not app.exception
        and app.selectbox(key="judgment_record").value == ws.text_runs[0]["judgments"][0]["id"]
    )
    app.segmented_control(key="judgments_mode").set_value("Question library").run()
    assert not app.exception and len(app.get("download_button")) == 1
    app.segmented_control(key="judgments_mode").set_value("Evaluation cases").run()
    assert not app.exception and any("no model calls" in c.value for c in app.caption)
    app.switch_page("app_pages/evidence.py").run()
    app.button(key="prepare_export").click().run()
    first_export = app.session_state["prepared_context"]
    assert len(app.get("download_button")) == 2
    ws.text_runs.append(
        code_text(ds, ds.context(), "f001", [feature()], 120, Coder()).model_dump(mode="json")
    )
    app.run()
    assert not app.exception and len(app.get("download_button")) == 0
    app.button(key="prepare_export").click().run()
    assert app.session_state["prepared_context"] != first_export


def test_prepared_question_ui_requires_explicit_confirmation_and_keeps_original_evidence():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from firstlook.state import Workspace
    from firstlook.question_workflow import prepare_question

    ws = Workspace()
    ws.load(load_example("penguins"))
    ws.investigation = discover(ws.dataset)
    original_ids = set(ws.investigation.results)
    ws.question_review = prepare_question(
        ws.dataset, ws.context(), "Compare flipper_length_mm and body_mass_g"
    )
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py", default_timeout=30)
    app.session_state["workspace"] = ws
    app.run().switch_page("app_pages/discover.py").run()
    assert not app.exception and any(b.label == "Run this interpretation" for b in app.button)
    assert set(ws.investigation.results) == original_ids


def test_filter_context_invalidates_text_but_return_restores_anchored_run():
    from firstlook.state import Workspace
    from firstlook.comparison import preview

    ws = Workspace()
    ws.load(text_data())
    ws.investigation = discover(ws.dataset)
    ws.text_runs = [
        code_text(ws.dataset, ws.context(), "f001", [feature()], 240, Coder()).model_dump(mode="json")
    ]
    frozen = copy.deepcopy(ws.text_runs)
    preview(ws, list(range(60)), "predicate", "mapping")
    ws.begin_filtered()
    assert not ws.text_runs and not ws.question_review
    ws.return_to_anchor()
    assert ws.text_runs == frozen


def test_group_holdout_declaration_survives_derived_predictor_table():
    from firstlook.text_features import derived_model_table
    from firstlook.semantic.model import get_model

    ds = load_example("text")
    run = code_text(ds, ds.context(), "f002", [feature()], 240, Coder())
    derived, target, group, features, mapping = derived_model_table(
        ds, ds.context(), run, "f005", "f001", True
    )
    assert get_model(derived).model_group == group == mapping["f001"]
    assert set(derived.frame[group]) <= set(ds.frame.f001)
    from firstlook.modeling import run_model

    with pytest.raises(ValueError, match="group holdout"):
        run_model(derived, derived.context(), target, "random")


def test_choice_option_permutation_preserves_identity_and_does_not_depend_on_position():
    s = specs()[1]
    raw = {"type": "choice", "choice": "penguin", "probabilities": {"bicycle": 0.1, "penguin": 0.9}}
    original = decode_answer(s, raw)
    shuffled = decode_answer(s.model_copy(update={"options": dict(reversed(list(s.options.items())))}), raw)
    assert original == shuffled and original.value == "penguin"


def test_companion_applicability_can_reject_a_high_probability_choice():
    from firstlook.question_workflow import prepare_question

    ds = load_example("penguins")

    class Unsupported(Interpreter):
        def judge(self, state, definitions, *, context, purpose):
            answer = super().judge(state, definitions, context=context, purpose=purpose)
            values = {k: (v.raw["noul"] if v.kind == "noul" else v.value) for k, v in answer.answers.items()}
            values["applicable"] = 0.05
            return batch(state, definitions, values, context, purpose)

    review = prepare_question(ds, ds.context(), "Forecast next year's customer churn", Unsupported())
    assert review["status"] == "needs clarification" and review["plan"] is None
    assert review["judgment"]["answers"]["task"]["status"] == "selected"


def test_typed_prioritization_records_relevance_and_does_not_confirm_meaning():
    from firstlook.investigation import prioritize
    from firstlook.semantic.model import get_model

    ds = load_example("penguins")
    inv = discover(ds)
    before = get_model(ds).model_dump()

    class Rater:
        def judge(self, state, definitions, *, context, purpose):
            return batch(state, definitions, context=context, purpose=purpose)

    prioritize(inv, Rater(), ds)
    assert inv.recommendations and inv.judgments
    assert all(r.context == inv.context.id for r in inv.judgments)
    assert get_model(ds).model_dump() == before


def test_claim_review_preserves_partial_evidence_and_provider_error_is_not_no():
    from firstlook.claim_review import review_synthesis

    synthesis = NarrativeSynthesis(
        interpretation="The relationship merits a closer look.", evidence_ids=["known"]
    )

    class Unavailable:
        def judge(self, *args, **kwargs):
            raise ProviderError("Controlled provider unavailable")

    audit = review_synthesis(
        synthesis, {"known": {"observation": "Pooled association"}}, "ctx", Unavailable()
    )
    assert audit["claims"][0]["status"] == "pending_review" and audit["record"] is None
    assert "unavailable" in audit["provider_note"] and audit["display_text"] == synthesis.interpretation


def test_note_review_selects_existing_text_and_never_commits_business_meaning():
    from firstlook.clarifications import review_notes
    from firstlook.semantic.model import get_model

    ds = load_example("penguins")
    model = get_model(ds)
    before = model.model_dump()

    class Notes:
        def judge(self, state, definitions, *, context, purpose):
            return batch(state, definitions, context=context, purpose=purpose)

    note = "Each record is one observed bird, measured once at capture."
    review = review_notes(ds, ds.context(), model.clarifications[0].id, note, Notes())
    assert review["passage"] == note and review["status"] == "unconfirmed source evidence"
    assert model.model_dump() == before


def test_context_mismatch_and_invalid_group_do_not_mutate_prepared_execution():
    from firstlook.question_workflow import prepare_question, execute_prepared

    ds = load_example("penguins")
    inv = discover(ds)
    review = prepare_question(ds, inv.context, "Compare flipper_length_mm and body_mass_g")
    before = copy.deepcopy(inv.results)
    with pytest.raises(ValueError):
        execute_prepared(ds, inv, review, review["intent"], "f004")
    assert inv.results == before


def test_text_input_budget_is_rejected_before_any_billable_batch():
    ds = text_data()
    coder = Coder()
    coder.max_input_bytes = 1
    with pytest.raises(ValueError, match="before sending any text"):
        code_text(ds, ds.context(), "f001", [feature()], 240, coder)
    assert coder.calls == 0
