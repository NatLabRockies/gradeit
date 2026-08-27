import unittest

import numpy as np

from gradeit.filters.savitzky_golay import savgol_filter

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


if __name__ == "__main__":
    unittest.main(warnings="ignore")
