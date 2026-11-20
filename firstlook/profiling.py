"""Deterministic summaries, with explicit support and numerical conventions."""

from __future__ import annotations

import pandas as pd

from firstlook.contracts import clean
from firstlook.ingest import Dataset


def profile(dataset: Dataset) -> dict:
    frame = dataset.frame
    fields = {}
    for f in dataset.record.fields:
        s = frame[f.id]
        item = {
            "id": f.id,
            "name": f.name,
            "role": f.role.value,
            "dtype": str(s.dtype),
            "count": int(s.notna().sum()),
            "missing": int(s.isna().sum()),
            "distinct": int(s.nunique()),
            "unique_ratio": s.nunique() / len(s),
            "constant": s.nunique() <= 1,
            "parse_failures": f.parse_failures,
            "examples": s.dropna().astype(str).head(4).tolist(),
        }
        if pd.api.types.is_numeric_dtype(s):
            v = s.dropna().astype(float)
            item.update(
                clean(
                    {
                        "mean": v.mean(),
                        "median": v.median(),
                        "std": v.std(ddof=1),
                        "min": v.min(),
                        "max": v.max(),
                        "quantiles": v.quantile(
                            [0, 0.01, 0.25, 0.5, 0.75, 0.99, 1], interpolation="linear"
                        ).to_dict(),
                    }
                )
            )
        elif pd.api.types.is_datetime64_any_dtype(s):
            item.update(clean({"start": s.min(), "end": s.max()}))
        else:
            freq = s.dropna().astype(str).value_counts().head(12)
            item["frequencies"] = freq.to_dict()
            item["frequency_coverage"] = int(freq.sum()) / max(int(s.notna().sum()), 1)
        fields[f.id] = clean(item)
    return {
        "fingerprint": dataset.record.fingerprint,
        "rows": len(frame),
        "columns": len(frame.columns),
        "missing": int(frame.isna().sum().sum()),
        "cells": int(frame.size),
        "duplicates": int(frame.duplicated().sum()),
        "memory_bytes": int(frame.memory_usage(deep=True).sum()),
        "fields": fields,
        "candidate_keys": [
            f.id for f in dataset.record.fields if frame[f.id].notna().all() and frame[f.id].is_unique
        ],
        "method": "Linear quantiles; sample standard deviation (ddof=1); missing is not zero.",
    }
