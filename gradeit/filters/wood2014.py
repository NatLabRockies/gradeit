"""Filter elevation with the Wood et al. (2014) method.

The filter resamples elevation onto a distance grid, smooths it, replaces large
errors, smooths again, and returns values at the original points.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.exceptions import InvalidInputError, SparseGridWarning
from gradeit.filters._util import consecutive_runs, cumulative_distance_ft
from gradeit.filters.elevation_filter import ElevationFilter
from gradeit.filters.savitzky_golay import savgol_filter


def binomial_kernel(order: int) -> np.ndarray:
    """The normalized binomial (Pascal's triangle) kernel of a given order.

    The result has an odd length, sums to 1, and has an order of at least 2.
    """
    order = max(2, int(order))
    if order % 2:
        order += 1
    coeffs = np.ones(1, dtype=np.float64)
    for _ in range(order):
        coeffs = np.convolve(coeffs, np.array([0.5, 0.5]))
    return coeffs


def binomial_filter(x: Union[Sequence[float], np.ndarray], order: int) -> np.ndarray:
    """Apply a binomial smoothing filter to a 1-D signal.

    Uses odd reflection at both ends to preserve the local slope.
    """
    arr = np.asarray(x, dtype=np.float64)
    coeffs = binomial_kernel(order)
    half = (coeffs.size - 1) // 2
    if half == 0 or arr.size < 2:
        return arr.copy()
    padded = np.pad(arr, half, mode="reflect", reflect_type="odd")
    return np.convolve(padded, coeffs, mode="valid")


def _combined_filter(x: np.ndarray, window: int, polyorder: int, order: int) -> np.ndarray:
    """The paper's "combined Savitzky-Golay and binomial filter"."""
    y = x
    if window >= 3:
        y = savgol_filter(y, window_length=window, polyorder=polyorder)
    if order >= 2:
        y = binomial_filter(y, order)
    return np.asarray(y, dtype=np.float64)


def _interp_linear_ends(x: np.ndarray, xp: np.ndarray, fp: np.ndarray) -> np.ndarray:
    """``np.interp``, but extrapolating linearly instead of clamping flat."""
    out = np.interp(x, xp, fp)
    if xp.size < 2:
        return out
    left = x < xp[0]
    if left.any():
        slope = (fp[1] - fp[0]) / (xp[1] - xp[0])
        out[left] = fp[0] + slope * (x[left] - xp[0])
    right = x > xp[-1]
    if right.any():
        slope = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
        out[right] = fp[-1] + slope * (x[right] - xp[-1])
    return out


def _resolve_savgol(
    window_ft: float, delta_ft: float, n_nodes: int, polyorder: int
) -> Tuple[int, int]:
    """Convert a Savitzky-Golay window in feet to (window_samples, polyorder).

    Returns ``0`` when the grid is too short. The window is odd and the
    polynomial order is reduced when needed.
    """
    half = max(1, int(round(window_ft / (2.0 * delta_ft))))
    window = 2 * half + 1
    largest = n_nodes if n_nodes % 2 == 1 else n_nodes - 1
    window = min(window, largest)
    if window < 3:
        return 0, polyorder
    return window, min(polyorder, window - 1)


def _resolve_binomial(sigma_ft: float, delta_ft: float, n_nodes: int) -> int:
    """Convert a binomial width in feet (as a sigma) to a kernel order.

    Returns ``0`` when the grid is too short for this filter.
    """
    order = int(round((2.0 * sigma_ft / delta_ft) ** 2))
    if order % 2:
        order += 1
    order = max(2, order)
    largest = n_nodes - 1
    if largest % 2:
        largest -= 1
    if largest < 2:
        return 0
    return min(order, largest)


def _merge_runs(runs: List[Tuple[int, int]], x: np.ndarray, gap_ft: float) -> List[Tuple[int, int]]:
    """Join runs separated by less than ``gap_ft`` of distance.

    Nearby runs can be parts of the same elevation error.
    """
    if not runs:
        return []
    merged = [runs[0]]
    for start, stop in runs[1:]:
        prev_start, prev_stop = merged[-1]
        if float(x[start] - x[prev_stop]) <= gap_ft:
            merged[-1] = (prev_start, stop)
        else:
            merged.append((start, stop))
    return merged


def _supported_segments(
    observed: np.ndarray, x: np.ndarray, max_gap_ft: float
) -> List[Tuple[int, int]]:
    """Split the node grid at unobserved gaps wider than ``max_gap_ft``.

    The filter does not interpolate or smooth across these gaps.
    """
    idx = np.flatnonzero(observed)
    if idx.size == 0:
        return []
    segments: List[Tuple[int, int]] = []
    start = int(idx[0])
    for a, b in zip(idx[:-1], idx[1:]):
        if float(x[b] - x[a]) > max_gap_ft:
            segments.append((start, int(a)))
            start = int(b)
    segments.append((start, int(idx[-1])))
    return segments


@dataclass(frozen=True)
class Wood2014Filter(ElevationFilter):
    """Elevation filtration per Wood et al. (2014), NLR/TP-5400-61109.

    Resamples elevation onto a uniform distance grid, smooths it, replaces
    large residuals, smooths again, and restores the original point spacing.

    Parameters
    ----------
    interval_ft:
        Target distance between grid nodes. Default: 100 ft. The actual grid
        includes the first and last trace points.
    savgol_window_ft, savgol_polyorder:
        Savitzky-Golay window width and polynomial order. The width is in feet.
    binomial_sigma_ft:
        Width of the binomial stage in feet.
    residual_threshold_ft:
        Replace a node when its smoothed residual exceeds this value. Default:
        8 ft.
    residual_grow_ratio:
        Include nearby nodes when their residual exceeds this fraction of the
        threshold. Set to 1.0 to disable this expansion.
    max_discard_len_ft:
        Do not replace runs longer than this distance.
    max_discard_fraction:
        Maximum fraction of measured nodes that may be replaced.
    max_gap_ft:
        Split the trace at missing-elevation gaps longer than this distance.
    min_node_occupancy:
        Warn when fewer than this fraction of grid nodes contain a GPS point.
        Set to ``0.0`` to disable the warning.
    """

    interval_ft: float = 100.0
    savgol_window_ft: float = 600.0
    savgol_polyorder: int = 3
    binomial_sigma_ft: float = 100.0
    residual_threshold_ft: float = 8.0
    residual_grow_ratio: float = 0.5
    max_discard_len_ft: float = 2000.0
    max_discard_fraction: float = 0.25
    max_gap_ft: float = 1000.0
    min_node_occupancy: float = 0.35

    def filter(
        self,
        elevation_profile: List[float],
        coordinates: List[Coordinate],
    ) -> List[float]:
        elev = np.asarray(elevation_profile, dtype=np.float64)
        n = elev.size
        if n != len(coordinates):
            raise InvalidInputError(
                f"elevation_profile has {n} values but {len(coordinates)} coordinates were given."
            )
        # No usable elevation data to filter.
        if n < 2 or not np.isfinite(elev).any():
            return elev.tolist()

        s = cumulative_distance_ft(coordinates)
        total = float(s[-1])
        if not np.isfinite(total) or total < self.interval_ft:
            # The trace is shorter than one grid interval.
            return elev.tolist()

        x, delta, node_s, node_elev, observed = self._downsample(elev, s, total)
        segments = _supported_segments(observed, x, self.max_gap_ft)
        if not segments:
            return elev.tolist()
        self._check_occupancy(observed, segments, s)

        pre = self._to_grid(x, node_s, node_elev, observed)
        final = np.full(x.size, np.nan, dtype=np.float64)
        for lo, hi in segments:
            final[lo : hi + 1] = self._filter_segment(
                pre[lo : hi + 1], x[lo : hi + 1], observed[lo : hi + 1], delta
            )

        out = np.full(n, np.nan, dtype=np.float64)
        for lo, hi in segments:
            inside = (s >= x[lo]) & (s <= x[hi])
            if inside.any():
                out[inside] = np.interp(s[inside], x[lo : hi + 1], final[lo : hi + 1])
        return out.tolist()

    # -- Step B ---------------------------------------------------------------

    def _downsample(
        self, elev: np.ndarray, s: np.ndarray, total: float
    ) -> Tuple[np.ndarray, float, np.ndarray, np.ndarray, np.ndarray]:
        """Median-downsample onto a uniform distance grid.

        Returns the grid, its spacing, median member distance, median
        elevation, and a flag for nodes with valid data.
        """
        n_bins = max(1, int(round(total / self.interval_ft)))
        x = np.linspace(0.0, total, n_bins + 1)
        delta = float(x[1] - x[0])

        # Assign each point to its closest grid node.
        node = np.clip(np.rint(s / delta), 0, n_bins).astype(np.int64)
        n_nodes = n_bins + 1

        valid = np.isfinite(elev)
        counts = np.bincount(node[valid], minlength=n_nodes)
        totals = np.bincount(node, minlength=n_nodes)
        starts = np.concatenate(([0], np.cumsum(totals)[:-1]))
        observed = counts > 0

        # Sort valid values within each grid node to find their median.
        last = elev.size - 1
        lo = np.minimum(starts + np.maximum(counts - 1, 0) // 2, last)
        hi = np.minimum(starts + counts // 2, last)

        order_e = np.lexsort((np.where(valid, elev, np.inf), node))
        node_elev = np.where(observed, 0.5 * (elev[order_e[lo]] + elev[order_e[hi]]), np.nan)

        order_s = np.lexsort((np.where(valid, s, np.inf), node))
        node_s = np.where(observed, 0.5 * (s[order_s[lo]] + s[order_s[hi]]), np.nan)

        return x, delta, node_s, node_elev, observed

    @staticmethod
    def _to_grid(
        x: np.ndarray, node_s: np.ndarray, node_elev: np.ndarray, observed: np.ndarray
    ) -> np.ndarray:
        """Resample the distance-anchored node medians onto the uniform grid."""
        xp = node_s[observed]
        fp = node_elev[observed]
        if xp.size == 0:
            return np.full(x.size, np.nan, dtype=np.float64)
        if xp.size == 1:
            return np.full(x.size, float(fp[0]), dtype=np.float64)
        # ``np.interp`` needs increasing source distances.
        keep = np.concatenate(([True], np.diff(xp) > 0))
        return _interp_linear_ends(x, xp[keep], fp[keep])

    def _check_occupancy(
        self, observed: np.ndarray, segments: List[Tuple[int, int]], s: np.ndarray
    ) -> None:
        """Warn when the node grid is finer than the GPS points can support.

        Only counts nodes in segments with elevation data.
        """
        if self.min_node_occupancy <= 0.0:
            return
        nodes = sum(hi - lo + 1 for lo, hi in segments)
        if nodes == 0:
            return
        measured = sum(int(observed[lo : hi + 1].sum()) for lo, hi in segments)
        occupancy = measured / nodes
        if occupancy >= self.min_node_occupancy:
            return

        # Ignore repeated locations when measuring point spacing.
        spacing = np.diff(s)
        moving = spacing[spacing > 0]
        advice = (
            f"the trace's median point spacing is {np.median(moving):,.0f} ft, so set "
            f"interval_ft at least that large"
            if moving.size
            else "the trace covers no distance"
        )
        warnings.warn(
            f"interval_ft={self.interval_ft:g} is finer than this trace can support: only "
            f"{occupancy:.0%} of the {nodes} grid nodes contain a GPS point, so most of the "
            f"filtered profile is interpolated rather than measured and step B's median "
            f"downsample removes no noise. To fix, {advice}. "
            f"Pass min_node_occupancy=0 to silence this warning.",
            SparseGridWarning,
            stacklevel=3,
        )

    # -- Smooth, replace errors, and smooth again --------------------------------

    def _filter_segment(
        self, pre: np.ndarray, x: np.ndarray, observed: np.ndarray, delta: float
    ) -> np.ndarray:
        n_nodes = pre.size
        if n_nodes < 3:
            return pre.copy()

        window, polyorder = _resolve_savgol(
            self.savgol_window_ft, delta, n_nodes, self.savgol_polyorder
        )
        order = _resolve_binomial(self.binomial_sigma_ft, delta, n_nodes)

        # Smooth the elevation and measure the difference.
        post = _combined_filter(pre, window, polyorder, order)
        residual = pre - post

        # Replace outliers by interpolation.
        half_support = ((max(window, 1) - 1) // 2 + order // 2) * delta
        discard = self._discard_mask(residual, observed, x, half_support)
        backfilled = pre.copy()
        keep = ~discard
        if discard.any() and keep.any():
            backfilled[discard] = np.interp(x[discard], x[keep], pre[keep])

        # Smooth the corrected profile.
        return _combined_filter(backfilled, window, polyorder, order)

    def _discard_mask(
        self,
        residual: np.ndarray,
        observed: np.ndarray,
        x: np.ndarray,
        half_support_ft: float,
    ) -> np.ndarray:
        n = residual.size
        discard = np.zeros(n, dtype=bool)
        magnitude = np.abs(residual)
        testable = observed & np.isfinite(magnitude)
        if not testable.any():
            return discard

        threshold = float(self.residual_threshold_ft)
        grow_ratio = min(max(self.residual_grow_ratio, 1e-6), 1.0)
        capped = 0.0 < self.max_discard_fraction < 1.0
        if capped:
            # Raise the threshold to keep replacements within the limit.
            ceiling = float(np.quantile(magnitude[testable], 1.0 - self.max_discard_fraction))
            threshold = max(threshold, ceiling / grow_ratio)

        seed = testable & (magnitude > threshold)
        if not seed.any():
            return discard
        grow = testable & (magnitude > threshold * grow_ratio)

        runs = _merge_runs(consecutive_runs(np.flatnonzero(grow)), x, half_support_ft)

        candidates: List[Tuple[int, int, float]] = []
        for start, stop in runs:
            if not seed[start : stop + 1].any():
                continue  # noise-only run, no node actually breached the threshold
            if start == 0 or stop == n - 1:
                # A boundary run has no clean point on both sides.
                continue
            if float(x[stop] - x[start]) > self.max_discard_len_ft:
                continue
            candidates.append((start, stop, float(magnitude[start : stop + 1].max())))

        budget = n
        if capped:
            budget = int(self.max_discard_fraction * int(testable.sum()))
        # Handle the largest errors first.
        candidates.sort(key=lambda run: -run[2])
        used = 0
        for start, stop, _ in candidates:
            width = stop - start + 1
            if used + width > budget:
                continue
            discard[start : stop + 1] = True
            used += width
        return discard


# Return the resolved filter settings without filtering a trace.
def resolve_parameters(
    f: Wood2014Filter, total_ft: float, n_nodes: Optional[int] = None
) -> Tuple[float, int, int, int]:
    """Return ``(delta_ft, savgol_window, savgol_polyorder, binomial_order)``."""
    n_bins = max(1, int(round(total_ft / f.interval_ft)))
    delta = total_ft / n_bins
    nodes = n_bins + 1 if n_nodes is None else n_nodes
    window, polyorder = _resolve_savgol(f.savgol_window_ft, delta, nodes, f.savgol_polyorder)
    order = _resolve_binomial(f.binomial_sigma_ft, delta, nodes)
    return delta, window, polyorder, order
