"""Publish actual local timings and RSS; these are measurements, not Cloud guarantees."""

import json
import platform
import resource
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil
import numpy as np
import pandas as pd

from firstlook.challenges import automatic_challenges
from firstlook.discovery import discover
from firstlook.evidence import environment, export_bundle, import_bundle, recompute
from firstlook.examples import load_example
from firstlook.ingest import load_table
from firstlook.modeling import run_model
from firstlook.profiling import profile
from firstlook.state import Workspace, pin


def main():
    timings = {}

    def timed(label, fn):
        start = time.perf_counter()
        result = fn()
        timings[label] = round(time.perf_counter() - start, 4)
        return result

    ds = timed("load_penguins", lambda: load_example("penguins"))
    timed("profile_penguins", lambda: profile(ds))
    inv = timed("discover_penguins", lambda: discover(ds))
    timed("challenge_penguins", lambda: automatic_challenges(ds, inv))
    nonlinear = load_example("nonlinear")
    run = timed("local_models_600_rows", lambda: run_model(nonlinear, nonlinear.context(), "f003"))
    ws = Workspace()
    ws.load(ds)
    ws.investigation = inv
    pin(ws, inv.findings[0].id)
    blob = timed("export_penguins", lambda: export_bundle(ws, True))
    replay = timed("import_penguins", lambda: import_bundle(blob))
    comparisons = timed("recompute_penguins", lambda: recompute(replay))
    assert all(c["status"] == "match" for c in comparisons)
    Path("reports/example-investigation.zip").write_bytes(blob)

    def investigate(key):
        start = time.perf_counter()
        d = load_example(key)
        result = discover(d)
        automatic_challenges(d, result)
        return time.perf_counter() - start

    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = timed(
            "two_concurrent_investigations", lambda: list(pool.map(investigate, ["reversal", "bike"]))
        )
    timed("repeat_discovery_10", lambda: [investigate("reversal") for _ in range(10)])
    rng = np.random.default_rng(20261120)
    x = rng.normal(size=(50_000, 15))
    large_frame = pd.DataFrame(x, columns=[f"measure_{i}" for i in range(15)])
    large_frame.insert(0, "outcome", x[:, 0] ** 2 + x[:, 1] + rng.normal(0, 0.4, 50_000))
    large_frame.insert(0, "record_id", np.arange(50_000))
    large_frame["region"] = rng.choice(list("ABCD"), 50_000)
    large_frame["recorded_at"] = pd.date_range("2020-01-01", periods=50_000, freq="h")
    large_frame["flag"] = rng.integers(0, 2, 50_000)
    raw = large_frame.to_csv(index=False, float_format="%.5g").encode()
    large = timed("load_50000x20", lambda: load_table(raw, "representative.csv"))
    timed("profile_50000x20", lambda: profile(large))
    large_inv = timed("discover_50000x20", lambda: discover(large))
    timed("challenge_50000x20", lambda: automatic_challenges(large, large_inv))
    timed("local_models_10000_of_50000", lambda: run_model(large, large.context(), "f001"))
    report = {
        "environment": environment(),
        "machine": {
            "platform": platform.platform(),
            "logical_cpus": psutil.cpu_count(),
            "machine_memory_GiB": round(psutil.virtual_memory().total / 1024**3, 2),
        },
        "timings_seconds": timings,
        "concurrent_durations_seconds": concurrent,
        "peak_process_RSS_MiB": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        "current_process_RSS_MiB": round(psutil.Process().memory_info().rss / 1024**2, 2),
        "bundle_bytes": len(blob),
        "replay_matches": len(comparisons),
        "nonlinear_gradient_boosting_R2": run.metrics["Gradient boosting"]["R²"],
        "hosted_models_ran": False,
        "large_workload": {
            "rows": 50_000,
            "fields": 20,
            "source_bytes": len(raw),
            "decoded_MiB": round(large.frame.memory_usage(deep=True).sum() / 1024**2, 2),
        },
        "scope": "Single Linux process; local measured fixtures. Not a Cloud capacity or model accuracy benchmark.",
    }
    Path("reports/benchmark.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
