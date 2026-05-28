"""Bridge correction as an :class:`ElevationFilter`.

The USGS DEM is a *bare-earth* model: bridges and overpasses are not present,
so where a road spans a valley or river the DEM dips to the terrain below and
back up. This filter detects those dips directly from elevation by comparing
each point to a two-sided rolling-max baseline of the surrounding road, then
linearly interpolates elevation across each accepted dip span so the corrected
profile carries the road's real slope across the bridge.

Output is a corrected *elevation* profile (not grade). ``gradeit()`` recomputes
grade from the final filtered elevation, so elevation and grade stay
internally consistent.

Recommended ordering: apply :class:`BridgeFilter` *before*
:class:`~gradeit.filters.savitzky_golay.SavitzkyGolayFilter`. Smoothing first
attenuates the dip magnitude this filter keys on; bridge-correct first, then
smooth the cleaned profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.filters.elevation_filter import ElevationFilter
from gradeit.grade import get_distances

_FT_PER_MILE = 5280.0


@dataclass(frozen=True)
class BridgeFilter(ElevationFilter):
    """Interpolate elevation across bare-earth-DEM bridge artifacts.

    The detector compares each point's elevation against a baseline built from
    the rolling maximum of elevation in a window on *both* sides of the point.
    Taking the minimum of the two side-maxima makes the baseline collapse to
    the point's own elevation on monotone climbs or descents, so steady
    grade does not trigger false positives — only a real dip (a span whose
    elevation sits below the road on both sides) does.

    Parameters
    ----------
    baseline_radius_ft:
        Half-width, in feet, of the rolling-max window on each side. Defaults
        to 1 mile. Should be at least as wide as the longest bridge expected
        in the trace so each side's window samples real road.
    min_dip_depth_ft:
        Per-point threshold for inclusion in a candidate dip run. Points where
        ``baseline - elevation`` is at most this value are not dip candidates.
    min_peak_depth_ft:
        A candidate run is only accepted if at least one of its points reaches
        this depth. Filters out wide but shallow DEM noise.
    min_bridge_len_ft, max_bridge_len_ft:
        Length bounds, in feet, for accepted runs. Shorter runs are usually
        noise; longer runs are usually real terrain (valleys, canyons) the
        filter cannot honestly distinguish from artifacts.
    max_aspect_ratio:
        Reject runs whose ``length / peak_depth`` exceeds this. A real bridge
        artifact is short relative to its depth; a real valley is long
        relative to its depth.
    grade_plausibility_tol:
        After interpolating across a candidate run, compare the recovered
        grade across the span against the median segment grade in the
        ``baseline_radius_ft`` neighborhood outside the run. Reject the
        correction if they differ by more than this. Guards against
        interpolating elevation in a way that contradicts the surrounding
        road's real slope.
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

        segment_distances = get_distances(coordinates)
        cumulative_ft = np.concatenate(([0.0], np.cumsum(segment_distances))).astype(np.float64)

        baseline = self._baseline(elev, cumulative_ft)
        dip_depth = baseline - elev

        candidates = np.flatnonzero(dip_depth > self.min_dip_depth_ft)
        if candidates.size == 0:
            return elev.tolist()

        out = elev.copy()
        for start, stop in self._consecutive_runs(candidates):
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

        ``baseline[i] = min(max(left half-window), max(right half-window))``.
        Each half-window is defined in cumulative-distance space and excludes
        ``i`` itself, so a single anomalous point cannot be its own baseline.
        At trace boundaries one side may be empty; we fall back to the
        non-empty side, or to ``elev[i]`` if both are empty.
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

    def _consecutive_runs(self, indices: np.ndarray) -> List[Tuple[int, int]]:
        """Group sorted indices into inclusive (start, stop) runs of consecutive values."""
        breaks = np.flatnonzero(np.diff(indices) != 1) + 1
        groups = np.split(indices, breaks)
        return [(int(g[0]), int(g[-1])) for g in groups]

    def _accept_run(
        self,
        start: int,
        stop: int,
        elev: np.ndarray,
        dip_depth: np.ndarray,
        cumulative_ft: np.ndarray,
        n: int,
    ) -> bool:
        # Boundary case: no clean anchor on one side to interpolate from.
        if start == 0 or stop == n - 1:
            return False

        length_ft = float(cumulative_ft[stop] - cumulative_ft[start])
        if length_ft < self.min_bridge_len_ft or length_ft > self.max_bridge_len_ft:
            return False

        peak_depth = float(dip_depth[start : stop + 1].max())
        if peak_depth < self.min_peak_depth_ft:
            return False
        if length_ft / peak_depth > self.max_aspect_ratio:
            return False

        # Plausibility gate: the recovered grade across the span should be
        # consistent with the surrounding road's median segment grade.
        span_ft = float(cumulative_ft[stop + 1] - cumulative_ft[start - 1])
        if span_ft <= 0:
            return False
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
