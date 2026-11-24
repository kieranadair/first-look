"""Scoped semantics: observed structure, declared meaning and executable permissions."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Kind = Literal[
    "unknown",
    "amount",
    "flow",
    "count",
    "state",
    "rate",
    "ratio",
    "cumulative",
    "temperature",
    "circular",
    "coordinate",
    "index",
    "composition",
]
Aggregation = Literal[
    "count_rows",
    "count_distinct",
    "sum",
    "mean",
    "median",
    "weighted_mean",
    "average_per_entity",
    "ratio",
    "snapshot_last",
    "delta",
    "circular_mean",
]
Transform = Literal["identity", "log", "sqrt", "zscore", "difference", "percent_change"]


class SemanticBase(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class Assertion(SemanticBase):
    id: str
    subject: str
    property: str
    value: JsonValue
    origin: Literal["computed", "heuristic", "human", "terra"]
    confirmed: bool = False
    scope: str
    method: str
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    exceptions: list[int] = Field(default_factory=list, max_length=20)


class Entity(SemanticBase):
    id: str
    label: str = Field(min_length=1, max_length=150)
    keys: list[str] = Field(min_length=1, max_length=3)
    confirmed: bool = False
    unique: bool = False
    complete: bool = False
    distinct: int = 0


class FieldMeaning(SemanticBase):
    field: str
    kind: Kind = "unknown"
    confirmed: bool = False
    unit: str = Field(default="", max_length=80)
    currency: str = Field(default="", max_length=12)
    basis: str = Field(default="", max_length=200)
    available_at_prediction: bool = True
    composition: str | None = None
    allowed_transforms: list[Transform] = Field(default_factory=list)


class Relationship(SemanticBase):
    id: str
    child: str
    parent: str
    within: list[str] = Field(default_factory=list, max_length=2)
    relation: Literal["hierarchy", "membership"]
    strict: bool
    complete: bool
    child_levels: int
    violating_levels: int
    overlap_entities: int = 0
    confirmed: bool = False
    scope: str
    examples: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=5)


class TimePolicy(SemanticBase):
    id: str
    field: str
    series: list[str] = Field(default_factory=list, max_length=3)
    kind: Literal["unknown", "event", "instant", "interval", "state", "cumulative"] = "unknown"
    expected_frequency: Literal["unknown", "D", "2D", "W", "MS"] = "unknown"
    observed_interval_seconds: float | None = None
    gap_policy: Literal["preserve", "zero", "forward_fill", "interpolate"] = "preserve"
    coverage_complete: bool = False
    complete_through: str | None = None
    max_gap_periods: int = Field(default=0, ge=0, le=31)
    confirmed: bool = False
    calendar: Literal["calendar", "business"] = "calendar"


class Metric(SemanticBase):
    id: str
    label: str = Field(min_length=1, max_length=160)
    aggregation: Aggregation
    field: str | None = None
    entity: str | None = None
    weight: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    denominator_scope: Literal["active_population", "group"] = "active_population"
    confirmed: bool = False
    allocation: Literal["none", "full_credit", "equal"] = "none"
    transform: Transform = "identity"
    time_policy: str | None = None
    description: str = Field(default="", max_length=800)


class Clarification(SemanticBase):
    id: str
    subject: str
    property: str
    question: str
    reason: str
    priority: float
    suggested: str = ""
    affected_metrics: list[str] = Field(default_factory=list)


class OperationDecision(SemanticBase):
    status: Literal["allowed", "conditional", "disallowed", "unknown"]
    reasons: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class MetadataProposal(SemanticBase):
    subject: str
    property: Literal["kind", "grain", "unit", "expected_frequency", "gap_policy", "model_group"]
    value: str = Field(max_length=150)
    reason: str = Field(max_length=600)


class SemanticModel(SemanticBase):
    schema_version: Literal[1] = 1
    dataset: str
    parsing_scope: str = ""
    grain: str = Field(default="One recorded row; business grain is unconfirmed.", max_length=500)
    grain_entity: str | None = None
    grain_confirmed: bool = False
    model_group: str | None = None
    entities: list[Entity] = Field(default_factory=list, max_length=12)
    meanings: list[FieldMeaning] = Field(default_factory=list, max_length=80)
    relationships: list[Relationship] = Field(default_factory=list, max_length=120)
    time_policies: list[TimePolicy] = Field(default_factory=list, max_length=20)
    metrics: list[Metric] = Field(default_factory=list, max_length=160)
    assertions: list[Assertion] = Field(default_factory=list, max_length=400)
    clarifications: list[Clarification] = Field(default_factory=list, max_length=80)
    search: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def revision(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:24]

    def metric(self, mid: str) -> Metric:
        found = next((m for m in self.metrics if m.id == mid), None)
        if found is None:
            raise ValueError("Unknown metric identity.")
        return found

    def entity(self, eid: str) -> Entity:
        found = next((e for e in self.entities if e.id == eid), None)
        if found is None:
            raise ValueError("Unknown entity identity.")
        return found

    def meaning(self, fid: str) -> FieldMeaning:
        found = next((m for m in self.meanings if m.field == fid), None)
        if found is None:
            raise ValueError("Unknown field meaning.")
        return found

    @model_validator(mode="after")
    def unique_ids(self):
        for objects in [
            self.metrics,
            self.entities,
            self.relationships,
            self.time_policies,
            self.assertions,
            self.clarifications,
        ]:
            ids = [o.id for o in objects]
            if len(ids) != len(set(ids)):
                raise ValueError("Semantic identities must be unique within each collection.")
        return self
