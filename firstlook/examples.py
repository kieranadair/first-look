"""Small real examples and reproducible fixtures with declared known properties."""

from pathlib import Path

import numpy as np
import pandas as pd

from firstlook.ingest import Dataset, load_table

ROOT = Path(__file__).resolve().parent.parent / "examples"
CATALOG = {
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
    "null": (
        "When little is there",
        "Independent variables: restraint is a useful analytical outcome.",
        "grain",
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
