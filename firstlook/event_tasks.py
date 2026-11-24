"""Finite single-table event recipes: past-only features and forward-only labels."""

from __future__ import annotations

from typing import Literal, Any
import hashlib
import pandas as pd
from pydantic import Field, model_validator

from firstlook.analytical_tasks import TaskDefinition, AvailabilityRule, availability_basis
from firstlook.contracts import Contract, Role, DatasetRecord, AnalysisContext, ModelRun, clean, digest
from firstlook.ingest import Dataset, from_frame
from firstlook.semantic.model import get_model, validate_model

EVENT_POLICY = "2026-11-24.1"


class EventTaskSpec(Contract):
    dataset: str
    entity: str
    event_time: str
    event_id: str | None = None
    known_time: str | None = None
    available_at_event: bool = False
    recipe: Literal["recurrence", "event_count"] = "recurrence"
    lookback_days: int = Field(default=90, ge=1, le=365)
    horizon_days: int = Field(default=30, ge=1, le=365)
    reporting_delay_days: int = Field(default=0, ge=0, le=365)
    anchors: list[str] = Field(min_length=3, max_length=6)
    complete_through: str
    coverage_confirmed: bool = False

    @model_validator(mode="after")
    def valid_spec(self):
        times = [pd.to_datetime(v, utc=True) for v in self.anchors]
        end = pd.to_datetime(self.complete_through, utc=True)
        if any(pd.isna(v) for v in [*times, end]):
            raise ValueError("Anchor and coverage dates must be recorded timestamps.")
        if len(set(times)) != len(times) or times != sorted(times):
            raise ValueError("Anchors must be unique and chronological.")
        if any(b - a < pd.Timedelta(self.horizon_days, unit="D") for a, b in zip(times, times[1:])):
            raise ValueError("Outcome windows at different anchors cannot overlap.")
        if self.lookback_days < self.horizon_days:
            raise ValueError("The lookback must cover at least one complete outcome-length window.")
        if not self.known_time and not self.available_at_event:
            raise ValueError(
                "Supply information-availability timestamps or explicitly attest availability at event time."
            )
        if not self.coverage_confirmed:
            raise ValueError("Derived negative labels require explicit complete event-recording coverage.")
        return self


class EventTaskRun(Contract):
    id: str
    policy: str = EVENT_POLICY
    source_context: AnalysisContext
    spec: EventTaskSpec
    derived_schema: DatasetRecord
    derived_context: AnalysisContext
    records: list[dict[str, Any]] = Field(min_length=3, max_length=10_000)
    memberships: list[dict[str, Any]] = Field(min_length=3, max_length=10_000)
    table_hash: str
    train_ids: list[int] = Field(min_length=1)
    test_ids: list[int] = Field(min_length=1)
    preparation: dict[str, Any]
    model: ModelRun | None = None

    @model_validator(mode="after")
    def valid_run(self):
        if (
            self.spec.dataset != self.source_context.dataset
            or self.derived_schema.fingerprint != self.derived_context.dataset
        ):
            raise ValueError("Event task source or derived identity mismatch.")
        if digest(self.records) != self.table_hash or self.id != digest(
            [self.source_context.id, self.spec.model_dump(), self.table_hash]
        ):
            raise ValueError("Event table or task identity has changed.")
        protocol = {"source_context": self.source_context.id, "spec": self.spec.model_dump(mode="json")}
        if (
            not self.derived_schema.semantic_model
            or self.derived_schema.semantic_model.search.get("event_protocol") != protocol
        ):
            raise ValueError("Derived schema has a different event protocol.")
        ids = list(range(len(self.records)))
        columns = {
            "Entity",
            "Anchor timestamp",
            "Historical events",
            "Events in previous window",
            "Active history days",
            "Days since last event",
            "Days since first observed event",
            "Outcome",
        }
        if (
            self.derived_schema.rows != len(ids)
            or self.derived_schema.columns != 8
            or len(self.derived_schema.fields) != 8
        ):
            raise ValueError("Derived event dimensions disagree with their schema.")
        for row in self.records:
            if set(row) != columns or not isinstance(row["Entity"], str):
                raise ValueError("Invalid derived event record shape.")
            anchor = pd.to_datetime(row["Anchor timestamp"], utc=True)
            if anchor not in [
                pd.to_datetime(v, utc=True) for v in self.spec.anchors
            ] or anchor + pd.Timedelta(self.spec.horizon_days, unit="D") > pd.to_datetime(
                self.spec.complete_through, utc=True
            ):
                raise ValueError("Derived event row has an undeclared or incomplete anchor.")
            for key in ["Historical events", "Events in previous window", "Active history days", "Outcome"]:
                if isinstance(row[key], bool) or not isinstance(row[key], int) or row[key] < 0:
                    raise ValueError("Event counts must be nonnegative integers.")
            if (
                row["Historical events"] < 1
                or not 1 <= row["Active history days"] <= row["Historical events"]
                or row["Events in previous window"] > row["Historical events"]
            ):
                raise ValueError("Event row is outside its past-active population.")
            if self.spec.recipe == "recurrence" and row["Outcome"] not in {0, 1}:
                raise ValueError("Recurrence labels must be zero or one.")
        if (
            self.derived_context.row_ids != ids
            or len(self.memberships) != len(ids)
            or [r["row_id"] for r in self.memberships] != ids
        ):
            raise ValueError("Event table membership does not match its derived rows.")
        if not set(self.train_ids + self.test_ids) <= set(ids) or set(self.train_ids) & set(self.test_ids):
            raise ValueError("Invalid event task train/test membership.")
        if len(self.train_ids) != len(set(self.train_ids)) or len(self.test_ids) != len(set(self.test_ids)):
            raise ValueError("Event task split memberships repeat.")
        if self.records:
            final = max(pd.to_datetime(r["Anchor timestamp"], utc=True) for r in self.records)
            expected_test = [
                i
                for i, r in enumerate(self.records)
                if pd.to_datetime(r["Anchor timestamp"], utc=True) == final
            ]
            expected_train = [
                i
                for i in ids
                if pd.to_datetime(self.records[i]["Anchor timestamp"], utc=True)
                + pd.Timedelta(self.spec.horizon_days + self.spec.reporting_delay_days, unit="D")
                <= final
            ]
            if self.train_ids != expected_train or self.test_ids != expected_test:
                raise ValueError("Event task holdout must be exactly the last complete anchor.")
        source = set(self.source_context.row_ids)
        for membership in self.memberships:
            if (
                set(membership) != {"row_id", "anchor", "entity", "history_rows", "outcome_rows"}
                or type(membership["row_id"]) is not int
            ):
                raise ValueError("Invalid event membership shape.")
            row = self.records[membership["row_id"]]
            if membership["entity"] != row["Entity"] or membership["anchor"] != row["Anchor timestamp"]:
                raise ValueError("Event membership entity or anchor differs from its derived row.")
            for key in ["history_rows", "outcome_rows"]:
                values = membership[key]
                if (
                    not isinstance(values, list)
                    or any(type(v) is not int for v in values)
                    or len(set(values)) != len(values)
                    or not set(values) <= source
                ):
                    raise ValueError("Event membership references invalid source rows.")
            if set(membership["history_rows"]) & set(membership["outcome_rows"]):
                raise ValueError("An event cannot belong to both a historical and forward window.")
        if self.model and (
            self.model.context != self.derived_context.id
            or self.model.train_ids != self.train_ids
            or self.model.test_ids != self.test_ids
        ):
            raise ValueError("Event model uses a different table or holdout.")
        if self.model:
            from firstlook.model_protocol import validate_recorded_protocol

            validate_recorded_protocol(self.model)
        return self


def _events(dataset, ctx, spec):
    if (
        spec.dataset != dataset.record.fingerprint
        or ctx.id != dataset.context(ctx.row_ids, ctx.focus, ctx.assumption).id
    ):
        raise ValueError("Event task belongs to another source context.")
    references = [spec.entity, spec.event_time] + [f for f in [spec.event_id, spec.known_time] if f]
    if len(set(references)) != len(references):
        raise ValueError("Entity, event identity and timing fields must have distinct roles.")
    if any(f not in dataset.frame or dataset.field(f).excluded for f in references):
        raise ValueError("Event task references an unknown or excluded field.")
    if any(dataset.field(f).role != Role.TIME for f in [spec.event_time, spec.known_time] if f):
        raise ValueError("Event and availability times must be parsed timestamps.")
    frame = dataset.frame.loc[ctx.row_ids]
    dates = pd.to_datetime(frame[spec.event_time], utc=True, errors="coerce")
    known = pd.to_datetime(frame[spec.known_time], utc=True, errors="coerce") if spec.known_time else dates
    if ((known - dates) > pd.Timedelta(spec.reporting_delay_days, unit="D")).any():
        raise ValueError(
            "Observed reporting delays exceed the declared outcome-reporting bound. Review the timestamps or explicitly increase the bound."
        )
    usable = frame[spec.entity].notna() & dates.notna()
    if spec.event_id:
        usable &= frame[spec.event_id].notna()
    if not usable.all():
        raise ValueError(
            f"{int((~usable).sum())} source events lack entity, event time or the chosen identity. Resolve their meaning before constructing negative labels; they cannot be silently dropped."
        )
    data = pd.DataFrame(
        {
            "entity": frame.loc[usable, spec.entity].astype(str),
            "event": dates.loc[usable],
            "known": known.loc[usable],
            "identity": frame.loc[usable, spec.event_id].astype(str)
            if spec.event_id
            else frame.index[usable].astype(str),
        }
    )
    rows = []
    for identity, part in data.groupby("identity", sort=False):
        if part["entity"].nunique() != 1 or part["event"].nunique() != 1:
            raise ValueError("A declared event identity maps to different entities or event times.")
        rows.append(
            {
                "identity": identity,
                "entity": part["entity"].iloc[0],
                "event": part["event"].iloc[0],
                "known": part["known"].max() if part["known"].notna().all() else pd.NaT,
                "source_rows": part.index.tolist(),
            }
        )
    if not rows:
        raise ValueError("No events have complete entity and timing identities.")
    events = pd.DataFrame(rows)
    events["known"] = pd.to_datetime(events["known"], utc=True)
    return events, {
        "source_rows": len(frame),
        "unusable_source_rows": int((~usable).sum()),
        "distinct_events": len(rows),
        "deduplicated_source_rows": int(usable.sum()) - len(rows),
        "unknown_availability_source_rows": int(known.isna().sum()),
        "duplicate_availability_policy": "Repeated event identities use the latest availability timestamp, or unknown if any constituent timestamp is missing.",
    }


def prepare_event_task(dataset, ctx, specification, progress=lambda _: None, cancelled=lambda: False):
    spec = EventTaskSpec.model_validate(specification)
    events, preparation = _events(dataset, ctx, spec)
    anchors = [pd.to_datetime(v, utc=True) for v in spec.anchors]
    end = pd.to_datetime(spec.complete_through, utc=True)
    records, memberships, anchor_counts, censored = [], [], [], []
    delta = pd.Timedelta(spec.horizon_days, unit="D")
    for anchor in anchors:
        if cancelled():
            raise ValueError("Event task preparation cancelled.")
        if anchor + delta > end:
            censored.append(anchor.isoformat())
            continue
        progress("Constructing past population and complete forward labels at " + anchor.date().isoformat())
        history = events[
            (events.event > anchor - pd.Timedelta(spec.lookback_days, unit="D"))
            & (events.event <= anchor)
            & (events.known <= anchor)
        ]
        future = events[(events.event > anchor) & (events.event <= anchor + delta)]
        future_groups = {key: part for key, part in future.groupby("entity", sort=True)}
        count = 0
        for entity, past in history.groupby("entity", sort=True):
            outcome = future_groups.get(entity, future.iloc[:0])
            previous = past[past.event > anchor - delta]
            records.append(
                {
                    "Entity": entity,
                    "Anchor timestamp": anchor.isoformat(),
                    "Historical events": len(past),
                    "Events in previous window": len(previous),
                    "Active history days": past.event.dt.floor("D").nunique(),
                    "Days since last event": (anchor - past.event.max()).total_seconds() / 86400,
                    "Days since first observed event": (anchor - past.event.min()).total_seconds() / 86400,
                    "Outcome": int(len(outcome) > 0) if spec.recipe == "recurrence" else len(outcome),
                }
            )
            memberships.append(
                {
                    "row_id": len(records) - 1,
                    "anchor": anchor.isoformat(),
                    "entity": entity,
                    "history_rows": sorted(i for group in past.source_rows for i in group),
                    "outcome_rows": sorted(i for group in outcome.source_rows for i in group),
                }
            )
            count += 1
            if len(records) > 10_000:
                raise ValueError(
                    "The event task exceeds 10,000 derived rows. Reduce anchors or the source population."
                )
        anchor_counts.append(
            {"anchor": anchor.isoformat(), "rows": count, "outcome_window_end": str(anchor + delta)}
        )
    if len(anchor_counts) < 3 or any(r["rows"] == 0 for r in anchor_counts):
        raise ValueError(
            "Choose at least three complete, nonempty anchor populations; incomplete windows are never negative labels."
        )
    frame = pd.DataFrame(records)
    frame["Anchor timestamp"] = pd.to_datetime(frame["Anchor timestamp"], utc=True)
    raw = frame.to_csv(index=False).encode()
    derived = from_frame(
        frame,
        "event-task.csv",
        raw=raw,
        source="Finite event task derived from exact recorded source membership",
    )
    derived.field("f000").role = Role.ID
    derived.field("f001").role = Role.TIME
    derived.field("f007").role = Role.BOOL if spec.recipe == "recurrence" else Role.MEASURE
    for fid in ["f002", "f003", "f004", "f005", "f006"]:
        derived.field(fid).role = Role.MEASURE
    # Rebuild only after roles are finalized. This is a distinct task, not a mutation of the source contract.
    from firstlook.semantic.profile import build_model

    model = build_model(derived)
    task = TaskDefinition(
        dataset=derived.record.fingerprint,
        question=f"{'Will another event occur' if spec.recipe == 'recurrence' else 'How many events will occur'} within {spec.horizon_days} days for entities active in the preceding {spec.lookback_days} days?",
        purpose="prediction",
        unit="Entity at an anchor timestamp",
        population="Entities with at least one recorded, available event in the bounded past window",
        target="f007",
        decision_time="At each recorded anchor",
        anchor_field="f001",
        horizon_days=spec.horizon_days,
        complete_through=spec.complete_through,
    )
    model.search["event_protocol"] = {"source_context": ctx.id, "spec": spec.model_dump(mode="json")}
    model.search["analytical_task"] = task.model_dump(mode="json")
    model.search["availability"] = {
        fid: AvailabilityRule(
            field=fid,
            status="known_at_anchor",
            basis=availability_basis(task),
            evidence="Computed only from recorded events whose event and information-availability times are at or before the anchor.",
        ).model_dump(mode="json")
        for fid in ["f002", "f003", "f004", "f005", "f006"]
    }
    derived.record.semantic_model = validate_model(derived, model)
    final_anchor = anchors[len(anchor_counts) - 1]
    train_ids = frame.index[
        frame["Anchor timestamp"] + pd.Timedelta(spec.horizon_days + spec.reporting_delay_days, unit="D")
        <= final_anchor
    ].tolist()
    test_ids = frame.index[frame["Anchor timestamp"] == final_anchor].tolist()
    if not train_ids:
        raise ValueError(
            "No historical outcome windows are fully known by the final anchor under the declared reporting-delay bound."
        )
    if set(frame.loc[train_ids, "Anchor timestamp"]) & set(frame.loc[test_ids, "Anchor timestamp"]):
        raise ValueError("Anchor memberships cannot overlap.")
    values = clean(records)
    table_hash = digest(values)
    preparation.update(
        {
            "anchor_populations": anchor_counts,
            "censored_anchors": censored,
            "coverage": spec.complete_through,
            "reporting_delay_days": spec.reporting_delay_days,
            "purged_training_rows": int((frame["Anchor timestamp"] < final_anchor).sum()) - len(train_ids),
            "population_rule": "Past-only recorded activity; future-only entities are excluded. Zero outcomes require the explicit coverage attestation.",
            "split_rule": "The last complete anchor is held out. Earlier anchors train only when their outcome window plus the attested reporting delay ends by that anchor; later labels are purged.",
            "generalization": "Later activity of previously observed entities, not unseen-entity generalization",
            "warnings": [
                "Completeness and event identity are user attestations. Absence of a recorded event is a negative label only within that declared coverage.",
                "Repeated anchors for the same entity are dependent. The final holdout is exploratory; no independent-sample significance claim is made.",
            ],
        }
    )
    return EventTaskRun(
        id=digest([ctx.id, spec.model_dump(), table_hash]),
        source_context=ctx,
        spec=spec,
        derived_schema=derived.record,
        derived_context=derived.context(),
        records=values,
        memberships=memberships,
        table_hash=table_hash,
        train_ids=train_ids,
        test_ids=test_ids,
        preparation=preparation,
    )


def event_dataset(run):
    run = EventTaskRun.model_validate(run)
    frame = pd.DataFrame(run.records)
    frame["Anchor timestamp"] = pd.to_datetime(frame["Anchor timestamp"], utc=True)
    raw = frame.to_csv(index=False).encode()
    if hashlib.sha256(raw).hexdigest() != run.derived_schema.fingerprint:
        raise ValueError("Recorded derived event bytes disagree with their schema fingerprint.")
    frame.columns = [f.id for f in run.derived_schema.fields]
    dataset = Dataset(run.derived_schema.model_copy(deep=True), frame, raw)
    validate_model(dataset, get_model(dataset))
    if dataset.context().id != run.derived_context.id:
        raise ValueError("Derived event task context changed.")
    return dataset


def event_preflight(run):
    from firstlook.model_protocol import model_preflight

    run = EventTaskRun.model_validate(run)
    dataset = event_dataset(run)
    return model_preflight(
        dataset, run.derived_context, "f007", "time", "f001", fixed_split=(run.train_ids, run.test_ids)
    )


def evaluate_event_task(run, provider=None, progress=lambda _: None, cancelled=lambda: False):
    from firstlook.modeling import run_model

    run = EventTaskRun.model_validate(run)
    if run.model:
        raise ValueError(
            "This task already has a final held-out evaluation. Do not tune against that holdout."
        )
    dataset = event_dataset(run)
    previous = dataset.frame.loc[run.test_ids, "f003"]
    baseline = (
        previous.gt(0).astype(int).to_numpy() if run.spec.recipe == "recurrence" else previous.to_numpy()
    )
    run.model = run_model(
        dataset,
        run.derived_context,
        "f007",
        "time",
        "f001",
        provider=provider,
        progress=progress,
        cancelled=cancelled,
        fixed_split=(run.train_ids, run.test_ids),
        reference_predictions={"Previous window": baseline},
    )
    run.model.warnings.extend(run.preparation["warnings"])
    return EventTaskRun.model_validate(run.model_dump(mode="json"))


def validate_event_source(dataset, run):
    run = EventTaskRun.model_validate(run)
    rebuilt = prepare_event_task(dataset, run.source_context, run.spec)
    if (
        rebuilt.table_hash != run.table_hash
        or rebuilt.memberships != run.memberships
        or rebuilt.train_ids != run.train_ids
        or rebuilt.test_ids != run.test_ids
        or rebuilt.derived_context.id != run.derived_context.id
    ):
        raise ValueError("Recorded event features, labels or memberships disagree with the exact source.")
    return True
