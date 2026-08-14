"""Small helpers shared by the elevation filters."""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.grade import get_distances


def cumulative_distance_ft(coordinates: Sequence[Coordinate]) -> np.ndarray:
    """Cumulative along-trace distance in feet, one value per coordinate.

    The first element is always ``0.0``, so the array aligns point-for-point
    with an elevation profile. Segment distances are non-negative, so the
    result is monotone non-decreasing -- but it is not strictly increasing:
    ``haversine`` rounds to 1 cm, so near-coincident points (a stationary
    vehicle) produce runs of identical values.
    """
    return np.concatenate(([0.0], np.cumsum(get_distances(list(coordinates))))).astype(np.float64)


def consecutive_runs(indices: np.ndarray) -> List[Tuple[int, int]]:
    """Group sorted indices into inclusive ``(start, stop)`` runs of consecutive values."""
    if indices.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(indices) != 1) + 1
    groups = np.split(indices, breaks)
    return [(int(g[0]), int(g[-1])) for g in groups]
