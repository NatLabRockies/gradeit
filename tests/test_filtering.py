import unittest

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.filters.savitzky_golay import savgol_filter, SavitzkyGolayFilter

try:
    from scipy.signal import savgol_filter as scipy_savgol_filter

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


class SavgolPrimitiveTest(unittest.TestCase):
    @unittest.skipUnless(HAS_SCIPY, "scipy is required to validate the savgol primitive")
    def test_matches_scipy(self):
        # Our pure-numpy filter must match scipy's default mode="interp" across a
        # range of signal lengths and window sizes, covering interior and edges.
        rng = np.random.default_rng(0)
        for length in (20, 100, 500):
            signal = rng.normal(size=length) + np.linspace(0, 10, length)
            for window in (5, 7, 17, 31):
                if window > length:
                    continue
                ours = savgol_filter(signal, window_length=window, polyorder=3)
                expected = scipy_savgol_filter(signal, window_length=window, polyorder=3)
                np.testing.assert_allclose(
                    ours, expected, rtol=1e-9, atol=1e-9, err_msg=f"length={length} window={window}"
                )

    def test_window_must_be_odd(self):
        with self.assertRaises(ValueError):
            savgol_filter(np.zeros(10), window_length=4, polyorder=3)

    def test_window_exceeds_length(self):
        with self.assertRaises(ValueError):
            savgol_filter(np.zeros(5), window_length=7, polyorder=3)

    def test_polyorder_too_large(self):
        with self.assertRaises(ValueError):
            savgol_filter(np.zeros(10), window_length=5, polyorder=5)

    def test_accepts_python_list(self):
        result = savgol_filter([1.0, 2.0, 3.0, 4.0, 5.0], window_length=3, polyorder=2)
        self.assertEqual(result.dtype, np.float64)
        self.assertEqual(result.shape, (5,))


class SavitzkyGolayFilterTest(unittest.TestCase):
    def setUp(self):
        lats = np.linspace(39.702730, 39.695368, 10)
        lons = np.linspace(-105.245678, -105.209049, 10)
        self.coordinates = [Coordinate.from_lat_lon(lat, lon) for lat, lon in zip(lats, lons)]
        self.elevation = [
            7048.15,
            7015.69,
            7157.89,
            7004.84,
            6921.27,
            6840.03,
            6696.7,
            6735.26,
            6554.42,
            6445.5,
        ]

    def test_filter_matches_primitive(self):
        # A valid odd window is used unchanged, so the strategy is just a thin
        # wrapper over savgol_filter with that window.
        efilter = SavitzkyGolayFilter(window=5, polyorder=3)
        result = efilter.filter(self.elevation, self.coordinates)

        expected = savgol_filter(self.elevation, window_length=5, polyorder=3).tolist()
        self.assertEqual(len(result), len(self.elevation))
        self.assertIsInstance(result, list)
        np.testing.assert_allclose(result, expected)

    def test_short_trace_clamps_window(self):
        # On a short trace the heuristic default (here 11) exceeds the 10-point
        # length; the resolved window is clamped to a valid odd value instead of
        # raising, and the result stays finite and the same length.
        efilter = SavitzkyGolayFilter(window=0)
        cuml_dist = [float(i) for i in range(10)]
        window = efilter._resolve_window(cuml_dist)
        self.assertEqual(window % 2, 1)
        self.assertGreater(window, efilter.polyorder)
        self.assertLessEqual(window, 10)

        result = efilter.filter(self.elevation, self.coordinates)
        self.assertEqual(len(result), len(self.elevation))
        self.assertTrue(all(np.isfinite(v) for v in result))

    def test_oversized_user_window_clamps(self):
        # A user window larger than the trace is reduced to fit rather than raising.
        efilter = SavitzkyGolayFilter(window=999)
        window = efilter._resolve_window([float(i) for i in range(10)])
        self.assertLessEqual(window, 10)
        self.assertEqual(window % 2, 1)

    def test_trace_too_short_raises(self):
        # Fewer points than the smallest valid window (polyorder + 1, made odd)
        # cannot be filtered at all.
        efilter = SavitzkyGolayFilter(window=0, polyorder=3)
        with self.assertRaises(ValueError):
            efilter._clamp_window(5, n=4)

    def test_filter_auto_window(self):
        # window=0 selects a heuristic default sized from cumulative distance.
        # Use a realistic-length trace (the heuristic targets real GPS traces);
        # the result stays finite and the same length as the input.
        n = 50
        lats = np.linspace(39.702730, 39.702730 - 0.000818 * (n - 1), n)
        lons = np.linspace(-105.245678, -105.245678 + 0.000409 * (n - 1), n)
        coordinates = [Coordinate.from_lat_lon(lat, lon) for lat, lon in zip(lats, lons)]
        elevation = (7000 + 200 * np.sin(np.linspace(0, 6, n))).tolist()

        efilter = SavitzkyGolayFilter(window=0)
        result = efilter.filter(elevation, coordinates)

        self.assertEqual(len(result), len(elevation))
        self.assertTrue(all(np.isfinite(v) for v in result))


if __name__ == "__main__":
    unittest.main(warnings="ignore")
