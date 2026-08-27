import unittest
import warnings
from dataclasses import FrozenInstanceError

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.exceptions import InvalidInputError, SparseGridWarning
from gradeit.filters import BridgeFilter, ElevationFilter, Wood2014Filter
from gradeit.filters._util import cumulative_distance_ft
from gradeit.filters.wood2014 import (
    _combined_filter,
    _resolve_binomial,
    _resolve_savgol,
    _supported_segments,
    binomial_filter,
    binomial_kernel,
    resolve_parameters,
)


def _make_coords(n: int, ft_step: float = 50.0) -> list[Coordinate]:
    """n coordinates spaced approximately ft_step apart along a meridian."""
    deg_per_ft = 1.0 / 364800.0  # ~ft per degree of latitude at 40 deg
    return [Coordinate.from_lat_lon(40.0 + i * ft_step * deg_per_ft, -105.0) for i in range(n)]


class BinomialPrimitiveTest(unittest.TestCase):
    def test_kernel_is_pascals_triangle(self):
        np.testing.assert_allclose(
            binomial_kernel(4), np.array([1, 4, 6, 4, 1]) / 16.0, rtol=0, atol=0
        )

    def test_kernel_sums_to_one_and_is_symmetric(self):
        for order in (2, 4, 8, 16):
            k = binomial_kernel(order)
            self.assertAlmostEqual(float(k.sum()), 1.0, places=15)
            np.testing.assert_allclose(k, k[::-1], rtol=0, atol=0)

    def test_odd_order_is_bumped_to_even(self):
        # An odd order gives an even-length kernel, which shifts the signal by
        # half a sample -- a systematic position error on a distance grid.
        self.assertEqual(binomial_kernel(3).size, 5)
        self.assertEqual(binomial_kernel(5).size, 7)

    def test_order_below_two_is_clamped(self):
        self.assertEqual(binomial_kernel(0).size, 3)
        self.assertEqual(binomial_kernel(-4).size, 3)

    def test_linear_ramp_is_preserved_exactly(self):
        # This is what odd-reflection padding buys. Even reflection or edge
        # replication would bias the terminal values.
        ramp = 3.0 * np.arange(20) + 7.0
        np.testing.assert_allclose(binomial_filter(ramp, 4), ramp, rtol=0, atol=1e-12)

    def test_quadratic_bias_is_sigma_squared_over_two(self):
        # sigma^2 = order/4 samples^2, so order=4 gives sigma=1 and a bias of 0.5.
        x = 0.5 * (np.arange(41) - 20.0) ** 2
        interior = slice(4, -4)
        np.testing.assert_allclose((binomial_filter(x, 4) - x)[interior], 0.5, rtol=0, atol=1e-12)

    def test_handles_signal_shorter_than_the_kernel(self):
        for n in (2, 3, 5):
            out = binomial_filter(np.arange(n, dtype=float), 8)
            self.assertEqual(out.size, n)
            self.assertTrue(np.all(np.isfinite(out)))

    def test_single_sample_is_returned_unchanged(self):
        np.testing.assert_allclose(binomial_filter([5.0], 4), [5.0], rtol=0, atol=0)


class CombinedFilterTest(unittest.TestCase):
    def test_linear_ramp_survives_the_full_cascade(self):
        ramp = 2.5 * np.arange(60) + 100.0
        out = _combined_filter(ramp, window=7, polyorder=3, order=4)
        np.testing.assert_allclose(out, ramp, rtol=0, atol=1e-10)

    def test_composite_center_tap_is_two_sevenths(self):
        # SG(7,3) cascaded with binomial(4) has a center tap of 96/336 = 2/7.
        impulse = np.zeros(41)
        impulse[20] = 1.0
        out = _combined_filter(impulse, window=7, polyorder=3, order=4)
        self.assertAlmostEqual(float(out[20]), 2.0 / 7.0, places=12)

    def test_composite_kernel_matches_the_analytic_taps(self):
        impulse = np.zeros(41)
        impulse[20] = 1.0
        out = _combined_filter(impulse, window=7, polyorder=3, order=4)
        expected = np.array([-2, -5, 6, 41, 80, 96, 80, 41, 6, -5, -2]) / 336.0
        np.testing.assert_allclose(out[15:26], expected, rtol=0, atol=1e-12)

    def test_stages_can_be_skipped(self):
        x = np.array([1.0, 5.0, 2.0, 8.0, 3.0])
        np.testing.assert_allclose(
            _combined_filter(x, window=0, polyorder=3, order=0), x, rtol=0, atol=0
        )


class ResolveParametersTest(unittest.TestCase):
    def test_savgol_window_resolves_from_feet(self):
        self.assertEqual(_resolve_savgol(600.0, 100.0, 201, 3), (7, 3))

    def test_savgol_window_is_clamped_to_the_grid(self):
        window, polyorder = _resolve_savgol(600.0, 100.0, 5, 3)
        self.assertEqual(window, 5)
        self.assertLess(polyorder, window)

    def test_savgol_is_skipped_on_a_tiny_grid(self):
        window, _ = _resolve_savgol(600.0, 100.0, 2, 3)
        self.assertEqual(window, 0)

    def test_binomial_sigma_is_bandwidth_invariant(self):
        # Same physical sigma at half the grid spacing must quadruple the order.
        self.assertEqual(_resolve_binomial(100.0, 100.0, 500), 4)
        self.assertEqual(_resolve_binomial(100.0, 50.0, 500), 16)

    def test_binomial_order_is_even_and_floored_at_two(self):
        for delta in (40.0, 70.0, 130.0, 900.0):
            order = _resolve_binomial(100.0, delta, 500)
            self.assertEqual(order % 2, 0)
            self.assertGreaterEqual(order, 2)

    def test_defaults_resolve_as_documented(self):
        # A 1.2 mi trace at the defaults -> ~100 ft grid, SG(7,3), binomial(4).
        delta, window, polyorder, order = resolve_parameters(Wood2014Filter(), 1.2 * 5280)
        self.assertAlmostEqual(delta, 6336.0 / 63.0, places=6)
        self.assertLess(abs(delta - 100.0), 1.0)
        self.assertEqual((window, polyorder, order), (7, 3, 4))


class SupportedSegmentsTest(unittest.TestCase):
    def test_contiguous_coverage_is_one_segment(self):
        x = np.arange(10) * 100.0
        observed = np.ones(10, dtype=bool)
        self.assertEqual(_supported_segments(observed, x, 1000.0), [(0, 9)])

    def test_short_gaps_do_not_split(self):
        x = np.arange(10) * 100.0
        observed = np.ones(10, dtype=bool)
        observed[4:6] = False  # a 300 ft gap, under the limit
        self.assertEqual(_supported_segments(observed, x, 1000.0), [(0, 9)])

    def test_long_gap_splits_the_grid(self):
        x = np.arange(20) * 100.0
        observed = np.ones(20, dtype=bool)
        observed[5:16] = False  # a 1200 ft gap
        self.assertEqual(_supported_segments(observed, x, 1000.0), [(0, 4), (16, 19)])

    def test_no_observations_yields_no_segments(self):
        x = np.arange(5) * 100.0
        self.assertEqual(_supported_segments(np.zeros(5, dtype=bool), x, 1000.0), [])


class DownsampleTest(unittest.TestCase):
    """Step B."""

    def test_grid_lands_exactly_on_both_ends_of_the_trace(self):
        coords = _make_coords(200, ft_step=50.0)
        s = cumulative_distance_ft(coords)
        f = Wood2014Filter()
        x, _, _, _, _ = f._downsample(np.full(200, 1000.0), s, float(s[-1]))
        # Exact, so step E is pure interpolation and never extrapolates.
        self.assertEqual(float(x[0]), 0.0)
        self.assertEqual(float(x[-1]), float(s[-1]))

    def test_node_value_is_the_median_not_the_mean(self):
        # One wild DEM post inside a bin must not move that bin's value.
        n = 200
        coords = _make_coords(n, ft_step=10.0)  # ~10 points per 100 ft bin
        elev = np.full(n, 1000.0)
        elev[50] = 1500.0

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        self.assertLess(float(np.max(np.abs(out - 1000.0))), 1.0)

    def test_nan_members_are_ignored_by_the_median(self):
        n = 200
        coords = _make_coords(n, ft_step=10.0)
        elev = np.full(n, 1000.0)
        elev[40:45] = np.nan

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        self.assertTrue(np.all(np.isfinite(out)))
        np.testing.assert_allclose(out, 1000.0, rtol=0, atol=1.0)

    def test_sparse_points_leave_empty_bins_but_still_interpolate(self):
        # 500 ft spacing on a 100 ft grid leaves most nodes unobserved.
        n = 50
        coords = _make_coords(n, ft_step=500.0)
        s = cumulative_distance_ft(coords)
        elev = 1000.0 + 0.03 * s

        # This is exactly what the occupancy guard exists to flag, so it warns.
        with self.assertWarns(SparseGridWarning):
            out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        self.assertTrue(np.all(np.isfinite(out)))
        np.testing.assert_allclose(out, elev, rtol=0, atol=1e-6)


class NodeOccupancyGuardTest(unittest.TestCase):
    """interval_ft finer than the points can support must not fail silently."""

    def _trace(self, n=80, ft_step=100.0):
        coords = _make_coords(n, ft_step=ft_step)
        s = cumulative_distance_ft(coords)
        return coords, (1000.0 + 0.03 * s).tolist()

    def test_grid_matched_to_spacing_does_not_warn(self):
        coords, elev = self._trace(ft_step=100.0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", SparseGridWarning)
            Wood2014Filter(interval_ft=100.0).filter(elev, coords)

    def test_grid_far_finer_than_spacing_warns(self):
        coords, elev = self._trace(ft_step=100.0)
        with self.assertWarns(SparseGridWarning) as caught:
            Wood2014Filter(interval_ft=20.0).filter(elev, coords)
        message = str(caught.warning)
        # The message must be actionable: name the knob, the occupancy, and the
        # spacing to set it from.
        self.assertIn("interval_ft=20", message)
        self.assertIn("100 ft", message)
        self.assertIn("min_node_occupancy=0", message)

    def test_guard_can_be_disabled(self):
        coords, elev = self._trace(ft_step=100.0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", SparseGridWarning)
            Wood2014Filter(interval_ft=20.0, min_node_occupancy=0.0).filter(elev, coords)

    def test_guard_does_not_change_the_output(self):
        # It is a warning, not a correction.
        coords, elev = self._trace(ft_step=100.0)
        loud = Wood2014Filter(interval_ft=20.0)
        quiet = Wood2014Filter(interval_ft=20.0, min_node_occupancy=0.0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SparseGridWarning)
            np.testing.assert_array_equal(loud.filter(elev, coords), quiet.filter(elev, coords))

    def test_real_data_gaps_do_not_trigger_the_guard(self):
        # A long unobserved stretch is already handled by max_gap_ft splitting
        # the trace, so it must not also be counted against the grid.
        coords = _make_coords(40, ft_step=100.0) + _make_coords(40, ft_step=100.0)
        s = cumulative_distance_ft(coords)
        elev = (1000.0 + 0.01 * s).tolist()
        with warnings.catch_warnings():
            warnings.simplefilter("error", SparseGridWarning)
            Wood2014Filter().filter(elev, coords)

    def test_stopped_vehicle_does_not_skew_the_advice(self):
        # Duplicate points from a parked vehicle say nothing about how finely
        # the road was sampled, so they are excluded from the median spacing.
        coords = _make_coords(60, ft_step=100.0)
        coords = coords[:30] + [coords[29]] * 40 + coords[30:]
        s = cumulative_distance_ft(coords)
        elev = (1000.0 + 0.03 * s).tolist()
        with self.assertWarns(SparseGridWarning) as caught:
            Wood2014Filter(interval_ft=20.0).filter(elev, coords)
        self.assertIn("100 ft", str(caught.warning))


class ConstantGradeTest(unittest.TestCase):
    """The routine must not distort a road that is already clean."""

    def test_constant_grade_round_trips_exactly(self):
        # Anchoring each node's median elevation to its members' median
        # *distance* is what makes this exact. Placing the median at the
        # node's nominal position aliases GPS spacing against grid spacing and
        # injects up to ~2 ft of error at 8% grade.
        for grade in (0.02, 0.05, 0.08):
            for ft_step in (25.0, 50.0, 88.0, 150.0):
                with self.subTest(grade=grade, ft_step=ft_step):
                    coords = _make_coords(200, ft_step=ft_step)
                    s = cumulative_distance_ft(coords)
                    truth = 1000.0 + grade * s
                    out = np.asarray(Wood2014Filter().filter(truth.tolist(), coords))
                    np.testing.assert_allclose(out, truth, rtol=0, atol=1e-6)

    def test_flat_road_is_preserved(self):
        coords = _make_coords(200, ft_step=50.0)
        elev = np.full(200, 1000.0)
        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        np.testing.assert_allclose(out, 1000.0, rtol=0, atol=1e-6)


class DiscardTest(unittest.TestCase):
    """Step D."""

    def _mask(self, residual, half_support_ft=0.0, **kwargs):
        # The safety valve is off by default here so each test isolates one
        # rule; on these short toy arrays a quantile-based ceiling would
        # otherwise dominate. test_max_discard_fraction_* turns it back on.
        kwargs.setdefault("max_discard_fraction", 0.0)
        f = Wood2014Filter(**kwargs)
        n = len(residual)
        x = np.arange(n) * 100.0
        return f._discard_mask(
            np.asarray(residual, float), np.ones(n, dtype=bool), x, half_support_ft
        )

    def test_node_above_threshold_is_discarded(self):
        mask = self._mask([0, 0, 0, 20.0, 0, 0, 0])
        self.assertTrue(bool(mask[3]))

    def test_node_below_threshold_is_kept(self):
        mask = self._mask([0, 0, 0, 5.0, 0, 0, 0])
        self.assertFalse(mask.any())

    def test_hysteresis_grows_a_run_from_a_seed(self):
        # A wide artifact drags the smoother with it, so the residual shrinks in
        # the middle; the flanks at 5 ft only get caught via the grow threshold.
        mask = self._mask([0, 0, 5.0, 20.0, 5.0, 0, 0])
        np.testing.assert_array_equal(mask, [False, False, True, True, True, False, False])

    def test_run_without_a_seed_is_ignored(self):
        mask = self._mask([0, 0, 5.0, 6.0, 5.0, 0, 0])
        self.assertFalse(mask.any())

    def test_run_longer_than_the_cap_is_rejected(self):
        residual = np.zeros(40)
        residual[5:35] = 20.0  # 2900 ft at a 100 ft grid
        mask = self._mask(residual)
        self.assertFalse(mask.any())

    def test_runs_touching_a_boundary_are_rejected(self):
        self.assertFalse(self._mask([20.0, 20.0, 0, 0, 0, 0, 0]).any())
        self.assertFalse(self._mask([0, 0, 0, 0, 0, 20.0, 20.0]).any())

    def test_max_discard_fraction_caps_the_damage(self):
        rng = np.random.default_rng(0)
        residual = rng.uniform(9.0, 30.0, 100)  # every node would breach 8 ft
        residual[0] = residual[-1] = 0.0
        mask = self._mask(residual, max_discard_fraction=0.25)
        self.assertLessEqual(mask.sum(), 30)

    def test_unobserved_nodes_are_never_discarded(self):
        f = Wood2014Filter()
        residual = np.full(9, 50.0)
        observed = np.ones(9, dtype=bool)
        observed[4] = False
        mask = f._discard_mask(residual, observed, np.arange(9) * 100.0, 0.0)
        self.assertFalse(bool(mask[4]))

    def test_fragments_within_one_kernel_support_are_merged(self):
        # The shoulders of a wide artifact sit on the smoothed curve, so their
        # residual is ~0 and the run fragments. Those fragments are one object.
        residual = [0, 0, 20.0, 0.5, 0.5, 20.0, 0, 0]
        np.testing.assert_array_equal(
            self._mask(residual, half_support_ft=500.0),
            [False, False, True, True, True, True, False, False],
        )

    def test_fragments_further_apart_are_not_merged(self):
        residual = [0, 0, 20.0, 0.5, 0.5, 20.0, 0, 0]
        mask = self._mask(residual, half_support_ft=100.0)
        np.testing.assert_array_equal(mask, [False, False, True, False, False, True, False, False])


class ArtifactRemovalTest(unittest.TestCase):
    def test_bridge_dip_is_discarded_and_backfilled(self):
        n = 400
        ft_step = 50.0
        coords = _make_coords(n, ft_step=ft_step)
        s = cumulative_distance_ft(coords)
        truth = np.full(n, 1000.0)
        elev = truth.copy()
        dip = (s > 8900.0) & (s < 9200.0)
        elev[dip] -= 60.0

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        # The artifact is removed, not merely attenuated.
        np.testing.assert_allclose(out[dip], 1000.0, rtol=0, atol=1.0)
        # And the rest of the road is untouched.
        far = np.abs(s - 9050.0) > 1500.0
        np.testing.assert_allclose(out[far], 1000.0, rtol=0, atol=0.5)

    def test_real_terrain_is_not_discarded(self):
        # A broad, smooth depression is topography, not a DEM artifact.
        n = 400
        coords = _make_coords(n, ft_step=50.0)
        s = cumulative_distance_ft(coords)
        elev = 1000.0 - 60.0 * np.exp(-0.5 * ((s - 10000.0) / 1200.0) ** 2)

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        self.assertLess(float(out.min()), 945.0)  # the valley survives

    def test_single_point_spike_is_removed(self):
        n = 300
        ft_step = 88.0
        coords = _make_coords(n, ft_step=ft_step)
        s = cumulative_distance_ft(coords)
        truth = 1000.0 + 0.01 * s
        elev = truth.copy()
        elev[150] -= 55.0

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        self.assertLess(abs(float(out[150] - truth[150])), 2.0)

    def test_grade_noise_is_reduced_on_a_noisy_dem(self):
        rng = np.random.default_rng(3)
        n = 500
        ft_step = 88.0
        coords = _make_coords(n, ft_step=ft_step)
        s = cumulative_distance_ft(coords)
        truth = 1000.0 + 40.0 * np.sin(2 * np.pi * s / 12000.0)
        elev = truth + rng.normal(0.0, 8.0, n)  # the DEM's own 2.44 m RMSE

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        seg = np.diff(s)
        true_grade = np.diff(truth) / seg
        raw_rmse = float(np.sqrt(np.mean((np.diff(elev) / seg - true_grade) ** 2)))
        out_rmse = float(np.sqrt(np.mean((np.diff(out) / seg - true_grade) ** 2)))
        self.assertLess(out_rmse, raw_rmse / 4.0)
        self.assertLess(out_rmse, 0.03)


class DegenerateInputTest(unittest.TestCase):
    def test_length_mismatch_raises(self):
        with self.assertRaises(InvalidInputError):
            Wood2014Filter().filter([1.0, 2.0], _make_coords(3))

    def test_two_points_returned_unchanged(self):
        coords = _make_coords(2, ft_step=50.0)
        elev = [1000.0, 1005.0]
        self.assertEqual(Wood2014Filter().filter(elev, coords), elev)

    def test_all_coincident_coordinates_returned_unchanged(self):
        coords = [Coordinate.from_lat_lon(40.0, -105.0) for _ in range(20)]
        elev = list(np.linspace(1000.0, 1010.0, 20))
        np.testing.assert_allclose(Wood2014Filter().filter(elev, coords), elev, rtol=0, atol=0)

    def test_trace_shorter_than_one_bin_returned_unchanged(self):
        coords = _make_coords(5, ft_step=10.0)  # 40 ft total, under a 100 ft bin
        elev = [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]
        self.assertEqual(Wood2014Filter().filter(elev, coords), elev)

    def test_all_nan_elevation_returns_all_nan_without_warning(self):
        coords = _make_coords(50, ft_step=50.0)
        elev = [float("nan")] * 50
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out = Wood2014Filter().filter(elev, coords)
        self.assertTrue(np.all(np.isnan(out)))

    def test_long_nan_gap_is_not_bridged(self):
        n = 200
        coords = _make_coords(n, ft_step=50.0)
        s = cumulative_distance_ft(coords)
        elev = 1000.0 + 0.02 * s
        gap = (s > 3000.0) & (s < 5000.0)  # a 2000 ft hole
        elev[gap] = np.nan

        out = np.asarray(Wood2014Filter(max_gap_ft=1000.0).filter(elev.tolist(), coords))
        self.assertTrue(np.all(np.isnan(out[gap])))
        self.assertTrue(np.all(np.isfinite(out[~gap])))

    def test_stationary_pileup_produces_identical_elevations(self):
        # 30 coincident points in the middle of a moving trace.
        coords = _make_coords(100, ft_step=88.0)
        coords = coords[:50] + [coords[50]] * 30 + coords[50:]
        s = cumulative_distance_ft(coords)
        elev = 1000.0 + 0.03 * s

        out = np.asarray(Wood2014Filter().filter(elev.tolist(), coords))
        self.assertEqual(out.size, len(coords))
        self.assertEqual(np.unique(np.round(out[50:80], 9)).size, 1)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_various_lengths_preserve_shape(self):
        for n in (2, 3, 5, 50, 500):
            with self.subTest(n=n):
                coords = _make_coords(n, ft_step=88.0)
                elev = list(1000.0 + 0.02 * np.arange(n) * 88.0)
                self.assertEqual(len(Wood2014Filter().filter(elev, coords)), n)


class Wood2014FilterApiTest(unittest.TestCase):
    def test_is_an_elevation_filter(self):
        self.assertIsInstance(Wood2014Filter(), ElevationFilter)

    def test_does_not_mutate_input(self):
        coords = _make_coords(200, ft_step=50.0)
        elev = list(np.full(200, 1000.0))
        before = list(elev)
        Wood2014Filter().filter(elev, coords)
        self.assertEqual(elev, before)

    def test_accepts_python_lists_and_returns_a_list(self):
        coords = _make_coords(200, ft_step=50.0)
        out = Wood2014Filter().filter([1000.0] * 200, coords)
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 200)

    def test_is_frozen(self):
        f = Wood2014Filter()
        with self.assertRaises(FrozenInstanceError):
            f.interval_ft = 50.0  # type: ignore[misc]

    def test_composes_with_bridge_filter(self):
        n = 300
        coords = _make_coords(n, ft_step=88.0)
        s = cumulative_distance_ft(coords)
        elev = 1000.0 + 0.01 * s
        elev[150] -= 40.0

        out = np.asarray(
            Wood2014Filter().filter(BridgeFilter().filter(elev.tolist(), coords), coords)
        )
        self.assertEqual(out.size, n)
        self.assertTrue(np.all(np.isfinite(out)))


if __name__ == "__main__":
    unittest.main(warnings="ignore")
