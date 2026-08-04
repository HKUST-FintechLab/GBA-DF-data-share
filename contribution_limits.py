"""Local deterministic contribution limits for recording/subject groups.

The current forest proof remains row-level: this helper limits how many rows a group can
contribute so a long recording cannot dominate the pooled counts.  It does *not* by itself
turn row-level DP into recording- or person-level DP; that would require recalibrating the
noise and a group-adjacency proof.
"""
import numpy as np


def validate_max_rows_per_group(value):
    """Return a positive group cap, or zero when the legacy cap is disabled."""
    try:
        cap = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("max_rows_per_group must be an integer") from error
    if not 0 <= cap <= 100_000:
        raise ValueError("max_rows_per_group must be between 0 and 100000")
    return cap


def cap_rows_by_group(X, y, groups, max_rows):
    """Uniformly retain at most ``max_rows`` rows from each local group.

    The first-seen group order and each group's evenly-spaced row positions make the result
    reproducible across operating systems. No group identifier leaves this function.
    Returns ``(X, y, groups, dropped_rows)``.
    """
    cap = validate_max_rows_per_group(max_rows)
    X = np.asarray(X)
    y = np.asarray(y)
    groups = np.asarray(groups).astype(str)
    if not (len(X) == len(y) == len(groups)):
        raise ValueError("X, y and groups must have the same number of rows")
    if cap == 0:
        return X, y, groups, 0

    keep, seen = [], set()
    for group in groups.tolist():
        if group in seen:
            continue
        seen.add(group)
        members = np.flatnonzero(groups == group)
        if len(members) <= cap:
            keep.extend(members.tolist())
        else:
            positions = np.linspace(0, len(members) - 1, num=cap, dtype=int)
            keep.extend(members[positions].tolist())
    keep = np.asarray(sorted(keep), dtype=int)
    return X[keep], y[keep], groups[keep], int(len(X) - len(keep))
