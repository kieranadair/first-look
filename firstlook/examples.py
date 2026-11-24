"""Small real examples and reproducible fixtures with declared known properties."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from firstlook.ingest import Dataset, load_table

ROOT = Path(__file__).resolve().parent.parent / "examples"
CATALOG = {
    "events": (
        "What happens next?",
        "Observed events, delayed information and a complete future-window task.",
        "event_repeat",
    ),
    "reversal": (
        "The hidden reversal",
        "A strong pooled relationship can tell a different story within groups.",
        "compare_arrows",
    ),
    "penguins": ("Palmer Penguins", "Real measurements, recorded groups and missing information.", "nature"),
    "bike": (
        "A city on two wheels",
        "Time coverage, weather and the trap of predicting a total from its parts.",
        "directions_bike",
    ),
    "nonlinear": (
        "Beyond a straight line",
        "Weak marginal summaries, joint structure and a model lens.",
        "show_chart",
    ),
    "semantic": (
        "Orders aren’t rows",
        "Repeated order values, overlapping categories and complete event days. See what analytical meaning changes.",
        "schema",
    ),
    "null": (
        "When little is there",
        "Independent variables: restraint is a useful analytical outcome.",
        "grain",
    ),
    "text": (
        "From words to evidence",
        "Support notes, frozen text features and a matched predictive comparison.",
        "text_snippet",
    ),
}


def synthetic(kind: str, seed: int = 42, n: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    if kind == "reversal":
        group = np.repeat(["Coastal", "Inland", "Upland"], n // 3)
        offset = np.repeat([0.0, 4.0, 8.0], n // 3)
        x = rng.normal(0, 0.8, len(group)) + offset
        y = 3 * offset - x + rng.normal(0, 0.5, len(group))
        return pd.DataFrame(
            {
                "record_id": np.arange(len(group)),
                "exposure": x,
                "response": y,
                "region": group,
                "sampling_day": pd.date_range("2024-01-01", periods=len(group), freq="h"),
            }
        )
    x, z = rng.uniform(-3, 3, n), rng.uniform(-3, 3, n)
    if kind == "nonlinear":
        y = x**2 + 2 * np.sin(z) + rng.normal(0, 0.4, n)
        return pd.DataFrame(
            {"record_id": np.arange(n), "x": x, "z": z, "outcome": y, "cohort": np.where(z > 0, "B", "A")}
        )
    return pd.DataFrame(
        {
            "record_id": np.arange(n),
            "alpha": rng.normal(size=n),
            "beta": rng.normal(size=n),
            "gamma": rng.normal(size=n),
            "cohort": rng.choice(["A", "B"], n),
        }
    )


def load_example(key: str) -> Dataset:
    if key == "events":
        return event_example()
    if key == "text":
        return text_example()
    if key == "semantic":
        return semantic_example()
    if key in {"reversal", "nonlinear", "null"}:
        df = synthetic(key)
        raw = df.to_csv(index=False).encode()
        ds = load_table(raw, key + ".csv")
        ds.record.name = CATALOG[key][0]
        ds.record.source = "Seeded synthetic fixture; seed 42. See generator for the known properties."
        return ds
    path = ROOT / ("penguins.csv" if key == "penguins" else "bike_daily.csv")
    if not path.exists():
        raise ValueError("This example file is unavailable. Choose a seeded example or upload a table.")
    ds = load_table(path.read_bytes(), path.name)
    ds.record.name = CATALOG[key][0]
    ds.record.source = (
        "Palmer Penguins · CC0 · Horst, Hill and Gorman"
        if key == "penguins"
        else "UCI Bike Sharing daily · CC BY 4.0 · Fanaee-T"
    )
    return ds


def event_example() -> Dataset:
    """Known synthetic observation coverage; no predictive results are supplied."""
    from firstlook.semantic.model import get_model, commit_model

    rng = np.random.default_rng(20261125)
    records = []
    start = pd.Timestamp("2024-01-01", tz="UTC")
    for entity in range(160):
        probability = rng.uniform(0.015, 0.09)
        for day in range(240):
            if rng.random() < probability:
                event = start + pd.Timedelta(day * 24 + int(rng.integers(0, 24)), unit="h")
                records.append(
                    {
                        "customer_id": f"C{entity:04}",
                        "event_id": f"E{len(records):06}",
                        "event_timestamp": event,
                        "available_timestamp": event + pd.Timedelta(int(rng.integers(0, 36)), unit="h"),
                        "channel": rng.choice(["Web", "Store"]),
                    }
                )
    frame = pd.DataFrame(records).sort_values("event_timestamp").reset_index(drop=True)
    ds = load_table(frame.to_csv(index=False).encode(), "synthetic-events.csv")
    ds.record.name = CATALOG["events"][0]
    ds.record.source = "Seeded synthetic event fixture; seed 20261125. Complete event coverage is supplied by the generator, not inferred."
    ds.record.description = "One observed purchase event per event_id. Information can arrive up to 35 hours later. The generator records all events through 2024-08-27 UTC; this supplied truth is for the synthetic example only."
    model = get_model(ds).model_copy(deep=True)
    for policy in model.time_policies:
        if ds.label(policy.field) == "event_timestamp":
            policy.kind, policy.confirmed, policy.coverage_complete, policy.complete_through = (
                "event",
                True,
                True,
                "2024-08-27",
            )
    commit_model(
        ds,
        model,
        "table",
        "synthetic_event_coverage",
        "Generator-supplied complete event recording; not automatically inferred",
    )
    return ds


def text_example() -> Dataset:
    """Synthetic pre-resolution notes; no model-coded answers are fabricated."""
    from firstlook.contracts import Role
    from firstlook.semantic.model import get_model, commit_model

    rng = np.random.default_rng(20261124)
    notes = [
        "The parcel arrived crushed and the casing is cracked.",
        "The package is intact but it contains a different item from my order.",
        "Please explain how to configure the item; it looks intact.",
        "Both a cracked case and a missing accessory need attention.",
    ]
    kinds = rng.integers(0, 4, 360)
    frame = pd.DataFrame(
        {
            "case_id": [f"C{i:04}" for i in range(360)],
            "customer_id": [f"U{i % 60:03}" for i in range(360)],
            "opening_note": [notes[k] for k in kinds],
            "queue": rng.choice(["Standard", "Priority"], 360),
            "prior_cases": rng.integers(0, 8, 360),
            "resolution_hours": np.maximum(1, np.array([15, 9, 3, 22])[kinds] + rng.normal(0, 2, 360)).round(
                2
            ),
        }
    )
    ds = load_table(frame.to_csv(index=False).encode(), "support_notes.csv")
    ds.record.name = CATALOG["text"][0]
    ds.record.source = (
        "Seeded synthetic support fixture; seed 20261124. No real customer data or Jev outputs."
    )
    ds.record.description = "Opening notes are recorded when a support case is created, before its resolution duration is known. Customers can have several cases."
    field = next(f for f in ds.record.fields if f.name == "opening_note")
    field.role = field.proposed_role = Role.TEXT
    model = get_model(ds)
    model.model_group = next(f.id for f in ds.record.fields if f.name == "customer_id")
    commit_model(ds, model)
    return ds


def semantic_example() -> Dataset:
    """Generator supplies ground truth declarations; these are not inferred facts."""
    from firstlook.contracts import digest
    from firstlook.semantic.model import commit_model, get_model
    from firstlook.semantic_contracts import Metric

    rng = np.random.default_rng(2718)
    rows = []
    categories = ["Office", "Furniture", "Technology"]
    for order in range(120):
        date = pd.Timestamp(datetime(2024, 1, 1) + timedelta(days=int(rng.integers(0, 60))))
        customer = f"C{int(rng.integers(1, 19)):02}"
        order_rows: list[dict[str, Any]] = []
        for _ in range(int(rng.integers(1, 5))):
            category = categories[int(rng.integers(0, 3))]
            quantity = int(rng.integers(1, 8))
            price = round(float(rng.uniform(8, 140)), 2)
            sales = round(quantity * price, 2)
            profit = round(sales * float(rng.uniform(-0.15, 0.4)), 2)
            order_rows.append(
                dict(
                    line_id=len(rows) + len(order_rows) + 1,
                    order_id=f"O{order:03}",
                    customer_id=customer,
                    order_date=date,
                    category=category,
                    region=["North", "South", "West"][order % 3],
                    sales=sales,
                    profit=profit,
                    quantity=quantity,
                    unit_price=price,
                )
            )
        total = round(sum(row["sales"] for row in order_rows), 2)
        rows.extend({**row, "order_total": total} for row in order_rows)
    df = pd.DataFrame(rows)
    ds = load_table(df.to_csv(index=False).encode(), "orders-arent-rows.csv")
    ds.record.name = CATALOG["semantic"][0]
    ds.record.source = "Seeded synthetic semantic demonstration · seed 2718. The generator explicitly supplies the analytical definitions and complete event coverage."
    ds.record.description = "One order line per row. Order totals repeat on every line. Orders can include several categories. All generated orders in January–February 2024 are recorded; absent event days are zero."
    model = get_model(ds).model_copy(deep=True)
    fields = {f.name: f.id for f in ds.record.fields}
    order = next(e for e in model.entities if e.keys == [fields["order_id"]])
    line = next(e for e in model.entities if e.keys == [fields["line_id"]])
    model.grain = (
        "One product-category line within an order; repeated order totals are entity values, not row amounts."
    )
    model.grain_confirmed = True
    model.grain_entity = line.id
    for name in ["sales", "profit", "quantity", "order_total", "unit_price"]:
        meaning = model.meaning(fields[name])
        meaning.kind = "rate" if name == "unit_price" else "flow"
        meaning.confirmed = True
        meaning.allowed_transforms = (
            ["identity", "difference", "percent_change"]
            if name == "profit"
            else ["identity", "log", "sqrt", "zscore", "difference", "percent_change"]
        )
        if name != "quantity":
            meaning.currency = "USD"
            meaning.basis = "Nominal synthetic dollars; no conversion or inflation adjustment."
    model.meaning(fields["profit"]).available_at_prediction = False
    for metric in model.metrics:
        if (
            metric.field in {fields["sales"], fields["profit"], fields["quantity"]}
            and metric.aggregation == "sum"
        ):
            metric.confirmed = True
    for policy in model.time_policies:
        policy.kind = "event"
        policy.expected_frequency = "D"
        policy.gap_policy = "zero"
        policy.coverage_complete = True
        policy.complete_through = "2024-02-29"
        policy.confirmed = True
    definitions = [
        Metric(
            id="demo_order_average",
            label="Sales per distinct order",
            aggregation="average_per_entity",
            field=fields["sales"],
            entity=order.id,
            confirmed=True,
            description="Recorded line sales divided by distinct orders with recorded sales. Contrast with equal row weighting.",
        ),
        Metric(
            id="demo_allocated_orders",
            label="Allocated order value",
            aggregation="sum",
            field=fields["order_total"],
            entity=order.id,
            allocation="equal",
            confirmed=True,
            description="Deduplicate order totals, then allocate each total equally across its distinct recorded category memberships.",
        ),
        Metric(
            id="demo_weighted_price",
            label="Quantity-weighted unit price",
            aggregation="weighted_mean",
            field=fields["unit_price"],
            weight=fields["quantity"],
            confirmed=True,
            description="Total price × units divided by total units. Exposure is the recorded unit quantity.",
        ),
        Metric(
            id="demo_margin",
            label="Recomposed profit margin",
            aggregation="ratio",
            numerator="m_total_" + fields["profit"],
            denominator="m_total_" + fields["sales"],
            denominator_scope="group",
            confirmed=True,
            description="Sum recorded profit divided by sum recorded sales inside each group; never average line margins.",
        ),
    ]
    model.metrics += definitions
    commit_model(
        ds,
        model,
        "table",
        "demonstration",
        {
            "generator": "semantic_example",
            "seed": 2718,
            "definitions": [m.id for m in definitions],
            "annotation": digest("Generator-defined synthetic truths"),
        },
    )
    return ds
