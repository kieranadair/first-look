"""Literal source evidence; candidates do not establish missingness or invalidity."""

from __future__ import annotations

import re
import pandas as pd

MARKERS = {
    "",
    "\\N",
    "NULL",
    "null",
    "None",
    "none",
    "NaN",
    "nan",
    "N/A",
    "n/a",
    "NA",
    "-",
    "?",
    "unknown",
    "Unknown",
}
PLACEHOLDERS = {"1900-01-01", "1970-01-01", "1753-01-01", "9999-12-31"}


def unsafe_integer_string(value):
    digits = str(value).lstrip("+-").lstrip("0") or "0"
    return len(digits) > 16 or (len(digits) == 16 and digits > "9007199254740992")


def inspect_source(frame, missing_tokens):
    fields = {}
    for position in range(len(frame.columns)):
        series = frame.iloc[:, position]
        text = series.dropna().astype(str)
        trimmed = text.str.strip()
        counts = text[trimmed.isin(MARKERS)].value_counts()
        numbers = pd.to_numeric(trimmed, errors="coerce")
        large = text[trimmed.str.match(r"^[+-]?\d+$")]
        fields[f"f{position:03}"] = {
            "name": str(frame.columns[position]),
            "rows": len(frame),
            "physical_nulls": int(series.isna().sum()),
            "literal_distinct": int(text.nunique()),
            "markers": [
                {"value": str(k), "count": int(v), "declared_missing": str(k) in missing_tokens}
                for k, v in counts.items()
            ],
            "numeric_sentinel_candidates": [
                {"value": v, "count": int(numbers.eq(v).sum())}
                for v in [0, -1, 999, 9999]
                if numbers.eq(v).any()
            ],
            "placeholder_dates": [
                {"value": v, "count": int(trimmed.str.startswith(v).sum())}
                for v in sorted(PLACEHOLDERS)
                if trimmed.str.startswith(v).any()
            ],
            "large_integer_strings": sum(unsafe_integer_string(v) for v in large),
            "leading_zero_strings": int(trimmed.str.match(r"^[+-]?0\d+$").sum()),
            "identifier_name": bool(
                re.search(r"(^id$|(^|[ _])id$|_id$|identifier|_code$)", str(frame.columns[position]), re.I)
            ),
        }
    return {
        "scope": "All literal source rows before coercion and declared missing-token replacement",
        "rows": len(frame),
        "fields": fields,
    }


def inspection_rows(dataset):
    rows = []
    for fid, item in dataset.record.source_profile.get("fields", {}).items():
        field = dataset.field(fid)
        rows.append(
            {
                "Field": field.name,
                "Source non-null distinct": item["literal_distinct"],
                "Parsed non-null distinct": int(dataset.frame[fid].nunique()),
                "Marker candidates": "; ".join(f"{r['value']!r}: {r['count']}" for r in item["markers"]),
                "Placeholder dates": sum(r["count"] for r in item["placeholder_dates"]),
                "Large integer strings": item["large_integer_strings"],
                "Leading zeros": item["leading_zero_strings"],
                "Parse failures": field.parse_failures,
            }
        )
    return rows
