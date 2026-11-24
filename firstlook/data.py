"""Bounded ingestion and recorded facts, without inferred business permissions."""

from __future__ import annotations

import csv
import hashlib
import io
import re

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firstlook.types import Dataset, Field, Request, clean

MAX_BYTES, MAX_ROWS, MAX_FIELDS = 25 * 1024**2, 50_000, 80


def load_table(raw, name, delimiter=",", encoding="utf-8-sig", missing_tokens=None) -> Dataset:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError("Choose a nonempty CSV or Parquet file up to 25 MiB.")
    tokens = list(dict.fromkeys([""] + list(missing_tokens or [])))
    if len(delimiter) != 1 or len(tokens) > 40 or any(not isinstance(t, str) or len(t) > 100 for t in tokens):
        raise ValueError("Choose a one-character delimiter and a short list of literal missing markers.")
    try:
        if raw.startswith(b"PAR1"):
            metadata = pq.ParquetFile(io.BytesIO(raw)).metadata
            if metadata.num_rows > MAX_ROWS or metadata.num_columns > MAX_FIELDS:
                raise ValueError("Choose a table with 1–50,000 rows and 1–80 fields.")
            if (
                sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups))
                > 80 * 1024**2
            ):
                raise ValueError("The expanded Parquet data exceeds the 80 MiB working budget.")
            frame = pd.read_parquet(io.BytesIO(raw))
            names = [str(c) for c in frame.columns]
        else:
            text = raw.decode(encoding)
            names = next(csv.reader(io.StringIO(text), delimiter=delimiter))
            frame = pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
                skip_blank_lines=False,
                nrows=MAX_ROWS + 1,
            )
            if len(names) != len(frame.columns):
                raise ValueError("The header and data have different field counts. Check the delimiter.")
    except (
        UnicodeError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        StopIteration,
        pa.ArrowException,
        OSError,
    ) as exc:
        raise ValueError("I couldn't read this table. Check its delimiter and encoding.") from exc
    if not 0 < len(frame) <= MAX_ROWS or not 0 < len(frame.columns) <= MAX_FIELDS:
        raise ValueError("Choose a table with 1–50,000 rows and 1–80 fields.")
    if frame.memory_usage(deep=True).sum() > 80 * 1024**2:
        raise ValueError("The decoded table exceeds the 80 MiB working budget.")
    frame = frame.reset_index(drop=True)
    frame.columns = [f"f{i:03}" for i in range(len(frame.columns))]
    fields = []
    for fid, label in zip(frame.columns, names):
        s = frame[fid]
        warnings = []
        identifier = bool(re.search(r"(^id$|[ _]id$|identifier|[ _]code$|^index$)", label, re.I))
        if s.dropna().map(lambda v: isinstance(v, (list, dict, tuple, bytes))).any():
            raise ValueError("Nested fields are not supported. Export a flat table first.")
        if pd.api.types.is_integer_dtype(s) and any(abs(int(v)) > 2**53 - 1 for v in s.dropna()):
            s = s.map(lambda v: str(int(v)) if pd.notna(v) else None)
            identifier = True
            warnings.append("Exact large-integer precision is preserved as identifier text.")
        if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            s = s.mask(s.isin(tokens))
            strings = s.dropna().astype(str)
            leading = bool(strings.str.match(r"^[+-]?0\d+$").any())
            integers = strings.str.match(r"^[+-]?\d+$")
            unsafe = any(abs(int(v)) > 2**53 - 1 for v in strings[integers])
            if leading or unsafe:
                identifier = True
                warnings.append("Exact identifier spelling/precision is preserved.")
            numeric = pd.to_numeric(s, errors="coerce")
            if len(strings) and not identifier and numeric.notna().sum() == len(strings):
                s = numeric
            elif not identifier and len(strings) and re.search(r"date|time|timestamp", label, re.I):
                try:
                    dates = pd.to_datetime(s, errors="coerce", format="mixed")
                    if pd.api.types.is_datetime64_any_dtype(dates) and dates.notna().sum() == len(strings):
                        s = dates
                    else:
                        warnings.append("Dates were not consistently parseable; original text is preserved.")
                except (ValueError, TypeError):
                    warnings.append(
                        "Dates use incompatible formats or timezones; original text is preserved."
                    )
            elif 0 < numeric.notna().sum() < len(strings):
                warnings.append(
                    "Mixed numeric/text values are preserved; review the source before arithmetic."
                )
        if pd.api.types.is_numeric_dtype(s):
            invalid = s.notna() & ~np.isfinite(s.astype(float))
            if invalid.any():
                s = s.mask(invalid)
                warnings.append(
                    f"{int(invalid.sum())} nonfinite numbers are excluded from numerical analysis."
                )
        if identifier:
            kind = "identifier"
        elif pd.api.types.is_datetime64_any_dtype(s):
            kind = "time"
        elif pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            kind = "number"
        elif s.nunique() <= 50 or s.nunique() / len(s) < 0.2:
            kind = "category"
        else:
            kind = "text"
        unit = re.search(r"(?:_|\()(mm|cm|kg|g|ms|seconds|percent)\)?$", label, re.I)
        frame[fid] = s
        fields.append(
            Field(
                fid,
                label or f"Column {len(fields) + 1}",
                kind,
                unit.group(1) if unit else "",
                int(s.isna().sum()),
                int(s.nunique()),
                s.dropna().astype(str).head(3).tolist(),
                warnings,
            )
        )
    return Dataset(
        name,
        hashlib.sha256(raw).hexdigest(),
        frame,
        fields,
        {"delimiter": delimiter, "encoding": encoding, "missing_tokens": tokens},
        raw,
    )


def profile(ds) -> dict:
    fields = {}
    for f in ds.fields:
        s = ds.frame[f.id]
        item = {
            "name": ds.label(f.id),
            "kind": f.kind,
            "missing": int(s.isna().sum()),
            "distinct": int(s.nunique()),
            "examples": f.examples,
            "warnings": f.warnings,
            "unit": f.unit,
        }
        if f.kind == "number":
            valid = s.dropna().astype(float)
            item.update(
                clean(
                    {
                        "min": valid.min(),
                        "q1": valid.quantile(0.25),
                        "median": valid.median(),
                        "mean": valid.mean(),
                        "q3": valid.quantile(0.75),
                        "max": valid.max(),
                    }
                )
            )
        elif f.kind == "time":
            item.update(clean({"min": s.min(), "max": s.max()}))
        fields[f.id] = item
    return {
        "rows": len(ds.frame),
        "fields": fields,
        "missing": int(ds.frame.isna().sum().sum()),
        "duplicates": int(ds.frame.duplicated().sum()),
    }


def starting_requests(ds) -> list[Request]:
    numbers = [f.id for f in ds.fields if f.kind == "number" and f.distinct > 1]
    categories = [f.id for f in ds.fields if f.kind == "category" and 2 <= f.distinct <= 30]
    times = [f.id for f in ds.fields if f.kind == "time"]
    requests = []
    if numbers:
        requests.append(Request("distribution", numbers[0]))
    if categories:
        requests.append(Request("categories", categories[0]))
    if times:
        requests.append(
            Request("time", times[0], numbers[0] if numbers else None, metric="mean" if numbers else "count")
        )
    elif len(numbers) >= 2:
        requests.append(Request("relationship", numbers[0], numbers[1]))
    elif categories and numbers:
        requests.append(Request("groups", numbers[0], group=categories[0]))
    return requests[:3] or [Request("missingness")]
