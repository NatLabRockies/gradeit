import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import requests
import tifffile

from gradeit.coordinate import Coordinate
from gradeit.elevation import usgs_api
from gradeit.elevation.tiff_reader import UsgsTile
from gradeit.elevation.usgs_api import USGSApi
from gradeit.elevation.usgs_local import USGSLocal, build_grid_refs
from gradeit.exceptions import ElevationLookupError

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


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        import requests

        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Stands in for ``requests.Session``, recording the batches it is sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, data=None, timeout=None):
        self.requests.append(json.loads(data["geometry"])["points"])
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        # A bare dict is shorthand for a 200 carrying that JSON body.
        if isinstance(response, dict):
            return FakeResponse(response)
        return response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def samples_response(values, offset=0, shuffle=False):
    """A getSamples body. ``values`` is meters per point; ``None`` means the
    service returned no sample for that point (it is omitted, as the real
    service omits out-of-coverage points)."""
    samples = [
        {"locationId": i + offset, "value": f"{v:.9f}", "rasterId": 1, "resolution": 1}
        for i, v in enumerate(values)
        if v is not None
    ]
    if shuffle:
        samples = samples[::-1]
    return {"samples": samples}


class UsgsApiBatchTest(unittest.TestCase):
    """The batched getSamples request/response handling, without the network."""

    def _coords(self, n):
        return [Coordinate.from_lat_lon(39.7 + i * 1e-4, -105.1 - i * 1e-4) for i in range(n)]

    def _run(self, coords, responses, **kwargs):
        emodel = USGSApi(**kwargs)
        session = FakeSession(responses)
        with mock.patch.object(usgs_api, "_require_requests") as req:
            req.return_value = mock.Mock(
                Session=lambda: session,
                RequestException=requests.RequestException,
                HTTPError=requests.HTTPError,
            )
            return emodel.get_elevation(coords), session

    def test_converts_meters_to_feet(self):
        elev, _ = self._run(self._coords(2), [samples_response([100.0, 200.0])])
        np.testing.assert_allclose(elev, [100.0 * FT_PER_M, 200.0 * FT_PER_M], rtol=0, atol=1e-9)

    def test_reproduces_epqs_value(self):
        # The 3DEP mosaic value for 39.7 N, 105.1 W in meters; EPQS reports
        # 5565.00950796875 ft for the same point. Nearest sampling (the default)
        # must reproduce that exactly, so switching to the batch endpoint does
        # not move any elevation the package previously returned.
        elev, _ = self._run(self._coords(1), [samples_response([1696.21484375])])
        self.assertEqual(elev[0], 5565.00950796875)

    def test_out_of_order_samples_are_reordered(self):
        # The real service returns samples in arbitrary order; only locationId
        # identifies the input point.
        elev, _ = self._run(self._coords(3), [samples_response([10.0, 20.0, 30.0], shuffle=True)])
        np.testing.assert_allclose(
            elev, [10.0 * FT_PER_M, 20.0 * FT_PER_M, 30.0 * FT_PER_M], rtol=0, atol=1e-9
        )

    def test_omitted_points_become_nan(self):
        # Out-of-coverage points are dropped from the response entirely, so the
        # gap must land on the right index, not shift the remaining values.
        elev, _ = self._run(self._coords(3), [samples_response([10.0, None, 30.0])])
        np.testing.assert_allclose(elev[0], 10.0 * FT_PER_M, rtol=0, atol=1e-9)
        self.assertTrue(np.isnan(elev[1]))
        np.testing.assert_allclose(elev[2], 30.0 * FT_PER_M, rtol=0, atol=1e-9)

    def test_nan_value_becomes_nan(self):
        response = {"samples": [{"locationId": 0, "value": "NaN"}, {"locationId": 1, "value": ""}]}
        elev, _ = self._run(self._coords(2), [response])
        self.assertTrue(np.all(np.isnan(elev)))

    def test_batches_and_preserves_global_order(self):
        coords = self._coords(5)
        responses = [
            samples_response([1.0, 2.0]),
            samples_response([3.0, 4.0]),
            samples_response([5.0]),
        ]
        elev, session = self._run(coords, responses, batch_size=2)
        self.assertEqual([len(batch) for batch in session.requests], [2, 2, 1])
        np.testing.assert_allclose(
            elev, [v * FT_PER_M for v in (1.0, 2.0, 3.0, 4.0, 5.0)], rtol=0, atol=1e-9
        )

    def test_batch_size_capped_at_service_limit(self):
        # Above the limit the service truncates silently, so the cap must be
        # enforced client-side rather than trusted to the server.
        self.assertEqual(USGSApi(batch_size=5000).batch_size, usgs_api.MAX_POINTS_PER_REQUEST)

    def test_geometry_is_lon_lat_order(self):
        coords = [Coordinate.from_lat_lon(39.7, -105.1)]
        _, session = self._run(coords, [samples_response([100.0])])
        self.assertEqual(session.requests[0], [[-105.1, 39.7]])

    def test_empty_trace_makes_no_request(self):
        emodel = USGSApi()
        with mock.patch.object(usgs_api, "_require_requests") as req:
            self.assertEqual(emodel.get_elevation([]), [])
        req.assert_not_called()

    def test_error_body_with_http_200_raises(self):
        # ArcGIS reports failures inside a 200 response.
        response = FakeResponse(
            {"error": {"code": 400, "message": "Unable to complete operation."}}
        )
        with self.assertRaisesRegex(ElevationLookupError, "Unable to complete operation"):
            self._run(self._coords(2), [response])

    def test_missing_samples_key_raises(self):
        with self.assertRaisesRegex(ElevationLookupError, "no samples"):
            self._run(self._coords(1), [{"foo": "bar"}])

    def test_out_of_range_location_id_raises(self):
        response = {"samples": [{"locationId": 7, "value": "100.0"}]}
        with self.assertRaisesRegex(ElevationLookupError, "outside the 2 points"):
            self._run(self._coords(2), [response])

    def test_non_numeric_value_raises(self):
        response = {"samples": [{"locationId": 0, "value": "not-a-number"}]}
        with self.assertRaisesRegex(ElevationLookupError, "not a number"):
            self._run(self._coords(1), [response])

    def test_retries_then_succeeds(self):
        responses = [
            requests.ConnectionError("boom"),
            FakeResponse(status_code=503),
            samples_response([100.0]),
        ]
        with mock.patch.object(usgs_api.time, "sleep"):
            elev, session = self._run(self._coords(1), responses)
        self.assertEqual(len(session.requests), 3)
        np.testing.assert_allclose(elev, [100.0 * FT_PER_M], rtol=0, atol=1e-9)

    def test_retries_exhausted_raises(self):
        responses = [FakeResponse(status_code=503)] * 3
        with (
            mock.patch.object(usgs_api.time, "sleep"),
            self.assertRaisesRegex(ElevationLookupError, "after 3 attempts"),
        ):
            self._run(self._coords(1), responses)

    def test_client_error_is_not_retried(self):
        responses = [FakeResponse(status_code=404)]
        with self.assertRaisesRegex(ElevationLookupError, "HTTP 404"):
            self._run(self._coords(1), responses)

    def test_invalid_sampling_raises(self):
        with self.assertRaises(ValueError):
            USGSApi(sampling="cubic")

    def test_invalid_batch_size_raises(self):
        with self.assertRaises(ValueError):
            USGSApi(batch_size=0)

    def test_sampling_selects_interpolation_method(self):
        coords = self._coords(1)
        for sampling, expected in [
            ("nearest", "RSP_NearestNeighbor"),
            ("bilinear", "RSP_BilinearInterpolation"),
        ]:
            payload = USGSApi(sampling=sampling)._build_payload(coords)
            self.assertEqual(payload["interpolation"], expected)


# Live check against the real service (network; skipped by default).
class ElevTestApi(unittest.TestCase):
    @unittest.skip("Requires network access so skip by default")
    def test_api_no_filter(self):
        emodel = USGSApi()
        lats = np.linspace(39.702730, 39.695368, 10)
        lons = np.linspace(-105.245678, -105.209049, 10)
        coords = [Coordinate.from_lat_lon(la, lo) for la, lo in zip(lats, lons)]
        elevation_ft = emodel.get_elevation(coords)
        self.assertEqual(len(elevation_ft), len(coords))
        self.assertTrue(np.all(np.isfinite(elevation_ft)))

    @unittest.skip("Requires network access so skip by default")
    def test_api_matches_epqs(self):
        # The batched endpoint must return exactly what the per-point EPQS
        # service returns, so the switch changes no published elevation.
        import requests as _requests

        coords = [Coordinate.from_lat_lon(39.7, -105.1), Coordinate.from_lat_lon(39.71, -105.11)]
        got = USGSApi().get_elevation(coords)
        for coord, value in zip(coords, got):
            r = _requests.get(
                "https://epqs.nationalmap.gov/v1/json",
                params={
                    "x": coord.longitude,
                    "y": coord.latitude,
                    "units": "feet",
                    "wkid": 4326,
                    "includeDate": "False",
                },
                timeout=30,
            )
            self.assertAlmostEqual(value, float(r.json()["value"]), places=6)


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
        # `lonlat_at` is corner-referenced, but the stored value of pixel (c, r)
        # lives at its center -- corner coords (c + 0.5, r + 0.5). So the true
        # surface at corner coords (c, r) is ramp(c - 0.5, r - 0.5). Bilinear
        # interpolation of a linear field reproduces it exactly.
        fracs = [(5.3, 8.7), (20.5, 4.25), (40.1, 50.9)]
        lons, lats = zip(*(lonlat_at(c, r) for c, r in fracs))
        got = self.tile.sample(np.array(lons), np.array(lats), sampling="bilinear")
        expected = [ramp(c - 0.5, r - 0.5) for c, r in fracs]
        np.testing.assert_allclose(got, expected, rtol=0, atol=1e-3)

    def test_bilinear_at_pixel_center_returns_that_pixel(self):
        # The defining property of a correctly registered bilinear sampler:
        # at a pixel's own center the four weights collapse onto that pixel.
        cells = [(1, 1), (5, 8), (20, 30), (40, 50)]
        lons, lats = zip(*(center(c, r) for c, r in cells))
        got = self.tile.sample(np.array(lons), np.array(lats), sampling="bilinear")
        expected = [ramp(c, r) for c, r in cells]
        np.testing.assert_allclose(got, expected, rtol=0, atol=1e-4)

    def test_bilinear_agrees_with_nearest_at_pixel_centers(self):
        # Corollary: the two samplers must agree exactly at pixel centers, and
        # this is what pins their shared registration to the same convention.
        cells = [(3, 4), (33, 17), (50, 12)]
        lons, lats = zip(*(center(c, r) for c, r in cells))
        near = self.tile.sample(np.array(lons), np.array(lats), sampling="nearest")
        bil = self.tile.sample(np.array(lons), np.array(lats), sampling="bilinear")
        np.testing.assert_allclose(bil, near, rtol=0, atol=1e-4)

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


class TiffReaderValidationTest(unittest.TestCase):
    """``open()`` rejects rasters that violate the reader's single-band,
    north-up, geographic-lon/lat assumptions instead of silently sampling
    wrong values."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, data, extratags, name="t.tif", **kwargs):
        dest = self.dir / name
        tifffile.imwrite(dest, data, tile=(16, 16), extratags=extratags, **kwargs)
        return dest

    def _geo_tags(self, model_type=None):
        """ModelPixelScale + ModelTiepoint georef; optional GeoKeyDirectory
        carrying GTModelTypeGeoKey (1=projected, 2=geographic, 3=geocentric)."""
        tags = [
            (33550, 12, 3, (PIXEL_SIZE, PIXEL_SIZE, 0.0), True),
            (33922, 12, 6, (0.0, 0.0, 0.0, X_ORIGIN, Y_ORIGIN, 0.0), True),
        ]
        if model_type is not None:
            # header (version, key_rev, minor_rev, num_keys) + one key entry
            # (key_id=1024, location=0 inline, count=1, value=model_type)
            tags.append((34735, 3, 8, (1, 1, 0, 1, 1024, 0, 1, model_type), True))
        return tags

    def test_multiband_rejected(self):
        # photometric="rgb" pins three contiguous samples in one page, so
        # page[0].samplesperpixel == 3 regardless of tifffile's default.
        data = np.zeros((32, 32, 3), dtype=np.float32)
        path = self._write(data, self._geo_tags(model_type=2), photometric="rgb")
        with self.assertRaisesRegex(ValueError, "single-band"):
            UsgsTile(path).open()

    def test_projected_crs_rejected(self):
        data = np.zeros((32, 32), dtype=np.float32)
        path = self._write(data, self._geo_tags(model_type=1))
        with self.assertRaisesRegex(ValueError, "geographic"):
            UsgsTile(path).open()

    def test_geographic_crs_accepted(self):
        data = np.zeros((32, 32), dtype=np.float32)
        path = self._write(data, self._geo_tags(model_type=2))
        with UsgsTile(path) as tile:
            self.assertEqual((tile.transform.width, tile.transform.height), (32, 32))

    def test_absent_crs_allowed(self):
        # No GeoKeyDirectory (as in the real fixture): unverifiable, so allowed.
        data = np.zeros((32, 32), dtype=np.float32)
        path = self._write(data, self._geo_tags())
        with UsgsTile(path) as tile:
            self.assertIsNotNone(tile.transform)

    def test_rotated_transformation_rejected(self):
        data = np.zeros((32, 32), dtype=np.float32)
        s = PIXEL_SIZE
        m = (
            s,
            s * 0.5,
            0.0,
            X_ORIGIN,  # off-diagonal s*0.5 => rotation/skew
            s * 0.5,
            -s,
            0.0,
            Y_ORIGIN,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        )
        path = self._write(data, [(34264, 12, 16, m, True)])
        with self.assertRaisesRegex(ValueError, "rotat"):
            UsgsTile(path).open()


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
