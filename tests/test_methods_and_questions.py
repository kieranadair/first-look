import re
from pathlib import Path

import pytest

from firstlook.methods import registry
from firstlook.questions import local_intent, run_question


def test_research_rules_refer_to_real_tests_and_sources():
    source = "\n".join(p.read_text() for p in Path("tests").glob("test_*.py"))
    test_names = set(re.findall(r"^def (test_\w+)", source, re.M))
    for rule in registry()["rules"].values():
        assert rule["source"].startswith("https://")
        assert set(rule["tests"]) <= test_names


def test_causal_question_is_reframed_without_generated_code(dataset, investigation):
    intent = local_intent(dataset, "Does exposure cause response?")
    assert intent.operation == "unsupported" and "cause" in intent.clarification
    with pytest.raises(ValueError):
        run_question(dataset, investigation, "Does exposure cause response?")


def test_question_resolves_to_same_contract_pipeline(dataset, investigation):
    result = run_question(dataset, investigation, "Does response differ by region?")
    finding = result.findings[0]
    assert result.results[finding.result_id].plan.operation == "group_distribution"
    assert finding.chart.result_id == finding.result_id


def luminance(value):
    rgb = [int(value[i : i + 2], 16) / 255 for i in [1, 3, 5]]
    values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(values, [0.2126, 0.7152, 0.0722]))


def test_text_and_primary_button_theme_contrast():
    import tomllib

    theme = tomllib.loads(Path(".streamlit/config.toml").read_text())["theme"]
    for mode in ["light", "dark"]:
        t = theme[mode]
        for fg, bg in [
            (t["textColor"], t["backgroundColor"]),
            (t["textColor"], t["secondaryBackgroundColor"]),
            (t["linkColor"], t["backgroundColor"]),
            ("#FFFFFF", t["primaryColor"]),
        ]:
            a, b = sorted([luminance(fg), luminance(bg)])
            assert (b + 0.05) / (a + 0.05) >= 4.5, (mode, fg, bg)
