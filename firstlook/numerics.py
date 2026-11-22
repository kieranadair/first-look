"""Source-based distribution summaries, independent of display compression."""

import numpy as np


def compressed_ecdf(values, cap: int = 1200):
    values = np.sort(np.asarray(values, dtype=float))
    if not len(values) or not np.isfinite(values).all() or cap < 3:
        raise ValueError("An ECDF needs finite values and at least three display locations.")
    unique, counts = np.unique(values, return_counts=True)
    cumulative = counts.cumsum() / len(values)
    if len(unique) <= cap:
        positions = np.arange(len(unique))
    else:
        # Probability ranks retain large tied jumps. All vertices are observed values.
        positions = np.unique(
            np.r_[0, np.searchsorted(cumulative, np.linspace(0, 1, cap - 2)), len(unique) - 1]
        )
    x, p = unique[positions], cumulative[positions]
    previous = np.searchsorted(x, unique, side="right") - 1
    approximate = np.where(previous >= 0, p[np.maximum(previous, 0)], 0)
    error = float(np.max(np.abs(cumulative - approximate)))
    return x, p, error, len(unique)


def cdf_distance(a, b) -> float:
    a, b = np.sort(np.asarray(a, dtype=float)), np.sort(np.asarray(b, dtype=float))
    if not len(a) or not len(b):
        raise ValueError("Both groups need recorded finite values.")
    thresholds = np.union1d(a, b)
    return float(
        np.max(
            np.abs(
                np.searchsorted(a, thresholds, side="right") / len(a)
                - np.searchsorted(b, thresholds, side="right") / len(b)
            )
        )
    )


def threshold_probability(values, threshold):
    source = np.asarray(values, dtype=float)
    source = source[np.isfinite(source)]
    if not len(source) or not np.isfinite(threshold):
        raise ValueError("An exact threshold query needs a finite threshold and recorded values.")
    count = int(np.count_nonzero(source <= threshold))
    return {"at_or_below": count, "nonmissing": len(source), "proportion": count / len(source)}
