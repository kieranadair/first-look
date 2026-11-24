"""Small, explicit boundaries for a fresh visual investigation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
import hashlib
import json
from typing import Any, Literal

import numpy as np
import pandas as pd

Kind = Literal["number", "category", "time", "identifier", "text"]
View = Literal[
    "distribution",
    "categories",
    "groups",
    "relationship",
    "time",
    "missingness",
    "category_relationship",
    "spatial",
    "multivariate",
]
Metric = Literal["count", "distinct", "sum", "mean", "median", "weighted_mean"]


def clean(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return clean(asdict(value))
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return clean(value.item())
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(clean(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()[:24]


@dataclass
class Field:
    id: str
    name: str
    kind: Kind
    unit: str = ""
    missing: int = 0
    distinct: int = 0
    examples: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Dataset:
    name: str
    fingerprint: str
    frame: pd.DataFrame
    fields: list[Field]
    parser: dict = field(default_factory=dict)
    raw: bytes = b""

    def field(self, fid: str) -> Field:
        match = next((f for f in self.fields if f.id == fid), None)
        if match is None:
            raise ValueError("Choose a field from this table.")
        return match

    def label(self, fid: str) -> str:
        f = self.field(fid)
        duplicates = sum(v.name == f.name for v in self.fields)
        return f.name + (f" (column {self.fields.index(f) + 1})" if duplicates > 1 else "")


@dataclass
class Meaning:
    kind: Literal["unknown", "additive", "nonadditive"] = "unknown"
    entity: str | None = None
    unit: str = ""
    note: str = ""


@dataclass
class TimeRule:
    events: bool = False
    complete: bool = False
    complete_through: str = ""


@dataclass
class Request:
    view: View
    x: str = ""
    y: str | None = None
    group: str | None = None
    metric: Metric = "count"
    entity: str | None = None
    weight: str | None = None
    period: Literal["D", "W", "MS"] = "MS"
    zero_fill: bool = False
    attribution: Literal["none", "equal", "full"] = "none"
    fields: list[str] = field(default_factory=list)
    representation: str = "auto"


@dataclass
class Result:
    id: str
    context: str
    request: Request
    table: list[dict]
    summary: dict
    rows: list[int]
    omitted: int
    definition: str
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class Comparison:
    selected: Result
    reference: Result
    definition: str


class ChoiceRequired(ValueError):
    """Only the requested operation waits; recorded-data exploration remains available."""

    def __init__(self, message: str, field: str, evidence: dict | None = None):
        super().__init__(message)
        self.field = field
        self.evidence = evidence or {}
