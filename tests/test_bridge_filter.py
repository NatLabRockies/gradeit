import unittest
from typing import List

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.filters import BridgeFilter, ElevationFilter, SavitzkyGolayFilter


def _make_coords(n: int, ft_step: float = 50.0) -> List[Coordinate]:
    """n coordinates spaced approximately ft_step apart along a meridian."""
    deg_per_ft = 1.0 / 364800.0  # ~ft per degree of latitude at 40 deg
    return [Coordinate.from_lat_lon(40.0 + i * ft_step * deg_per_ft, -105.0) for i in range(n)]


class BridgeFilterDetectionTest(unittest.TestCase):
    def test_is_an_elevation_filter(self):
        self.assertIsInstance(BridgeFilter(), ElevationFilter)

    def test_interpolates_textbook_bridge_dip(self):
        # Flat road with a clear DEM dip (steep shoulders + valley floor).
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[90] = 985.0
        elev[91:100] = 970.0
        elev[100] = 985.0

        f = BridgeFilter(baseline_radius_ft=2000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))

        np.testing.assert_allclose(out[90:101], 1000.0, atol=1.0)
        np.testing.assert_array_equal(out[:80], elev[:80])
        np.testing.assert_array_equal(out[120:], elev[120:])

    def test_short_dip_below_min_length_is_ignored(self):
        # A single-point dip has zero length and is rejected before peak-depth checks.
        n = 100
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[50] = 970.0

        f = BridgeFilter(baseline_radius_ft=1000.0, min_bridge_len_ft=200.0)
        out = np.asarray(f.filter(elev.tolist(), coords))
        np.testing.assert_array_equal(out, elev)

    def test_shallow_dip_below_peak_threshold_is_ignored(self):
        # A wide dip that never reaches the min_peak_depth_ft floor is left alone.
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[80:120] = 994.0  # 6 ft deep, below default 10 ft peak threshold

        f = BridgeFilter(baseline_radius_ft=2000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))
        np.testing.assert_array_equal(out, elev)

    def test_flat_road_is_not_modified(self):
        n = 100
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)

        f = BridgeFilter(baseline_radius_ft=1000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))
        np.testing.assert_array_equal(out, elev)

    def test_climbing_road_with_embedded_bridge(self):
        # A road climbing at 5% with a short DEM dip embedded in the middle.
        # The two-sided baseline must collapse on the monotone climb away from
        # the dip and must still catch the dip itself.
        n = 200
        ft_step = 50.0
        coords = _make_coords(n, ft_step=ft_step)
        synth_cumft = np.arange(n) * ft_step
        climbline = 1000.0 + 0.05 * synth_cumft
        elev = climbline.copy()
        elev[98:103] -= 30.0  # 5-point, ~250 ft bridge

        f = BridgeFilter(baseline_radius_ft=2000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))

        # Climb untouched outside the bridge region.
        np.testing.assert_allclose(out[:80], elev[:80])
        np.testing.assert_allclose(out[120:], elev[120:])
        # Bridge restored close to the climb line (haversine vs synth grid differs
        # by <1% so allow a small tolerance).
        np.testing.assert_allclose(out[98:103], climbline[98:103], atol=2.0)

    def test_two_adjacent_bridges_both_corrected(self):
        # Two separate dips beyond each other's baseline windows are handled
        # independently and don't contaminate the road between them.
        n = 400
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[80:91] = 975.0
        elev[200:211] = 975.0

        f = BridgeFilter(baseline_radius_ft=2000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))

        np.testing.assert_allclose(out[80:91], 1000.0, atol=1.0)
        np.testing.assert_allclose(out[200:211], 1000.0, atol=1.0)
        np.testing.assert_array_equal(out[120:180], elev[120:180])

    def test_asymmetric_dip_interpolates_between_anchors(self):
        # The two clean anchors on either side of the dip sit at different
        # elevations. Interpolation must use them, producing a sloped fill
        # rather than a horizontal one.
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[100:111] = 970.0
        elev[111:] = 1010.0  # right anchor 10 ft above left anchor

        f = BridgeFilter(baseline_radius_ft=2000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))

        # The dip is filled with a monotonically increasing ramp between the
        # two anchor elevations (~1000 and ~1010).
        filled = out[100:111]
        self.assertTrue(np.all(filled >= 999.0))
        self.assertTrue(np.all(filled <= 1011.0))
        self.assertTrue(np.all(np.diff(filled) >= 0))

    def test_dip_at_trace_start_is_not_corrected(self):
        n = 100
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[0:11] = 970.0

        out = np.asarray(BridgeFilter(baseline_radius_ft=1500.0).filter(elev.tolist(), coords))
        np.testing.assert_array_equal(out, elev)

    def test_dip_at_trace_end_is_not_corrected(self):
        n = 100
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[-11:] = 970.0

        out = np.asarray(BridgeFilter(baseline_radius_ft=1500.0).filter(elev.tolist(), coords))
        np.testing.assert_array_equal(out, elev)


class BridgeFilterPlausibilityGateTest(unittest.TestCase):
    def test_step_terrain_rejects_implausible_correction(self):
        # Flat road that steps up 50 ft right after the dip. The interpolated
        # slope across the dip would be ~0.083 (rising), but the surrounding
        # road is flat (median grade 0). The plausibility gate rejects.
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[111:] = 1050.0
        elev[100:111] = 970.0

        f = BridgeFilter(baseline_radius_ft=2000.0, grade_plausibility_tol=0.05)
        out = np.asarray(f.filter(elev.tolist(), coords))
        np.testing.assert_allclose(out[100:111], 970.0)

    def test_real_valley_road_documents_current_behavior(self):
        # A real road descending into a valley, traversing the floor, and
        # ascending out the other side. The dip-shape detector cannot tell
        # this apart from a bridge artifact without ground-truth bridge
        # data, and the plausibility gate cannot save it either: the
        # surrounding median grade balances out (descending shoulder on the
        # left cancels with ascending shoulder on the right), matching the
        # ~flat recovered slope across the symmetric valley.
        # Document the current behavior so a future refinement that learns
        # to distinguish valleys from bridges shows up as a deliberate test
        # change rather than a silent regression.
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1500.0)
        elev[60:101] = np.linspace(1500.0, 1200.0, 41)
        elev[100:121] = 1200.0
        elev[120:161] = np.linspace(1200.0, 1500.0, 41)

        f = BridgeFilter(baseline_radius_ft=2000.0)
        out = np.asarray(f.filter(elev.tolist(), coords))
        # The floor is "corrected" away from 1200 ft -- detection cannot
        # tell the valley apart from a bridge.
        self.assertFalse(np.allclose(out[100:121], 1200.0))
        # In particular the valley floor is lifted substantially toward the
        # ridge level.
        self.assertGreater(float(np.mean(out[100:121])), 1250.0)


class BridgeFilterPipelineTest(unittest.TestCase):
    def test_bridge_then_savgol(self):
        # Recommended order: bridge correction first cleans the dip, then
        # Savitzky-Golay smooths the resulting flat profile.
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[90:111] = 970.0

        after_bridge = BridgeFilter(baseline_radius_ft=2000.0).filter(elev.tolist(), coords)
        after_pipeline = SavitzkyGolayFilter(window=11, polyorder=3).filter(after_bridge, coords)

        out = np.asarray(after_pipeline)
        self.assertEqual(len(out), n)
        self.assertLess(abs(float(np.mean(out[95:106])) - 1000.0), 1.0)

    def test_savgol_then_bridge_does_not_error(self):
        # Reverse order is permitted; running SavGol first attenuates the dip
        # so bridge detection may produce less correction, but it must not
        # error and must return the right shape.
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev = np.full(n, 1000.0)
        elev[90:111] = 970.0

        after_savgol = SavitzkyGolayFilter(window=11, polyorder=3).filter(elev.tolist(), coords)
        after_pipeline = BridgeFilter(baseline_radius_ft=2000.0).filter(after_savgol, coords)
        self.assertEqual(len(after_pipeline), n)
        self.assertTrue(all(np.isfinite(v) for v in after_pipeline))


class BridgeFilterApiTest(unittest.TestCase):
    def test_does_not_mutate_input(self):
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev_list: List[float] = [1000.0] * n
        for i in range(95, 106):
            elev_list[i] = 970.0
        original = list(elev_list)

        BridgeFilter(baseline_radius_ft=2000.0).filter(elev_list, coords)
        self.assertEqual(elev_list, original)

    def test_accepts_python_lists(self):
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        elev: List[float] = [1000.0] * n
        for i in range(95, 106):
            elev[i] = 970.0

        out = BridgeFilter(baseline_radius_ft=2000.0).filter(elev, coords)
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), n)


if __name__ == "__main__":
    unittest.main()
