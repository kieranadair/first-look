"""Authority and request-boundary contracts for chart advice, without provider calls."""

import json

import pytest

from firstlook.visualization.guidance import (
    GUIDANCE_VERSION,
    HARD_RULES,
    MODEL_POLICIES,
    SOFT_GUIDANCE,
    SOURCES,
    guidance_for,
    policy_packet,
)


def test_policy_packet_is_versioned_finite_json_with_a_small_request_budget():
    packet = policy_packet()
    encoded = json.dumps(packet, allow_nan=False).encode("utf-8")
    restored = json.loads(encoded)
    assert len(encoded) <= 4_000
    assert isinstance(GUIDANCE_VERSION, str) and GUIDANCE_VERSION.strip()
    assert restored["version"] == GUIDANCE_VERSION
    assert restored["enforced_by"] == "Python"
    assert restored["deterministic_origin"] != restored["conditional_origin"]
    assert set(restored["model_roles"]) == {"jev", "terra"}
    assert set(restored["deterministic_rule_ids"]) == {r["id"] for r in restored["rules"]}
    assert all(r["note"] and set(r["source_keys"]) <= set(restored["sources"]) for r in restored["rules"])


def test_hard_invariants_and_conditional_preferences_have_distinct_authority_and_sources():
    assert HARD_RULES and SOFT_GUIDANCE and HARD_RULES.keys().isdisjoint(SOFT_GUIDANCE)
    for rid, rule in HARD_RULES.items():
        assert rule["id"] == rid and rule["title"] and rule["note"]
        assert rule["ownership"] == "Python" and rule["origin"] == "application_invariant"
        assert rule["source"] and rule["source_keys"]
        assert set(rule["source_keys"]) <= set(SOURCES)
    for rid, preference in SOFT_GUIDANCE.items():
        assert preference["id"] == rid and preference["title"] and preference["note"]
        assert preference["ownership"] == "Jev/Terra"
        assert preference["origin"] == "conditional_preference"
        assert preference["roles"] and set(preference["roles"]) <= {"jev", "terra"}
        assert preference["source"] and set(preference["source_keys"]) <= set(SOURCES)


@pytest.mark.parametrize("role", ["jev", "terra"])
def test_model_guidance_preserves_python_permissions_and_proposal_boundaries(role):
    prompt = guidance_for(role)
    assert GUIDANCE_VERSION in prompt
    assert MODEL_POLICIES[role] in prompt
    assert "cannot override" in prompt and "not permissions" in prompt
    assert "Do not authorize" in prompt and "numerical facts" in prompt
    if role == "jev":
        assert "one atomic judgment" in prompt and "supplied eligible option ID" in prompt
        assert "Do not chain unprovided choices" in prompt
    else:
        assert "hypotheses" in prompt and "supplied permitted Python checks" in prompt
        assert "not established facts" in prompt


@pytest.mark.parametrize("role", ["python", "Terra", "all", ""])
def test_guidance_has_only_the_two_supported_model_roles(role):
    with pytest.raises(ValueError, match="only for jev or terra"):
        guidance_for(role)


def test_request_metadata_cannot_mutate_the_shared_policy_registry():
    packet = policy_packet()
    packet["deterministic_rule_ids"].clear()
    packet["rules"][0]["source_keys"].clear()
    packet["sources"].clear()
    fresh = policy_packet()
    assert fresh["deterministic_rule_ids"] and fresh["rules"][0]["source_keys"] and fresh["sources"]
