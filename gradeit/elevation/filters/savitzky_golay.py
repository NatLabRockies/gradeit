from typing import List

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.elevation.filters._savgol import savgol_filter
from gradeit.elevation.filters.elevation_filter import ElevationFilter
from gradeit.grade import get_distances


class SavitzkyGolayFilter(ElevationFilter):
    """
    A Savitzky-Golay smoothing filter for elevation profiles.

    The filter is applied in the temporal domain (over the ordered sequence of
    points) rather than the spatial domain; filtering spatially would require
    error-prone resampling of the elevation signal to a uniform point spacing.

    Parameters
    ----------
    window:
        The Savitzky-Golay filter window size. Must be odd; an even value is
        bumped up by one. A value of ``0`` selects a default window sized from
        the trace's cumulative distance (see ``_resolve_window``). Out-of-range
        values fall back to that default. The resolved window is always clamped
        to an odd value in ``(polyorder, len(trace)]``.
    polyorder:
        The order of the polynomial fit within each window, by default ``3``.
    """

    def __init__(self, window: int = 17, polyorder: int = 3):
        self.window = window
        self.polyorder = polyorder

    def filter(self, elevation_profile: List[float], coordinates: List[Coordinate]) -> List[float]:
        distances = get_distances(coordinates)
        cuml_dist = list(np.append(0, np.cumsum(distances)))

        window = self._resolve_window(cuml_dist)
        smoothed = savgol_filter(elevation_profile, window_length=window, polyorder=self.polyorder)

        return smoothed.tolist()

    def _resolve_window(self, cuml_dist: List[float]) -> int:
        # Compute the default window from the trace's cumulative distance.
        avg_spd = cuml_dist[-1] / len(cuml_dist)  # vehicle avg speed in ft/s
        filter_width = 2500  # in [ft], width of the spike to be filtered (tentative)
        filter_factor = 5
        df_filter = round(
            filter_width / avg_spd * filter_factor
        )  # (estimated formula; tune filter_width/filter_factor for the desired effect)
        if df_filter < self.polyorder:
            df_filter = self.polyorder + 2
        elif df_filter > len(cuml_dist):
            df_filter = int(round(len(cuml_dist) * 0.75))  # safeguard against crossing array size
        sg_default = df_filter
        if sg_default % 2 == 0:
            sg_default += 1  # if even, transform to odd

        # window == 0 requests the default value (see examples/basic.py)
        if self.window == 0:
            window = sg_default
        else:
            # validate the user-defined window; fall back to the default if invalid
            window = self.window
            if window % 2 == 0:
                window += 1
            if (window > len(cuml_dist)) or (window < 3):
                window = sg_default

        # Final guarantee: the window must be odd, exceed the polynomial order, and
        # fit within the trace. The heuristic above can violate these bounds on
        # short traces (e.g. the even->odd bump pushing it past the array length).
        return self._clamp_window(window, len(cuml_dist))

    def _clamp_window(self, window: int, n: int) -> int:
        """Coerce ``window`` into the nearest odd value in ``(polyorder, n]``.

        Raises ValueError if the trace is too short to admit any such window.
        """
        smallest = self.polyorder + 1  # smallest odd window strictly above polyorder
        if smallest % 2 == 0:
            smallest += 1
        largest = n if n % 2 == 1 else n - 1  # largest odd window that fits the trace
        if largest < smallest:
            raise ValueError(
                f"trace of length {n} is too short for a Savitzky-Golay filter of "
                f"polyorder {self.polyorder} (need at least {smallest} points)"
            )
        if window % 2 == 0:
            window += 1
        return min(max(window, smallest), largest)
