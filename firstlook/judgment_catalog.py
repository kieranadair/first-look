"""Auditable question wording, criteria and policies for all built-in Jev workflows."""

from firstlook.judgments import JudgmentSpec, applicability_spec, relevance_spec
from firstlook.contracts import digest

TASKS = {
    "relationship": "Examine association between two recorded numerical quantities, without establishing a cause.",
    "group_shape": "Compare the distribution of one numerical quantity across recorded groups.",
    "distribution": "Inspect one numerical quantity's distribution.",
    "frequency": "Count the recorded levels of one categorical field.",
    "category_relationship": "Compare counts or conditional proportions across two categorical fields.",
    "metric": "Compute one existing named metric with its recorded grain and denominator.",
    "missingness": "Inspect missing values in the recorded population.",
    "time": "Inspect a numerical quantity over one recorded timestamp.",
}


def intent_specs(state):
    measures, groups = state["measures"], state["groups"]
    times, metrics = state["timestamps"], state["metrics"]
    specs = [
        applicability_spec(),
        JudgmentSpec(
            id="task",
            purpose="Requested analytical task",
            kind="choice",
            question="Which task in `candidates` is explicitly requested by `goal`?",
            options=TASKS,
        ),
        JudgmentSpec(
            id="causal",
            purpose="Prevent an association plan from claiming causal identification",
            kind="noul",
            question="Does `goal` ask this table to establish that one variable causes another?",
            yes="The request asks to prove or establish a causal effect or causal explanation.",
            no="The request asks to describe, compare, predict or inspect association without establishing causation.",
        ),
    ]
    for name, options, text in [
        (
            "measure",
            measures,
            "Which field is the primary numerical quantity or outcome named in `goal`?",
        ),
        (
            "other_measure",
            measures,
            "Which field is the other numerical comparison or predictor named in `goal`?",
        ),
        ("group", groups, "Which field names the grouping or first category requested in `goal`?"),
        (
            "other_group",
            groups,
            "Which field names the second categorical dimension requested in `goal`?",
        ),
        ("timestamp", times, "Which timestamp is explicitly requested in `goal`?"),
        ("metric", metrics, "Which existing named metric is requested in `goal`?"),
    ]:
        if options:
            specs.append(
                JudgmentSpec(
                    id=name,
                    purpose="Map a stated field or metric to a supplied identity",
                    kind="choice",
                    question=text,
                    options={
                        k: str(v["name"]) + " — " + str(v.get("definition", v.get("role", "")))
                        for k, v in options.items()
                    },
                )
            )
    if groups:
        specs.append(
            JudgmentSpec(
                id="within_group",
                purpose="Explicit subgroup request",
                kind="noul",
                question="Does `goal` explicitly ask to compare a numerical relationship within or between recorded groups?",
                yes="The question names group differences or asks whether a pooled numerical relationship holds within groups.",
                no="The question asks only about two numerical fields in the pooled population, or does not request a subgroup relationship.",
            )
        )
    return specs


def claim_specs(alias):
    return [
        JudgmentSpec(
            id=alias + "_support",
            purpose="Semantic support of a generated claim",
            kind="noul",
            question=f"Does the supplied evidence in `claims.{alias}` explicitly support that claim's wording?",
            yes="The evidence states what the claim says, without a missing explanation or an invented completed test.",
            no="The claim contradicts the evidence, supplies an unstated explanation, or treats an unperformed test as completed.",
        ),
        JudgmentSpec(
            id=alias + "_scope",
            purpose="Population and aggregation scope of a generated claim",
            kind="noul",
            question=f"Does the claim in `claims.{alias}` retain its cited evidence's population and aggregation scope?",
            yes="The wording stays within the supplied population, grouping, sampling and holdout scope.",
            no="The wording generalizes beyond the supplied rows, implies within-group evidence from a pooled view, or extends prediction to causation.",
        ),
    ]


def note_specs(notes):
    return [
        JudgmentSpec(
            id="explicit",
            purpose="Collection notes supporting a semantic clarification",
            kind="noul",
            question="Do `notes` explicitly state information answering `decision`?",
            yes="A note explicitly describes the requested recording process, value grain or quantity meaning.",
            no="The notes omit the required meaning, merely name a field, or describe a different process.",
        ),
        JudgmentSpec(
            id="passage",
            purpose="Select an existing source passage without generating a citation",
            kind="choice",
            question="Which supplied note most directly addresses `decision`?",
            options={k: v[:1400] for k, v in notes.items()},
        ),
    ]


def preparation_specs(alias):
    return [
        JudgmentSpec(
            id=alias + "_support",
            purpose="Prepared definition supported by supplied wording",
            kind="noul",
            question=f"Do the supplied passages in `definitions.{alias}` explicitly state that proposed definition?",
            yes="The source wording explicitly establishes the proposed meaning, estimator or recording rule.",
            no="The source omits a required fact, only names the field, or the proposed meaning goes beyond its wording.",
        ),
        JudgmentSpec(
            id=alias + "_scope",
            purpose="Source applicability to the proposed field and process",
            kind="noul",
            question=f"Do the supplied passages in `definitions.{alias}` describe that proposal's field and recording process?",
            yes="The wording describes the same field, entity grain and recording process as the proposed definition.",
            no="The passage describes another field, population, entity grain or recording process, or does not identify the proposal's scope.",
        ),
    ]


def built_in_definitions():
    state = {
        "measures": {"body_mass": {"name": "Body mass", "role": "measure"}},
        "groups": {"species": {"name": "Species", "role": "category"}},
        "timestamps": {"observed_date": {"name": "Observed date", "role": "timestamp"}},
        "metrics": {
            "recorded_rows": {
                "name": "Recorded rows",
                "definition": "Count recorded rows in the active population",
            }
        },
    }
    return (
        intent_specs(state)
        + [relevance_spec("candidate_relevance", "candidates.example")]
        + note_specs({"collection_note": "The supplied collection note, retained verbatim in state."})
        + claim_specs("example")
        + preparation_specs("preparation_example")
    )


def text_spec(feature, key):
    return JudgmentSpec(
        id="text_" + digest([key, feature.key]),
        purpose="Model-coded text feature: " + feature.label,
        kind="noul",
        question=f"For `texts.text_{key}`: {feature.question}",
        yes=feature.yes,
        no=feature.no,
        version=feature.version,
    )
