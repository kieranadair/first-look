"""Seeded analytical checks against known patterns and nulls; no model-as-judge or live APIs."""

from bisect import bisect_right
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from firstlook.contracts import Role
from firstlook.discovery import analyze, correlations, discover, plan_for
from firstlook.ingest import from_frame
from firstlook.semantic.profile import build_model


def dataset(frame):
    ds = from_frame(frame, "evaluation.csv", raw=frame.to_csv(index=False).encode())
    for f in ds.record.fields:
        if pd.api.types.is_numeric_dtype(ds.frame[f.id]):
            f.role = Role.MEASURE
    ds.record.semantic_model = build_model(ds)
    return ds


def main():
    results = []
    start = time.perf_counter()
    for seed in [17, 31, 82, 109, 151, 211, 307, 401, 503, 601]:
        rng = np.random.default_rng(seed)
        x = np.sort(rng.uniform(-3, 3, 400))
        branch = np.repeat(np.sort(rng.uniform(1, 200, 200)), 2)
        cases = {
            "linear": (x, 2 * x + rng.normal(0, 0.1, 400)),
            "curved_center": (x, x * x),
            "variance_only": (branch, branch * np.tile([-1, 1], 200)),
            "independent_null": (rng.normal(size=400), rng.normal(size=400)),
        }
        for name, (a, b) in cases.items():
            frame = pd.DataFrame({"x": a, "y": b})
            stats = correlations(frame, "x", "y")
            bins = pd.qcut(frame.x, 5, duplicates="drop")
            medians = frame.groupby(bins, observed=True).y.median()
            median_range = (medians.max() - medians.min()) / max(
                float(frame.y.quantile(0.75) - frame.y.quantile(0.25)), 1e-12
            )
            old = max(abs(stats["pearson"]), abs(stats["spearman"])) >= 0.3 or median_range >= 0.5
            inv = discover(dataset(frame))
            found = any(f.family in {"relationship", "quantile_bin_summary"} for f in inv.findings)
            results.append(
                {
                    "seed": seed,
                    "pattern": name,
                    "expected_structure": name != "independent_null",
                    "previous_center_or_association_screen": bool(old),
                    "current_shortlist_contains_witness": found,
                }
            )
    values = list(range(1201)) + [1199] * 48799
    ds = dataset(pd.DataFrame({"values": values}))
    ordered = sorted(values)
    curves = []
    for version in [1, 2]:
        result, _ = analyze(
            ds,
            ds.context(),
            plan_for(ds.context(), "ecdf", ["f000"], "CDF representation audit", {"recipe_version": version}),
        )
        xs = [r["x"] for r in result.records]
        probabilities = [r["value"] for r in result.records]
        errors = []
        for threshold in set(values):
            previous = bisect_right(xs, threshold) - 1
            actual = probabilities[previous] if previous >= 0 else 0
            errors.append(abs(bisect_right(ordered, threshold) / len(ordered) - actual))
        curves.append(
            {
                "recipe_version": version,
                "plotted_vertices": len(xs),
                "max_vertical_error_independent_oracle": max(errors),
                "reported_error": result.metadata.get("ecdf_error"),
            }
        )
    summaries = []
    for name in cases:
        subset = [r for r in results if r["pattern"] == name]
        summaries.append(
            {
                "pattern": name,
                "fixtures": len(subset),
                "previous_witnesses": sum(r["previous_center_or_association_screen"] for r in subset),
                "current_witnesses": sum(r["current_shortlist_contains_witness"] for r in subset),
                "interpretation": "False promotion audit; no structure planted"
                if name == "independent_null"
                else "Recovery of this specified synthetic pattern",
            }
        )
    report = {
        "scope": "Finite synthetic patterns and nulls; not human productivity, causal validity or general detection guarantees. Previous screen is reconstructed arithmetic, not a full old UI comparison.",
        "seeded_summary": summaries,
        "fixtures": results,
        "cdf_representation": curves,
        "seconds": time.perf_counter() - start,
        "live_provider_calls": False,
        "screenshots": False,
    }
    Path("reports/exploration-evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "fixtures"}, indent=2))


if __name__ == "__main__":
    main()
