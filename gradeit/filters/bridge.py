"""Bridge correction as a :class:`GradeFilter`.

The USGS DEM is a *bare-earth* model: bridges and overpasses are not present, so
where a road spans a valley or river the DEM dips down to the terrain below and
back up, producing a spurious steep-down / flat / steep-up grade artifact. This
filter detects those flat spans, confirms they sit inside a real dip, and zeros
the grade across the spanned region so the road reads as level.

This is an array-based rewrite of the original ``filter_bridge.py`` (which
operated directly on a pandas DataFrame). The detection logic is preserved, with
one deliberate correctness fix noted in ``_bridge_spans``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.filters.grade_filter import GradeFilter

_FT_PER_MILE = 5280.0


@dataclass(frozen=True)
class BridgeGradeFilter(GradeFilter):
    """Zero the grade across bare-earth-DEM bridge artifacts.

    Parameters
    ----------
    extension_ft:
        How far, in feet, to extend each detected flat span on either side so
        the correction also covers the dip's sloped shoulders. Defaults to
        0.8 miles (the original default, which was expressed in miles).
    min_bridge_len_ft:
        Flat spans shorter than this (in feet) are ignored as noise rather than
        treated as bridges.
    flat_grade_threshold:
        A point is "flat" when ``|grade|`` is below this value. Consecutive flat
        points form a candidate span.
    edge_grade_threshold:
        A candidate is only treated as a real bridge if the grade somewhere in
        its extended window reaches at least this magnitude (i.e. the span sits
        in an actual dip with steep shoulders). Otherwise it is left untouched.
    """

    extension_ft: float = 0.8 * _FT_PER_MILE
    min_bridge_len_ft: float = 100.0
    flat_grade_threshold: float = 1e-4
    edge_grade_threshold: float = 0.05

    def filter(
        self,
        grade: np.ndarray,
        distances_ft: np.ndarray,
        coordinates: Optional[List[Coordinate]] = None,
        elevation_ft: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        grade = np.asarray(grade, dtype=float)
        distances_ft = np.asarray(distances_ft, dtype=float)
        cumulative_ft = np.cumsum(distances_ft)

        out = grade.copy()
        for start, stop in self._bridge_spans(grade, cumulative_ft):
            out[start : stop + 1] = 0.0
        return out

    def _bridge_spans(self, grade: np.ndarray, cumulative_ft: np.ndarray) -> List[Tuple[int, int]]:
        """Return inclusive (start, stop) index spans whose grade should be zeroed."""
        spans: List[Tuple[int, int]] = []
        for start, end in self._flat_runs(grade):
            # Ignore flat spans too short to be a real bridge deck.
            if cumulative_ft[end] - cumulative_ft[start] < self.min_bridge_len_ft:
                continue

            # Extend the span in cumulative-distance space to cover the sloped
            # shoulders of the dip. Distance is monotonic, so the points inside
            # the window form a contiguous index range.
            lo = cumulative_ft[start] - self.extension_ft
            hi = cumulative_ft[end] + self.extension_ft
            in_window = np.flatnonzero((cumulative_ft > lo) & (cumulative_ft < hi))
            if in_window.size == 0:
                continue
            ext_start, ext_stop = int(in_window[0]), int(in_window[-1])

            # Keep the span only if a steep section is present in the extended
            # window -- i.e. the flat run really sits in a dip. The original
            # ``bridge_filter_2`` wrote ``np.max(np.abs(g) < threshold)``, which
            # (by operator precedence) tested whether *any* point was below the
            # threshold and inverted the intended behavior; this uses the maximum
            # magnitude, the documented intent.
            window_abs = np.abs(grade[ext_start : ext_stop + 1])
            window_abs = window_abs[np.isfinite(window_abs)]
            if window_abs.size == 0 or window_abs.max() < self.edge_grade_threshold:
                continue

            spans.append((ext_start, ext_stop))
        return spans

    def _flat_runs(self, grade: np.ndarray) -> List[Tuple[int, int]]:
        """Maximal runs of consecutive flat points, as inclusive (start, stop) spans."""
        flat_idx = np.flatnonzero(np.abs(grade) < self.flat_grade_threshold)
        if flat_idx.size == 0:
            return []
        # Split the flat indices wherever they stop being consecutive.
        breaks = np.flatnonzero(np.diff(flat_idx) != 1) + 1
        groups = np.split(flat_idx, breaks)
        return [(int(g[0]), int(g[-1])) for g in groups]
