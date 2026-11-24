"""One working investigation, immutable kept observations and dataset-scoped budgets."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace

import pandas as pd

from firstlook.types import Comparison, Dataset, Kind, Meaning, Request, Result, TimeRule, clean, digest


@dataclass
class Session:
    ds: Dataset | None = None
    profile: dict = field(default_factory=dict)
    meanings: dict[str, Meaning] = field(default_factory=dict)
    time_rules: dict[str, TimeRule] = field(default_factory=dict)
    question: str = ""
    notes: str = ""
    rows: list[int] | None = None
    current: Result | None = None
    last_request: Request | None = None
    comparison: Comparison | None = None
    record: list[dict] = field(default_factory=list)
    assistance: dict = field(default_factory=dict)
    provider_history: list[dict] = field(default_factory=list)
    assistance_requests: set[str] = field(default_factory=set)
    assistance_cache: dict[str, dict] = field(default_factory=dict)
    prediction: dict = field(default_factory=dict)
    prediction_used: bool = False

    @property
    def context(self) -> str:
        from firstlook.analysis import context_id

        if self.ds is None:
            return ""
        return context_id(self.ds, self.meanings, self.rows, self.time_rules)

    @property
    def scope(self) -> str:
        return self.context

    @property
    def assistance_context(self) -> str:
        return digest(
            [
                self.context,
                self.current.id if self.current else None,
                [self.comparison.selected.id, self.comparison.reference.id] if self.comparison else None,
                self.question,
                self.notes,
                self.prediction.get("id"),
            ]
        )

    def _dataset(self) -> Dataset:
        if self.ds is None:
            raise ValueError("Open your table first.")
        return self.ds

    def _expect(self, expected_context: str | None) -> None:
        if expected_context is not None and expected_context != self.context:
            raise ValueError("This choice belongs to an earlier view. Review it against the current data.")

    def _invalidate(self) -> None:
        self.current, self.comparison, self.assistance = None, None, {}

    def load(self, ds: Dataset) -> None:
        from firstlook.data import profile, starting_requests

        # Compute before replacing a valid existing investigation.
        prepared_profile = profile(ds)
        requests = starting_requests(ds)
        fresh = Session(ds=ds, profile=prepared_profile)
        if requests:
            fresh.run(requests[0])
        self.__dict__.update(fresh.__dict__)

    def run(self, request: Request) -> Result:
        from firstlook.analysis import analyze

        ds = self._dataset()
        result = analyze(ds, request, self.meanings, self.rows, self.time_rules)
        self.current, self.last_request, self.comparison = result, deepcopy(request), None
        self.assistance = {}
        return result

    def declare(self, fid: str, meaning: Meaning, *, expected_context: str | None = None) -> None:
        self._expect(expected_context)
        ds = self._dataset()
        f = ds.field(fid)
        if not isinstance(meaning, Meaning) or meaning.kind not in {"unknown", "additive", "nonadditive"}:
            raise ValueError("Choose an explicit recorded quantity meaning.")
        if f.kind != "number":
            raise ValueError("A quantity meaning applies to a numerical field.")
        if len(meaning.unit) > 80 or len(meaning.note) > 2000:
            raise ValueError("Keep the unit under 80 characters and the explanation under 2,000.")
        if meaning.entity:
            entity = ds.field(meaning.entity)
            if entity.id == fid or entity.kind not in {"identifier", "category"}:
                raise ValueError("Choose a separate identifier or categorical field for the value entity.")
        updated = deepcopy(self.meanings)
        updated[fid] = deepcopy(meaning)
        if updated != self.meanings:
            self.meanings = updated
            self._invalidate()

    def set_time_rule(self, fid: str, rule: TimeRule, *, expected_context: str | None = None) -> None:
        self._expect(expected_context)
        if self._dataset().field(fid).kind != "time" or not isinstance(rule, TimeRule):
            raise ValueError("Choose a recorded timestamp for this recording rule.")
        if rule.complete and not rule.complete_through.strip():
            raise ValueError("Complete recording needs a last complete date.")
        if rule.complete_through:
            try:
                if pd.isna(pd.Timestamp(rule.complete_through)):
                    raise ValueError("A missing timestamp is not a last complete date.")
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("Supply a valid last complete date.") from exc
        updated = deepcopy(self.time_rules)
        updated[fid] = deepcopy(rule)
        if updated != self.time_rules:
            self.time_rules = updated
            self._invalidate()

    def set_role(self, fid: str, kind: Kind, *, expected_context: str | None = None) -> None:
        self._expect(expected_context)
        ds = self._dataset()
        old = ds.field(fid)
        if kind not in {"number", "category", "time", "identifier", "text"}:
            raise ValueError("Choose one of the supported field roles.")
        if kind == "number" and not pd.api.types.is_numeric_dtype(ds.frame[fid]):
            raise ValueError(
                "This field is not recorded numerically. Reopen with the right parsing settings if needed."
            )
        if kind == "time" and not pd.api.types.is_datetime64_any_dtype(ds.frame[fid]):
            raise ValueError("A time role needs values parsed as timestamps.")
        if old.kind == kind:
            return
        # Reject role edits that would silently invalidate another field's explicit value entity.
        if kind not in {"identifier", "category"} and any(m.entity == fid for m in self.meanings.values()):
            raise ValueError(
                "This field is a declared value entity. Review that definition before changing its role."
            )
        fields = [replace(f, kind=kind) if f.id == fid else deepcopy(f) for f in ds.fields]
        self.ds = replace(ds, fields=fields)
        if kind != "number":
            self.meanings.pop(fid, None)
        if kind != "time":
            self.time_rules.pop(fid, None)
        self._invalidate()

    def set_rows(self, rows: list[int] | None) -> None:
        ds = self._dataset()
        if rows is not None:
            if (
                not rows
                or len(rows) != len(set(rows))
                or any(isinstance(r, bool) or not isinstance(r, int) or r not in ds.frame.index for r in rows)
            ):
                raise ValueError("Choose distinct recorded rows from this table.")
            rows = sorted(rows)
            if rows == list(ds.frame.index):
                rows = None
        if rows != self.rows:
            self.rows = deepcopy(rows)
            self._invalidate()

    def reset(self) -> None:
        self.set_rows(None)

    def save_result(self, note: str = "") -> str:
        ds = self._dataset()
        if self.current is None or self.current.context != self.context:
            raise ValueError("Keep a view from the current investigation first.")
        if len(note) > 2000:
            raise ValueError("Keep the interpretation under 2,000 characters.")
        identity = digest([self.current.id, clean(self.comparison)])
        if any(r["id"] == identity for r in self.record):
            return identity
        if len(self.record) >= 24:
            raise ValueError("This record holds 24 views. Export it before starting another investigation.")
        self.record.append(
            deepcopy(
                clean(
                    {
                        "id": identity,
                        "context": self.context,
                        "result": self.current,
                        "comparison": self.comparison,
                        "meanings": self.meanings,
                        "time_rules": self.time_rules,
                        "fields": ds.fields,
                        "question": self.question,
                        "note": note,
                    }
                )
            )
        )
        return identity

    def update_note(self, identity: str, note: str) -> None:
        if len(note) > 2000:
            raise ValueError("Keep the interpretation under 2,000 characters.")
        entry = next((r for r in self.record if r["id"] == identity), None)
        if entry is None:
            raise ValueError("Choose a kept observation.")
        entry["note"] = note

    def begin_assistance(self, key: str) -> str:
        self._dataset()
        if not isinstance(key, str) or not key.strip() or len(key) > 200:
            raise ValueError("This assistance request needs a bounded identity.")
        if key in self.assistance_requests:
            raise ValueError("This request has already been attempted. Reruns do not repeat paid work.")
        self.assistance_requests.add(key)
        return self.assistance_context

    def accept_assistance(self, payload: dict, context: str, *, retain_stale: bool = False) -> bool:
        if self.ds is None or context != self.assistance_context and not retain_stale:
            return False
        if not isinstance(payload, dict):
            raise ValueError("The assistant returned an invalid response.")
        self.assistance_cache[context] = deepcopy(clean(payload))
        self.provider_history = (self.provider_history + [{**deepcopy(clean(payload)), "context": context}])[
            -24:
        ]
        if context != self.assistance_context:
            return False
        self.assistance = deepcopy(self.assistance_cache[context])
        return True

    def begin_prediction(self) -> str:
        self._dataset()
        if self.prediction_used:
            raise ValueError(
                "This table has already used its fixed prediction check. Keep its recorded holdout independent of further searching."
            )
        self.prediction_used = True
        return self.context

    def accept_prediction(self, payload: dict, context: str) -> bool:
        if context != self.context or self.ds is None:
            return False
        if not isinstance(payload, dict):
            raise ValueError("The prediction check returned an invalid response.")
        self.prediction = deepcopy(clean(payload))
        return True
