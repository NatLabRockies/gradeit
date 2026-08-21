"""Bridge correction as an :class:`ElevationFilter`.

USGS bare-earth elevation data may show a dip under a bridge or overpass. This
filter finds short dips and fills them with a straight elevation line. Apply it
before :class:`~gradeit.filters.Wood2014Filter`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.filters._util import consecutive_runs, cumulative_distance_ft
from gradeit.filters.elevation_filter import ElevationFilter

_FT_PER_MILE = 5280.0


@dataclass(frozen=True)
class BridgeFilter(ElevationFilter):
    """Interpolate elevation across bare-earth-DEM bridge artifacts.

    Compares each point with the highest elevation on both sides. A point that
    is much lower than both sides can be part of a bridge artifact.

    Parameters
    ----------
    baseline_radius_ft:
        Distance, in feet, checked on each side of a point. Default: 1 mile.
        Set it wider than the bridge, but narrow enough to avoid treating a
        valley as a bridge.
    min_dip_depth_ft:
        Per-point threshold for inclusion in a candidate dip run. Points where
        ``baseline - elevation`` is at most this value are not dip candidates.
    min_peak_depth_ft:
        A run needs at least one point this deep to be accepted.
    min_bridge_len_ft, max_bridge_len_ft:
        Minimum and maximum length in feet for an accepted run. Length includes
        the clean point on each side used for interpolation.
    max_aspect_ratio:
        Reject runs whose length divided by peak depth is too large.
    grade_plausibility_tol:
        Reject a correction when its grade differs too much from nearby road
        grade.
    """

    baseline_radius_ft: float = _FT_PER_MILE
    min_dip_depth_ft: float = 5.0
    min_peak_depth_ft: float = 10.0
    min_bridge_len_ft: float = 50.0
    max_bridge_len_ft: float = 1.5 * _FT_PER_MILE
    max_aspect_ratio: float = 50.0
    grade_plausibility_tol: float = 0.05

    def filter(
        self,
        elevation_profile: List[float],
        coordinates: List[Coordinate],
    ) -> List[float]:
        elev = np.asarray(elevation_profile, dtype=np.float64)
        n = elev.size
        if n < 3:
            return elev.tolist()

        cumulative_ft = cumulative_distance_ft(coordinates)

        baseline = self._baseline(elev, cumulative_ft)
        dip_depth = baseline - elev

        candidates = np.flatnonzero(dip_depth > self.min_dip_depth_ft)
        if candidates.size == 0:
            return elev.tolist()

        out = elev.copy()
        for start, stop in consecutive_runs(candidates):
            if not self._accept_run(start, stop, elev, dip_depth, cumulative_ft, n):
                continue
            out[start : stop + 1] = np.interp(
                cumulative_ft[start : stop + 1],
                [cumulative_ft[start - 1], cumulative_ft[stop + 1]],
                [elev[start - 1], elev[stop + 1]],
            )
        return out.tolist()

    def _baseline(self, elev: np.ndarray, cumulative_ft: np.ndarray) -> np.ndarray:
        """Two-sided rolling-max baseline at each index.

        Uses the lower of the highest values in the left and right windows.
        """
        n = elev.size
        radius = self.baseline_radius_ft
        lo = np.searchsorted(cumulative_ft, cumulative_ft - radius, side="left")
        hi = np.searchsorted(cumulative_ft, cumulative_ft + radius, side="right")

        baseline = np.empty(n, dtype=np.float64)
        for i in range(n):
            left = elev[lo[i] : i]
            right = elev[i + 1 : hi[i]]
            left_max = left.max() if left.size else -np.inf
            right_max = right.max() if right.size else -np.inf
            if np.isneginf(left_max) and np.isneginf(right_max):
                baseline[i] = elev[i]
            elif np.isneginf(left_max):
                baseline[i] = right_max
            elif np.isneginf(right_max):
                baseline[i] = left_max
            else:
                baseline[i] = min(left_max, right_max)
        return baseline

    def _accept_run(
        self,
        start: int,
        stop: int,
        elev: np.ndarray,
        dip_depth: np.ndarray,
        cumulative_ft: np.ndarray,
        n: int,
    ) -> bool:
        # A boundary run has no anchor on one side.
        if start == 0 or stop == n - 1:
            return False

        # Include both interpolation anchors in the run length.
        span_ft = float(cumulative_ft[stop + 1] - cumulative_ft[start - 1])
        if span_ft <= 0:
            return False
        if span_ft < self.min_bridge_len_ft or span_ft > self.max_bridge_len_ft:
            return False

        peak_depth = float(dip_depth[start : stop + 1].max())
        if peak_depth < self.min_peak_depth_ft:
            return False
        if span_ft / peak_depth > self.max_aspect_ratio:
            return False

        # Compare the corrected grade with nearby road grade.
        recovered_grade = (elev[stop + 1] - elev[start - 1]) / span_ft

        surrounding = self._surrounding_median_grade(start, stop, elev, cumulative_ft)
        if (
            surrounding is not None
            and abs(recovered_grade - surrounding) > self.grade_plausibility_tol
        ):
            return False
        return True

    def _surrounding_median_grade(
        self,
        start: int,
        stop: int,
        elev: np.ndarray,
        cumulative_ft: np.ndarray,
    ) -> Optional[float]:
        """Median segment grade in the ``baseline_radius_ft`` windows outside the run."""
        radius = self.baseline_radius_ft
        left_lo = int(np.searchsorted(cumulative_ft, cumulative_ft[start] - radius, side="left"))
        right_hi = int(np.searchsorted(cumulative_ft, cumulative_ft[stop] + radius, side="right"))

        seg_grades: List[float] = []
        if start - left_lo >= 2:
            seg_grades.extend(
                self._segment_grades(elev[left_lo:start], cumulative_ft[left_lo:start])
            )
        if right_hi - (stop + 1) >= 2:
            seg_grades.extend(
                self._segment_grades(elev[stop + 1 : right_hi], cumulative_ft[stop + 1 : right_hi])
            )
        if not seg_grades:
            return None
        return float(np.median(seg_grades))

    @staticmethod
    def _segment_grades(elev: np.ndarray, cumulative_ft: np.ndarray) -> List[float]:
        d_elev = np.diff(elev)
        d_dist = np.diff(cumulative_ft)
        usable = d_dist > 0
        if not usable.any():
            return []
        return (d_elev[usable] / d_dist[usable]).tolist()
