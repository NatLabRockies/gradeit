import unittest
from pathlib import Path

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.elevation.tiff_reader import UsgsTile
from gradeit.elevation.usgs_api import USGSApi
from gradeit.elevation.usgs_local import USGSLocal, build_grid_refs

# Constants mirroring scripts/make_test_fixture.py. The fixture is a 64x64
# float32 GeoTIFF (LZW + predictor 3, 16x16 internal tiles) whose elevation is
# the linear ramp BASE + A*col + B*row, with one no-data cell. A linear field
# makes bilinear interpolation analytically exact, so golden values are precise.
# Anchor to this test file (the fixture ships alongside it) rather than to the
# installed gradeit package, which may live elsewhere under a non-editable install.
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
GRID_REF = "n40w105"
FIXTURE_TILE = FIXTURE_DIR / GRID_REF / f"USGS_13_{GRID_REF}.tif"
X_ORIGIN, Y_ORIGIN, PIXEL_SIZE = -105.0, 40.0, 0.001
WIDTH = HEIGHT = 64
BASE, A, B = 1000.0, 1.5, -0.75
NODATA_CELL = (10, 10)  # (row, col)
FT_PER_M = 3.28084


def lonlat_at(col: float, row: float):
    """lon/lat for a (possibly fractional) pixel coordinate in the fixture."""
    return X_ORIGIN + col * PIXEL_SIZE, Y_ORIGIN - row * PIXEL_SIZE


def center(col: int, row: int):
    """lon/lat of the center of integer pixel (col, row)."""
    return lonlat_at(col + 0.5, row + 0.5)


def ramp(col: float, row: float) -> float:
    return BASE + A * col + B * row


# Test the USGS Web API implementation (network; skipped by default).
class ElevTestApi(unittest.TestCase):
    @unittest.skip("Takes some time so skip by default")
    def test_api_no_filter(self):
        emodel = USGSApi()
        lats = np.linspace(39.702730, 39.695368, 10)
        lons = np.linspace(-105.245678, -105.209049, 10)
        coords = [Coordinate.from_lat_lon(la, lo) for la, lo in zip(lats, lons)]
        elevation_ft = emodel.get_elevation(coords)
        self.assertEqual(len(elevation_ft), len(coords))


class TiffReaderTest(unittest.TestCase):
    """Sampling behavior of the pure-Python GeoTIFF reader, via the fixture."""

    def setUp(self):
        self.tile = UsgsTile(FIXTURE_TILE).open()

    def tearDown(self):
        self.tile.close()

    def test_transform_from_tags(self):
        gt = self.tile.transform
        self.assertAlmostEqual(gt.x_origin, X_ORIGIN)
        self.assertAlmostEqual(gt.y_origin, Y_ORIGIN)
        self.assertAlmostEqual(gt.pixel_width, PIXEL_SIZE)
        self.assertAlmostEqual(gt.pixel_height, -PIXEL_SIZE)
        self.assertEqual((gt.width, gt.height), (WIDTH, HEIGHT))
        self.assertEqual(self.tile.nodata, -999999.0)

    def test_nearest_matches_ramp(self):
        # Sample a spread of pixel centers across multiple internal tiles.
        cells = [(0, 0), (5, 8), (33, 17), (60, 60), (63, 63)]
        lons, lats = zip(*(center(c, r) for c, r in cells))
        got = self.tile.sample(np.array(lons), np.array(lats), sampling="nearest")
        expected = [ramp(c, r) for c, r in cells]
        np.testing.assert_allclose(got, expected, rtol=0, atol=1e-4)

    def test_bilinear_exact_on_linear_field(self):
        fracs = [(5.3, 8.7), (20.5, 4.25), (40.1, 50.9)]
        lons, lats = zip(*(lonlat_at(c, r) for c, r in fracs))
        got = self.tile.sample(np.array(lons), np.array(lats), sampling="bilinear")
        expected = [ramp(c, r) for c, r in fracs]
        np.testing.assert_allclose(got, expected, rtol=0, atol=1e-3)

    def test_bilinear_differs_from_nearest(self):
        lon, lat = lonlat_at(5.3, 8.7)
        near = self.tile.sample(np.array([lon]), np.array([lat]), sampling="nearest")[0]
        bil = self.tile.sample(np.array([lon]), np.array([lat]), sampling="bilinear")[0]
        self.assertGreater(abs(near - bil), 1e-6)

    def test_nodata_returns_nan(self):
        row, col = NODATA_CELL
        lon, lat = center(col, row)
        got = self.tile.sample(np.array([lon]), np.array([lat]), sampling="nearest")
        self.assertTrue(np.isnan(got[0]))

    def test_bilinear_renormalizes_near_nodata(self):
        # A fractional point adjacent to the no-data cell must stay finite and
        # never be contaminated by the -999999 sentinel.
        row, col = NODATA_CELL
        lon, lat = lonlat_at(col + 0.4, row + 0.4)
        got = self.tile.sample(np.array([lon]), np.array([lat]), sampling="bilinear")[0]
        self.assertTrue(np.isfinite(got))
        self.assertGreater(got, 0.0)

    def test_out_of_bounds_returns_nan(self):
        lons = np.array([-200.0, X_ORIGIN - 1.0])
        lats = np.array([0.0, Y_ORIGIN + 1.0])
        got = self.tile.sample(lons, lats, sampling="bilinear")
        self.assertEqual(len(got), 2)
        self.assertTrue(np.all(np.isnan(got)))

    def test_tile_edge_bilinear_falls_back_to_nearest(self):
        # Center of the last column: the 2x2 bilinear footprint would leave the
        # raster, so it must fall back to nearest (finite, not NaN).
        lon, lat = center(WIDTH - 1, 30)
        got = self.tile.sample(np.array([lon]), np.array([lat]), sampling="bilinear")[0]
        self.assertTrue(np.isfinite(got))
        np.testing.assert_allclose(got, ramp(WIDTH - 1, 30), rtol=0, atol=1e-4)

    def test_empty_input(self):
        got = self.tile.sample(np.array([]), np.array([]), sampling="bilinear")
        self.assertEqual(len(got), 0)

    def test_invalid_sampling_raises(self):
        with self.assertRaises(ValueError):
            self.tile.sample(np.array([X_ORIGIN]), np.array([Y_ORIGIN]), sampling="cubic")


class UsgsLocalTest(unittest.TestCase):
    """End-to-end local elevation lookup against the fixture database."""

    def test_get_elevation_values_and_order(self):
        emodel = USGSLocal(FIXTURE_DIR, sampling="nearest")
        cells = [(5, 8), (60, 60), (0, 0)]
        coords = []
        for c, r in cells:
            lon, lat = center(c, r)
            coords.append(Coordinate.from_lat_lon(lat, lon))
        elev_ft = emodel.get_elevation(coords)
        self.assertEqual(len(elev_ft), len(coords))
        expected_ft = [ramp(c, r) * FT_PER_M for c, r in cells]
        np.testing.assert_allclose(elev_ft, expected_ft, rtol=0, atol=1e-3)

    def test_default_sampling_is_bilinear(self):
        self.assertEqual(USGSLocal(FIXTURE_DIR).sampling, "bilinear")

    def test_out_of_coverage_returns_nan(self):
        # Southern/eastern hemisphere point maps to grid ref "0" -> NaN, and the
        # in-coverage point is still resolved (length and order preserved).
        emodel = USGSLocal(FIXTURE_DIR, sampling="nearest")
        lon_in, lat_in = center(5, 8)
        coords = [
            Coordinate.from_lat_lon(-10.0, 20.0),
            Coordinate.from_lat_lon(lat_in, lon_in),
        ]
        elev_ft = emodel.get_elevation(coords)
        self.assertTrue(np.isnan(elev_ft[0]))
        np.testing.assert_allclose(elev_ft[1], ramp(5, 8) * FT_PER_M, rtol=0, atol=1e-3)

    def test_missing_tile_raises(self):
        emodel = USGSLocal(FIXTURE_DIR)
        # In-coverage but no tile on disk for this grid ref.
        coords = [Coordinate.from_lat_lon(45.5, -110.5)]
        with self.assertRaises(FileNotFoundError):
            emodel.get_elevation(coords)

    def test_invalid_sampling_raises(self):
        with self.assertRaises(ValueError):
            USGSLocal(FIXTURE_DIR, sampling="cubic")


class BuildGridRefsTest(unittest.TestCase):
    def test_western_northern_hemisphere(self):
        refs = build_grid_refs([39.99, 45.2], [-104.99, -110.8])
        self.assertEqual(list(refs), ["n40w105", "n46w111"])

    def test_longitude_zero_padded_to_three(self):
        refs = build_grid_refs([40.5], [-66.5])
        self.assertEqual(list(refs), ["n41w067"])

    def test_out_of_coverage_maps_to_zero(self):
        refs = build_grid_refs([-10.0, 10.0], [20.0, 30.0])
        self.assertEqual(list(refs), ["0", "0"])


if __name__ == "__main__":
    unittest.main(warnings="ignore")
