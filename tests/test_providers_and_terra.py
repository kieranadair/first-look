"""Controlled HTTP transports exercise the real SDKs without keys or paid requests."""

import json
from types import SimpleNamespace

import httpx2
import pytest
from openai import OpenAI
from pydantic import ValidationError
from typesafe_sdk import RetryPolicy, TypeSafeClient

from firstlook.challenges import challenge
from firstlook.config import Settings
from firstlook.contracts import EvidencePacket, HypothesisProposal, NarrativeSynthesis, ProposalBatch
from firstlook.investigation import run_terra, valid_proposal
from firstlook.providers.base import ProviderError
from firstlook.providers.language import TerraProvider
from firstlook.providers.typesafe import JevProvider
from firstlook.visualization.compiler import axis_domains
from firstlook.visualization.review_assets import render_asset


def jev_client(handler):
    return TypeSafeClient(
        api_key="controlled-test-key",
        model="jev-latest",
        retry=RetryPolicy(max_retries=0),
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def test_official_jev_http_contract_and_record():
    requests = []

    def reply(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/v1/systemone"
        return httpx2.Response(
            200,
            json={
                "model": "jev-resolved-test",
                "usage": {"input_tokens": 20, "output_tokens": 3},
                "answers": {
                    "next": {
                        "type": "choice",
                        "choice": "a",
                        "confidence": 0.9,
                        "probabilities": {"a": 0.9, "none": 0.1},
                    }
                },
            },
        )

    p = JevProvider(Settings(typesafe_api_key="controlled-test-key"), jev_client(reply))
    result = p.choose({"evidence": "summary"}, {"a": "A valid view", "none": "Abstain"}, "Choose one")
    assert result.accepted and result.choice == "a"
    assert result.resolved_model == "jev-resolved-test"
    assert result.usage["input_tokens"] == 20
    assert requests[0]["questions"]["next"]["type"] == "choice"
    assert result.criteria == {"a": "A valid view", "none": "Abstain"}


@pytest.mark.parametrize("p,accepted", [(0.5, False), (0.74, False), (0.9, True)])
def test_jev_uncertain_choices_abstain(p, accepted):
    client = SimpleNamespace(
        system_one=lambda **kw: SimpleNamespace(
            choices={"next": SimpleNamespace(choice="a", probabilities={"a": p, "none": 1 - p})},
            model="test",
            usage={},
        )
    )
    record = JevProvider(Settings(typesafe_api_key="controlled-test-key"), client).choose(
        {}, {"a": "A", "none": "No"}, "Choose"
    )
    assert record.accepted is accepted


def test_unknown_jev_option_rejected():
    client = SimpleNamespace(
        system_one=lambda **kw: SimpleNamespace(
            choices={"next": SimpleNamespace(choice="invented", probabilities={"invented": 1.0})}
        )
    )
    with pytest.raises(ProviderError):
        JevProvider(Settings(typesafe_api_key="controlled-test-key"), client).choose({}, {"a": "A"}, "Choose")


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_official_provider_failures_are_sanitized(status):
    def reply(request):
        return httpx2.Response(status, json={"error": {"message": "do not print controlled-test-key"}})

    with pytest.raises(ProviderError) as exc:
        JevProvider(Settings(typesafe_api_key="controlled-test-key"), jev_client(reply)).choose(
            {}, {"a": "A"}, "Choose"
        )
    assert "controlled-test-key" not in str(exc.value)


def openai_client(handler):
    return OpenAI(
        api_key="controlled-test-key",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def response(payload):
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "gpt-6.1-terra-test",
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(payload), "annotations": []}],
            }
        ],
        "parallel_tool_calls": False,
        "tools": [],
        "tool_choice": "auto",
        "temperature": 1.0,
        "top_p": 1.0,
        "usage": {
            "input_tokens": 40,
            "output_tokens": 10,
            "total_tokens": 50,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def test_official_terra_responses_structured_text_and_image():
    sent = []

    def reply(request):
        sent.append(json.loads(request.content))
        assert request.url.path == "/v1/responses"
        return httpx2.Response(
            200, json=response({"schema_version": 1, "proposals": [], "abstain_reason": "No eligible check"})
        )

    p = TerraProvider(Settings(openai_api_key="controlled-test-key"), openai_client(reply))
    packet = EvidencePacket(
        context="ctx", focus=None, fields=[], findings=[], assets=[], allowed_operations=["none"]
    )
    result = p.propose(packet, [b"controlled-png"])
    assert result.proposals == [] and result.abstain_reason
    body = sent[0]
    assert body["store"] is False and body["max_output_tokens"] == 4500
    assert body["text"]["format"]["type"] == "json_schema"
    assert [c["type"] for c in body["input"][0]["content"]] == ["input_text", "input_image"]
    assert p.records[0]["resolved_model"] == "gpt-6.1-terra-test"
    for _ in range(2):
        p.propose(packet, [])
    with pytest.raises(ProviderError, match="budget"):
        p.propose(packet, [])
    assert len(sent) == 3


def test_terra_timeout_and_refusal_preserve_failure_boundary():
    def timeout(request):
        raise httpx2.ReadTimeout("controlled-test-key", request=request)

    p = TerraProvider(Settings(openai_api_key="controlled-test-key"), openai_client(timeout))
    with pytest.raises(ProviderError) as exc:
        p.synthesize({"evidence": []})
    assert "controlled-test-key" not in str(exc.value)

    def refusal(request):
        payload = response({})
        payload["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot comply"}]
        return httpx2.Response(200, json=payload)

    p = TerraProvider(Settings(openai_api_key="controlled-test-key"), openai_client(refusal))
    with pytest.raises(ProviderError, match="refusal"):
        p.synthesize({})


def proposal(finding, op="quantile_bin_summary", **kw):
    return HypothesisProposal(
        question="Could the conditional shape matter?",
        operation=op,
        finding_id=finding.id,
        reason="A testable visual hypothesis",
        **kw,
    )


def test_proposal_fields_and_operations_are_constrained(dataset, investigation):
    f = next(f for f in investigation.findings if f.family == "relationship")
    assert valid_proposal(dataset, investigation, proposal(f))[0]
    assert not valid_proposal(dataset, investigation, proposal(f, fields=["invented"]))[0]
    assert not valid_proposal(dataset, investigation, proposal(f, "subgroup", fields=["f000"]))[0]
    investigation.challenges.append(challenge(dataset, investigation, f, "quantile_bin_summary"))
    assert not valid_proposal(dataset, investigation, proposal(f))[0]
    with pytest.raises(ValidationError):
        proposal(f, "execute_python")


def test_review_assets_use_contract_domains_and_bound_values(investigation):
    f = next(f for f in investigation.findings if f.family == "relationship")
    result = investigation.results[f.result_id]
    asset = render_asset(result, f.chart)
    assert asset.png.startswith(b"\x89PNG") and len(asset.png) < 1_500_000
    assert len(asset.records) == asset.manifest["plotted_rows"] <= 600
    assert asset.manifest["axis_domains"] == axis_domains(f.chart, result)
    assert asset.manifest["labels"] == {"x": f.chart.x_label, "y": f.chart.y_label}
    assert asset.manifest["context"] == result.plan.context


def test_matched_visual_and_text_loop_preserves_checked_and_negative_evidence(dataset, investigation):
    import copy

    f = next(f for f in investigation.findings if f.family == "relationship")

    class Recorded:
        records = []

        def propose(self, packet, images):
            self.packet, self.images = packet, images
            return ProposalBatch(proposals=[proposal(f)])

        def synthesize(self, packet):
            assert packet["checks"]
            return NarrativeSynthesis(
                interpretation="The conditional view deserves attention, with grouping still unresolved.",
                evidence_ids=[f.id],
                next_questions=["Would the relationship hold within groups?"],
            )

    v, t = Recorded(), Recorded()
    left, right = copy.deepcopy(investigation), copy.deepcopy(investigation)
    run_terra(dataset, left, v, visual=True)
    run_terra(dataset, right, t, visual=False)
    assert v.packet.model_dump() == t.packet.model_dump()
    assert len(v.images) > 0 and t.images == []
    assert left.challenges[-1].operation == "quantile_bin_summary"
    assert left.challenges[-1].status == "not_checked"
    assert len(left.challenges) == len(investigation.challenges) + 1
    assert left.terra["synthesis"]["evidence_ids"] == [f.id]


def test_generated_numerical_claim_is_not_published_as_fact(dataset, investigation):
    class Unverified:
        records = []

        def propose(self, *args):
            return ProposalBatch(abstain_reason="No useful check")

        def synthesize(self, *args):
            return NarrativeSynthesis(interpretation="This proves a 90% causal uplift.", evidence_ids=[])

    run_terra(dataset, investigation, Unverified(), visual=False)
    assert "omitted" in investigation.terra["synthesis"]["interpretation"]


def test_semantic_hypotheses_are_validated_without_mutating_data(dataset):
    from firstlook.contracts import SemanticReview, SemanticSuggestion, Role
    from firstlook.semantics import validate_semantic_review

    original = dataset.record.model_dump()
    review = SemanticReview(
        suggestions=[
            SemanticSuggestion(field_id="f001", role=Role.ID, reason="May be a code; ask its meaning"),
            SemanticSuggestion(field_id="f003", role=Role.MEASURE, reason="Invalid physical conversion"),
            SemanticSuggestion(field_id="invented", role=Role.CATEGORY, reason="Unknown identity"),
        ]
    )
    results = validate_semantic_review(dataset, review)
    assert len(results) == 2 and results[0]["valid"] and not results[1]["valid"]
    assert dataset.record.model_dump() == original


def test_official_semantic_review_returns_typed_metadata_hypotheses():
    sent = []
    payload = {
        "schema_version": 1,
        "suggestions": [],
        "dataset_note": "Hypotheses require confirmation.",
        "metadata_proposals": [
            {
                "subject": "f001",
                "property": "kind",
                "value": "flow",
                "reason": "A name suggests an accrued amount; confirm its recording grain.",
            }
        ],
    }

    def reply(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=response(payload))

    provider = TerraProvider(Settings(openai_api_key="controlled-test-key"), openai_client(reply))
    result = provider.semantics(
        {"semantic_contract": {"grain_confirmed": False}, "fields": [{"id": "f001", "name": "sales"}]}
    )
    assert result.metadata_proposals[0].property == "kind"
    packet = json.loads(sent[0]["input"][0]["content"][0]["text"])
    assert "cannot be established from values alone" in packet["metadata_task"]
    assert sent[0]["store"] is False


def test_semantic_checks_and_definitions_reach_the_visual_reasoning_packet():
    from firstlook.examples import load_example
    from firstlook.discovery import Investigation, analyze
    from firstlook.semantic.planner import metric_plan
    from firstlook.investigation import run_terra
    from firstlook.contracts import ProposalBatch, NarrativeSynthesis, HypothesisProposal

    ds = load_example("semantic")
    ctx = ds.context()
    result, finding = analyze(ds, ctx, metric_plan(ds, ctx, "demo_order_average", ["f004"]))
    inv = Investigation(ctx, findings=[finding], results={result.id: result})

    class Reviewer:
        records = []

        def propose(self, packet, images):
            assert packet.metadata["semantic_contract"]["grain_confirmed"]
            assert packet.findings[0]["definition"]["aggregation"] == "average_per_entity"
            assert "semantic_unit" in packet.findings[0]["eligible_checks"]
            assert len(images) == 1
            return ProposalBatch(
                proposals=[
                    HypothesisProposal(
                        finding_id=finding.id,
                        operation="semantic_unit",
                        fields=result.plan.fields,
                        question="Does the averaging unit change the conclusion?",
                        reason="Rows and orders have different exposures.",
                    )
                ]
            )

        def synthesize(self, packet):
            return NarrativeSynthesis(
                interpretation="Averaging units answer different questions.", evidence_ids=[finding.id]
            )

    run_terra(ds, inv, Reviewer())
    assert any(c.operation == "semantic_unit" and c.status == "changed" for c in inv.challenges)


def test_jev_receives_semantics_and_only_prioritizes_unanswered_decisions(dataset):
    from firstlook.investigation import prioritize
    from firstlook.discovery import discover
    from firstlook.contracts import DecisionRecord, digest
    from firstlook.semantic.model import get_model

    inv = discover(dataset)
    before = get_model(dataset).revision
    calls = []

    class Decider:
        def choose(self, state, options, instructions):
            calls.append(state)
            choice = next(k for k in options if k != "none")
            return DecisionRecord(
                provider="controlled",
                requested_model="test",
                state_hash=digest(state),
                options=list(options),
                choice=choice,
                accepted=True,
            )

    prioritize(inv, Decider(), dataset)
    assert "semantic_contract" in calls[0] and "questions" in calls[1]
    assert get_model(dataset).revision == before
    assert inv.semantic_decisions[-1]["stage"] == "clarification_priority"
