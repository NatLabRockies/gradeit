import unittest
from pathlib import Path
from typing import List

import numpy as np

from gradeit import gradeit
from gradeit.coordinate import Coordinate
from gradeit.elevation import ElevationModel
from gradeit.exceptions import InvalidInputError, InvalidSourceError
from gradeit.filters import BridgeGradeFilter, SavitzkyGolayFilter
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

    def test_returns_grade_result_no_filter(self):
        result = gradeit(
            self.coords, source="usgs-local", usgs_db_path=FIXTURE_DIR, sampling="nearest"
        )
        self.assertIsInstance(result, GradeResult)
        n = len(self.coords)
        self.assertEqual(result.elevation_ft.shape, (n,))
        self.assertEqual(result.distances_ft.shape, (n,))
        self.assertEqual(result.grade_dec.shape, (n,))
        self.assertEqual(result.distances_ft[0], 0.0)
        # No filtering requested -> filtered fields stay None.
        self.assertIsNone(result.elevation_ft_filtered)
        self.assertIsNone(result.grade_dec_filtered)

    def test_source_enum_and_string_equivalent(self):
        from gradeit import Source

        r_str = gradeit(
            self.coords, source="usgs-local", usgs_db_path=FIXTURE_DIR, sampling="nearest"
        )
        r_enum = gradeit(
            self.coords, source=Source.USGS_LOCAL, usgs_db_path=FIXTURE_DIR, sampling="nearest"
        )
        np.testing.assert_array_equal(r_str.elevation_ft, r_enum.elevation_ft)

    def test_elevation_filter_true_populates_filtered_fields(self):
        result = gradeit(
            self.coords,
            source="usgs-local",
            usgs_db_path=FIXTURE_DIR,
            sampling="nearest",
            elevation_filter=True,
        )
        self.assertIsNotNone(result.elevation_ft_filtered)
        self.assertIsNotNone(result.grade_dec_filtered)
        self.assertEqual(result.elevation_ft_filtered.shape, result.elevation_ft.shape)

    def test_elevation_filter_instance(self):
        result = gradeit(
            self.coords,
            source="usgs-local",
            usgs_db_path=FIXTURE_DIR,
            sampling="nearest",
            elevation_filter=SavitzkyGolayFilter(window=3, polyorder=2),
        )
        self.assertIsNotNone(result.elevation_ft_filtered)

    def test_grade_filter_keeps_raw_grade_and_fills_filtered(self):
        result = gradeit(
            self.coords,
            source="usgs-local",
            usgs_db_path=FIXTURE_DIR,
            sampling="nearest",
            grade_filter=BridgeGradeFilter(),
        )
        # Raw grade preserved; corrected grade present even without elevation filtering.
        self.assertIsNotNone(result.grade_dec_filtered)
        self.assertIsNone(result.elevation_ft_filtered)

    def test_input_not_mutated(self):
        # A dict input must come back unchanged (no appended keys).
        lats = [c.latitude for c in self.coords]
        lons = [c.longitude for c in self.coords]
        data = {"latitude": list(lats), "longitude": list(lons)}
        before = {k: list(v) for k, v in data.items()}
        gradeit(data, source="usgs-local", usgs_db_path=FIXTURE_DIR, sampling="nearest")
        self.assertEqual(data, before)


class GradeitInjectionTest(unittest.TestCase):
    def test_custom_elevation_model(self):
        coords = [Coordinate.from_lat_lon(39.0 + 0.01 * i, -105.0) for i in range(5)]
        result = gradeit(coords, elevation_model=StubModel())
        np.testing.assert_array_equal(result.elevation_ft, [1000.0, 1010.0, 1020.0, 1030.0, 1040.0])


class GradeitErrorTest(unittest.TestCase):
    def setUp(self):
        self.coords = [Coordinate.from_lat_lon(39.0, -105.0), Coordinate.from_lat_lon(39.1, -105.1)]

    def test_bad_source_raises(self):
        with self.assertRaises(InvalidSourceError):
            gradeit(self.coords, source="not-a-source")

    def test_local_without_path_raises(self):
        with self.assertRaises(InvalidSourceError):
            gradeit(self.coords, source="usgs-local")

    def test_too_few_coordinates_raises(self):
        with self.assertRaises(InvalidInputError):
            gradeit([Coordinate.from_lat_lon(39.0, -105.0)], elevation_model=StubModel())


if __name__ == "__main__":
    unittest.main()
