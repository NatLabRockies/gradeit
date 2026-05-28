import unittest
from pathlib import Path
from typing import List

import numpy as np

from gradeit import gradeit
from gradeit.coordinate import Coordinate
from gradeit.elevation import ElevationModel, USGSLocal
from gradeit.exceptions import InvalidInputError
from gradeit.filters import BridgeFilter, SavitzkyGolayFilter
from gradeit.io import GradeResult

# The synthetic fixture DB shipped alongside the elevation tests (see
# scripts/make_test_fixture.py): a 64x64 ramp tile for grid ref n40w105.
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
X_ORIGIN, Y_ORIGIN, PIXEL_SIZE = -105.0, 40.0, 0.001


def _center(col: int, row: int):
    """lon/lat of the center of integer pixel (col, row) in the fixture."""
    return X_ORIGIN + (col + 0.5) * PIXEL_SIZE, Y_ORIGIN - (row + 0.5) * PIXEL_SIZE


class StubModel(ElevationModel):
    """A custom elevation model that returns a fixed ramp, for injection tests."""

    def get_elevation(self, trace: List[Coordinate]) -> List[float]:
        return [1000.0 + 10.0 * i for i in range(len(trace))]


class GradeitLocalTest(unittest.TestCase):
    """End-to-end gradeit() against the local fixture tile."""

    def setUp(self):
        cells = [(5, 8), (10, 8), (20, 8), (30, 8), (40, 8)]
        self.coords = [
            Coordinate.from_lat_lon(lat, lon) for lon, lat in (_center(c, r) for c, r in cells)
        ]
        self.model = USGSLocal(FIXTURE_DIR, sampling="nearest")

    def test_returns_grade_result_filter_disabled(self):
        result = gradeit(self.coords, elevation_model=self.model, elevation_filter=None)
        self.assertIsInstance(result, GradeResult)
        n = len(self.coords)
        self.assertEqual(result.elevation_ft.shape, (n,))
        self.assertEqual(result.distances_ft.shape, (n,))
        self.assertEqual(result.grade_dec.shape, (n,))
        self.assertEqual(result.distances_ft[0], 0.0)
        # Filtering explicitly disabled -> filtered fields stay None.
        self.assertIsNone(result.elevation_ft_filtered)
        self.assertIsNone(result.grade_dec_filtered)

    def test_default_filter_is_bridge_filter(self):
        # With no elevation_filter argument, gradeit applies a BridgeFilter, so
        # the filtered fields are populated even though the caller asked for
        # nothing explicitly.
        result = gradeit(self.coords, elevation_model=self.model)
        self.assertIsNotNone(result.elevation_ft_filtered)
        self.assertIsNotNone(result.grade_dec_filtered)
        self.assertEqual(result.elevation_ft_filtered.shape, result.elevation_ft.shape)

    def test_empty_filter_sequence_disables_filtering(self):
        result = gradeit(self.coords, elevation_model=self.model, elevation_filter=[])
        self.assertIsNone(result.elevation_ft_filtered)
        self.assertIsNone(result.grade_dec_filtered)

    def test_elevation_filter_instance_populates_filtered_fields(self):
        result = gradeit(
            self.coords,
            elevation_model=self.model,
            elevation_filter=SavitzkyGolayFilter(window=3, polyorder=2),
        )
        self.assertIsNotNone(result.elevation_ft_filtered)
        self.assertIsNotNone(result.grade_dec_filtered)
        self.assertEqual(result.elevation_ft_filtered.shape, result.elevation_ft.shape)

    def test_elevation_filter_sequence_applies_in_order(self):
        # A sequence runs the filters left-to-right and recomputes grade once
        # from the final filtered elevation, so both filtered fields are
        # populated and stay internally consistent.
        result = gradeit(
            self.coords,
            elevation_model=self.model,
            elevation_filter=[BridgeFilter(), SavitzkyGolayFilter(window=3, polyorder=2)],
        )
        self.assertIsNotNone(result.elevation_ft_filtered)
        self.assertIsNotNone(result.grade_dec_filtered)
        # Raw arrays untouched.
        self.assertEqual(result.elevation_ft.shape, (len(self.coords),))

    def test_elevation_filter_true_raises_invalid_input(self):
        # The boolean shortcut has been removed; passing True is an error.
        with self.assertRaises(InvalidInputError):
            gradeit(self.coords, elevation_model=self.model, elevation_filter=True)

    def test_input_not_mutated(self):
        # A dict input must come back unchanged (no appended keys).
        lats = [c.latitude for c in self.coords]
        lons = [c.longitude for c in self.coords]
        data = {"latitude": list(lats), "longitude": list(lons)}
        before = {k: list(v) for k, v in data.items()}
        gradeit(data, elevation_model=self.model)
        self.assertEqual(data, before)


class GradeitInjectionTest(unittest.TestCase):
    def test_custom_elevation_model(self):
        coords = [Coordinate.from_lat_lon(39.0 + 0.01 * i, -105.0) for i in range(5)]
        result = gradeit(coords, elevation_model=StubModel())
        np.testing.assert_array_equal(result.elevation_ft, [1000.0, 1010.0, 1020.0, 1030.0, 1040.0])


class GradeitErrorTest(unittest.TestCase):
    def test_too_few_coordinates_raises(self):
        with self.assertRaises(InvalidInputError):
            gradeit([Coordinate.from_lat_lon(39.0, -105.0)], elevation_model=StubModel())


if __name__ == "__main__":
    unittest.main()
