"""Bounded drafts are proposals. Only a reviewed transaction changes analytical meaning."""

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from firstlook.analytical_tasks import AvailabilityRule, TaskDefinition
from firstlook.contracts import Contract, Role
from firstlook.semantic_contracts import FieldMeaning, TimePolicy

PREPARATION_POLICY = "2026-11-24.1"


class SourceQuote(Contract):
    source: str = Field(max_length=80)
    quote: str = Field(min_length=1, max_length=700)


class Explanation(Contract):
    reason: str = Field(min_length=1, max_length=600)
    evidence: list[SourceQuote] = Field(default_factory=list, max_length=3)


class QuantityProposal(Explanation):
    meaning: FieldMeaning


class RoleProposal(Explanation):
    field: str
    role: Role
    order: list[str] = Field(default_factory=list, max_length=100)


class SelectionProposal(Explanation):
    candidate: str = Field(max_length=100)


class GrainProposal(Explanation):
    description: str = Field(min_length=1, max_length=500)
    entity: str | None = None


class TimeProposal(Explanation):
    policy: TimePolicy


class AvailabilityProposal(Explanation):
    rule: AvailabilityRule


class TaskProposal(Explanation):
    task: TaskDefinition


class PreparationInterpretation(Contract):
    summary: str = Field(max_length=1600)
    quantities: list[QuantityProposal] = Field(default_factory=list, max_length=16)
    roles: list[RoleProposal] = Field(default_factory=list, max_length=8)
    selections: list[SelectionProposal] = Field(default_factory=list, max_length=24)
    grain: GrainProposal | None = None
    times: list[TimeProposal] = Field(default_factory=list, max_length=4)
    task: TaskProposal | None = None
    availability: list[AvailabilityProposal] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def bounded_bundle(self):
        if (
            sum(len(v) for v in [self.quantities, self.roles, self.selections, self.times, self.availability])
            > 32
        ):
            raise ValueError("At most 32 connected preparation changes per request.")
        return self


class PreparedChange(Contract):
    id: str
    kind: Literal[
        "quantity", "role", "entity", "grain", "metric", "relationship", "time", "task", "availability"
    ]
    subject: str
    label: str = Field(max_length=250)
    payload: dict[str, JsonValue]
    before: JsonValue = None
    origin: Literal["python", "heuristic", "terra", "template"]
    reason: str = Field(max_length=1000)
    evidence: list[SourceQuote] = Field(default_factory=list, max_length=3)
    requires: list[str] = Field(default_factory=list, max_length=20)
    suggested: bool = False
    issue: str = ""
    review: str = "Not reviewed by Jev"


class PreparationDraft(Contract):
    policy: str = PREPARATION_POLICY
    dataset: str
    parsing_scope: str
    base_semantics: str
    request: str = ""
    goal: str = Field(default="", max_length=1000)
    summary: str = Field(default="", max_length=1600)
    changes: list[PreparedChange] = Field(default_factory=list, max_length=140)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=24)
    decisions: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=24)
    sources: dict[str, str] = Field(default_factory=dict, max_length=3)
    records: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=8)
    errors: list[str] = Field(default_factory=list, max_length=8)
    applied: list[str] = Field(default_factory=list, max_length=140)
    deferred: list[str] = Field(default_factory=list, max_length=24)
    telemetry: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_changes(self):
        ids = [c.id for c in self.changes]
        if len(ids) != len(set(ids)):
            raise ValueError("Preparation change identities must be unique.")
        return self
