"""Area encodings require an already validated, complete additive partition."""

from __future__ import annotations

import math

from firstlook.contracts import ResultArtifact


def amount_records(result: ResultArtifact) -> list[dict]:
    """Bind original amounts without replacing saved cumulative-share evidence."""
    meta, plan = result.metadata, result.plan
    definition = meta.get("definition", {})
    if not (
        plan.operation == "exploration"
        and plan.params.get("recipe") == "concentration"
        and meta.get("partwhole_verified") is True
        and meta.get("full_original_parts") is True
        and definition.get("aggregation") in {"sum", "count_rows"}
        and definition.get("transform", "identity") == "identity"
        and result.missing == 0
    ):
        raise ValueError("Area requires a validated complete, nonnegative additive partition.")
    records = result.records
    if not records or any(r.get("other") for r in records):
        raise ValueError("Contribution overview requires original parts, not pooled Other.")
    amounts: list[float] = []
    for row in records:
        value = row.get("amount")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("Area amounts must be finite and nonnegative; signed values are not clipped.")
        amounts.append(float(value))
    total = math.fsum(amounts)
    if total <= 0 or not math.isclose(total, result.metrics.get("total", -1), rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("Original amounts must reconcile with a positive recorded population total.")
    running = 0.0
    output = []
    for row, amount in zip(records, amounts):
        running += amount
        if not (
            math.isclose(row.get("share", -1), amount / total, rel_tol=1e-9, abs_tol=1e-10)
            and math.isclose(row.get("value", -1), running / total, rel_tol=1e-9, abs_tol=1e-10)
        ):
            raise ValueError("Part shares and cumulative shares must use the same recorded total.")
        output.append({**row, "cumulative_share": row["value"], "value": amount})
    return output


def labelled_part_capacity(height: int) -> int:
    """Declared display budget, not a universal category-count research threshold."""
    return max(5, (height - 100) // 24)


def treemap_rectangles(values: list[float]) -> list[tuple[float, float, float, float]]:
    """Deterministic area-preserving binary layout for the offscreen overview.

    Native ECharts uses its own rectangle placement. Both encode the same exact
    areas; placement has no quantitative meaning and is not a spatial analysis.
    Zero parts retain an empty rectangle rather than an invented minimum area.
    """
    if not values or any(not math.isfinite(v) or v < 0 for v in values) or math.fsum(values) <= 0:
        raise ValueError("A treemap needs finite nonnegative parts and a positive total.")
    output = [(0.0, 0.0, 0.0, 0.0)] * len(values)
    indices = sorted((i for i, v in enumerate(values) if v > 0), key=lambda i: (-values[i], i))

    def split(ids, x, y, width, height):
        if len(ids) == 1:
            output[ids[0]] = (x, y, width, height)
            return
        total = math.fsum(values[i] for i in ids)
        before = 0.0
        cut = 1
        best = float("inf")
        for k in range(1, len(ids)):
            before += values[ids[k - 1]]
            distance = abs(before - total / 2)
            if distance < best:
                best, cut = distance, k
        ratio = math.fsum(values[i] for i in ids[:cut]) / total
        if width >= height:
            split(ids[:cut], x, y, width * ratio, height)
            split(ids[cut:], x + width * ratio, y, width * (1 - ratio), height)
        else:
            split(ids[:cut], x, y, width, height * ratio)
            split(ids[cut:], x, y + height * ratio, width, height * (1 - ratio))

    split(indices, 0.0, 0.0, 1.0, 1.0)
    return output
