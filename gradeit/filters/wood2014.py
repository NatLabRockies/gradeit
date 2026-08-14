"""The Wood et al. (2014) elevation filtration routine.

Implements the five-step routine tabulated as Table 1 of Wood, Burton, Duran &
Gonder, *Appending High-Resolution Elevation Data to GPS Speed Traces for
Vehicle Energy Modeling and Simulation*, NREL/TP-5400-61109 (2014):

* **A.** Raw elevation versus distance.
* **B.** Elevation is downsampled onto uniformly spaced distance intervals,
  each node carrying the **median** of the raw points that fall in it.
* **C.** The downsampled profile is passed through a combined Savitzky-Golay
  and binomial filter, and the difference between the pre-filtered and
  post-filtered values is computed.
* **D.** Nodes whose filtration difference exceeds a threshold are discarded
  and backfilled via interpolation.
* **E.** The backfilled profile is passed through the same combined filter
  again, then elevation at the original distance values is recovered by
  interpolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.exceptions import InvalidInputError
from gradeit.filters._util import consecutive_runs, cumulative_distance_ft
from gradeit.filters.elevation_filter import ElevationFilter
from gradeit.filters.savitzky_golay import savgol_filter


def binomial_kernel(order: int) -> np.ndarray:
    """The normalized binomial (Pascal's triangle) kernel of a given order.

    Coefficients are ``C(order, k) / 2**order`` for ``k = 0..order``, giving a
    kernel of length ``order + 1`` that sums to 1. It is the discrete analogue
    of a Gaussian with ``sigma = sqrt(order) / 2`` samples, and its frequency
    response ``cos(w/2)**order`` is monotone -- no sidelobes, no ringing.

    ``order`` is forced even so the kernel has odd length and is therefore
    zero-phase; an odd order would shift the profile by half a sample, which on
    a distance grid is a systematic position error. The minimum is 2.

    Built by repeated convolution with ``[0.5, 0.5]``. Every coefficient is a
    dyadic rational, so the result is exact in float64.
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

    Edges are handled by **odd** reflection (``2*x[0] - x[k]``), which
    reproduces the local slope exactly and therefore leaves a constant-grade
    road untouched end to end. Even reflection would mirror the slope at the
    boundary and bias the terminal elevation; replicate padding would flatten
    it. On a straight ramp this implementation is exact to float64 precision.
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

    Returns a window of ``0`` when the node grid is too short to smooth, which
    :func:`_combined_filter` treats as "skip this stage". The window is always
    odd; ``polyorder`` is lowered if the window cannot accommodate it.
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

    The binomial's single integer order sets both its length and its shape,
    with ``sigma = sqrt(order) / 2`` samples. Parameterizing by sigma rather
    than by span keeps the physical bandwidth invariant when ``delta_ft``
    changes: ``order = (2 * sigma / delta)**2``. The order is quantized and
    floored at 2, so the narrowest achievable sigma is ``delta / sqrt(2)``.

    Returns ``0`` when the node grid is too short, meaning "skip this stage".
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

    An artifact wider than one node makes the smoothed curve pass *through* its
    own shoulders, so the residual there dips back to ~0 and the run breaks into
    fragments with clean-looking nodes between them. Backfilling only the
    fragments then interpolates from those shoulders and leaves most of the
    artifact in place. Within one kernel support a near-zero residual is
    evidence of the smoother tracking the artifact, not of clean data, so
    fragments that close together belong to the same object.
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

    A gap that long carries no elevation information -- most often because the
    DEM returned no-data, or because the trace left the downloaded tiles. The
    routine must not fabricate a profile across it, and must not let values on
    one side leak through the smoother into the other.
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
    """Elevation filtration per Wood et al. (2014), NREL/TP-5400-61109.

    Resamples the elevation profile onto a uniform distance grid (median per
    node), smooths it with a combined Savitzky-Golay and binomial filter,
    discards and backfills nodes whose filtration residual is too large to be
    DEM noise, smooths again, and interpolates back onto the original points.

    Parameters
    ----------
    interval_ft:
        Target spacing of the uniform distance grid (step B). Default 100 ft,
        roughly 3x the ~33 ft post spacing of the USGS 1/3 arc-second DEM: below
        one post, adjacent nodes read the same cell and the downsample removes
        no noise. The realized spacing is ``total_distance / round(total /
        interval_ft)``, so the grid lands exactly on both ends of the trace.
    savgol_window_ft, savgol_polyorder:
        Width and polynomial order of the Savitzky-Golay stage, declared in feet
        so the physical cutoff does not move when ``interval_ft`` changes. At
        the defaults this resolves to a 7-sample window, whose composite kernel
        attenuates white DEM noise by 57%.
    binomial_sigma_ft:
        Width of the binomial stage, as a Gaussian-equivalent sigma in feet. A
        sigma rather than a span, because the binomial's order sets both its
        length and its shape; see :func:`_resolve_binomial`. A vertical curve is
        biased by ``sigma**2 * curvature / 2``, which at the default is about
        0.5 ft on a 60 mph crest -- a sixteenth of the DEM's own 8 ft RMSE.
    residual_threshold_ft:
        Step D discard threshold on ``|pre - post|``. Default 8 ft, which is the
        DEM's stated 2.44 m vertical RMSE: a filtration residual larger than the
        elevation model's own 1-sigma accuracy is not explainable as DEM noise.
        Note this is a *residual*, not a raw drop -- the smoother is itself
        dragged toward an artifact, so a ~55 ft bridge drop leaves a residual
        near 11 ft. Setting this to the "tens of feet" the paper attributes to
        the raw artifact would catch nothing.
    residual_grow_ratio:
        Hysteresis. A run of nodes above ``residual_threshold_ft *
        residual_grow_ratio`` is discarded whole as long as at least one node in
        it breaches the full threshold. Without this, a wide artifact drags the
        smoothed curve down with it, the residual shrinks in the middle, and a
        per-node test punches out the flanks while leaving the floor. Runs that
        end up within one kernel support of each other are then merged for the
        same reason (see :func:`_merge_runs`). Set to 1.0 to disable the
        hysteresis itself.
    max_discard_len_ft:
        Reject discard runs longer than this -- a residual sustained over that
        distance is real topography, not an artifact.
    max_discard_fraction:
        Safety valve, in two parts: the threshold is raised if it would
        otherwise fire too often, and the surviving runs are then accepted
        strongest-anomaly-first until this fraction of measured nodes is spent.
        Inert at the defaults on realistic data; it exists so unusually noisy
        input cannot silently erase a quarter of the trace.
    max_gap_ft:
        Unobserved stretches longer than this split the trace into independently
        filtered segments; original points inside such a gap are returned as
        ``NaN`` rather than interpolated across.
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
        # Degenerate cases: return the input untouched rather than fabricate.
        if n < 2 or not np.isfinite(elev).any():
            return elev.tolist()

        s = cumulative_distance_ft(coordinates)
        total = float(s[-1])
        if not np.isfinite(total) or total < self.interval_ft:
            # Every point at one location, or a trace shorter than one bin.
            return elev.tolist()

        x, delta, node_s, node_elev, observed = self._downsample(elev, s, total)
        segments = _supported_segments(observed, x, self.max_gap_ft)
        if not segments:
            return elev.tolist()

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

        Returns ``(x, delta, node_s, node_elev, observed)``. ``x`` is the node
        grid; ``node_elev`` is the median elevation of each node's members and
        ``node_s`` the median of their *distances*.

        Carrying the member distances matters more than it looks. Placing a
        node's median elevation at the node's nominal position injects an error
        of up to ``delta/2 * grade``, because the members' distance centroid is
        not the node centre. That beat between GPS spacing and grid spacing is
        not white, so the smoother does not remove it -- it survives to the
        output at up to ~2 ft on an 8% grade. Anchoring the median elevation to
        the median distance and then resampling makes a constant-grade road
        exact instead.
        """
        n_bins = max(1, int(round(total / self.interval_ft)))
        x = np.linspace(0.0, total, n_bins + 1)
        delta = float(x[1] - x[0])

        # Node k owns the ball of radius delta/2 around x[k]; the grid lands on
        # 0 and `total` exactly, so step E never has to extrapolate.
        node = np.clip(np.rint(s / delta), 0, n_bins).astype(np.int64)
        n_nodes = n_bins + 1

        valid = np.isfinite(elev)
        counts = np.bincount(node[valid], minlength=n_nodes)
        totals = np.bincount(node, minlength=n_nodes)
        starts = np.concatenate(([0], np.cumsum(totals)[:-1]))
        observed = counts > 0

        # Sort by (node, value) with invalid members pushed to the tail of each
        # group, so the first `counts[k]` entries of group k are its valid ones.
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
        # Two nodes can share a median distance when all their members sit on a
        # bin boundary; np.interp needs a strictly increasing source axis.
        keep = np.concatenate(([True], np.diff(xp) > 0))
        return _interp_linear_ends(x, xp[keep], fp[keep])

    # -- Steps C, D, E --------------------------------------------------------

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

        # Step C: filter, then take the pre/post difference.
        post = _combined_filter(pre, window, polyorder, order)
        residual = pre - post

        # Step D: discard the outliers and backfill them by interpolation.
        half_support = ((max(window, 1) - 1) // 2 + order // 2) * delta
        discard = self._discard_mask(residual, observed, x, half_support)
        backfilled = pre.copy()
        keep = ~discard
        if discard.any() and keep.any():
            backfilled[discard] = np.interp(x[discard], x[keep], pre[keep])

        # Step E: filter the backfilled profile again.
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
            # Raise the threshold only if it would otherwise fire too often.
            # The ceiling is applied to the *grow* threshold, because that is
            # what governs how far a run extends.
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
                # No clean anchor on one side; interpolation would clamp flat
                # and silently zero the grade at the trace boundary.
                continue
            if float(x[stop] - x[start]) > self.max_discard_len_ft:
                continue  # sustained over this distance, it is terrain
            candidates.append((start, stop, float(magnitude[start : stop + 1].max())))

        budget = n
        if capped:
            budget = int(self.max_discard_fraction * int(testable.sum()))
        # Strongest anomaly first, so a tight budget keeps the worst offenders.
        candidates.sort(key=lambda run: -run[2])
        used = 0
        for start, stop, _ in candidates:
            width = stop - start + 1
            if used + width > budget:
                continue
            discard[start : stop + 1] = True
            used += width
        return discard


# Kept for callers that want to know what a given trace resolves to without
# running the filter (used in tests and in scripts/reproduce_figure4.py).
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
