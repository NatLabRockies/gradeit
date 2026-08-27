"""Guard the committed documentation sample data.

The docs examples run against small corridor crops of real USGS tiles committed
under ``docs/data/`` (see ``scripts/make_docs_data.py``). Regenerating them needs
the full multi-hundred-megabyte source tiles, which are not in the repository, so
the crop step itself cannot be tested here.

What *can* be checked cheaply and offline is that the committed data is
self-consistent: every trace point must fall inside its crop and return real
elevation. That is the failure mode a bad regeneration produces -- ``USGSLocal``
returns ``NaN`` outside its coverage rather than raising, so a mismatched crop
and trace would silently feed ``NaN`` into every example instead of failing.
"""

import unittest
from pathlib import Path

import numpy as np

from gradeit import USGSLocal, gradeit
from gradeit.coordinate import Coordinate

DOCS_DATA = Path(__file__).resolve().parent.parent / "docs" / "data"
TILE_DIR = DOCS_DATA / "tiles"
TRACE_DIR = DOCS_DATA / "traces"

# Name -> expected point count, as emitted by scripts/make_docs_data.py.
EXPECTED_TRACES = {"golden_creek": 250, "carquinez": 420}


def load_trace(name):
    import csv

    with (TRACE_DIR / f"{name}.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [Coordinate.from_lat_lon(float(r["latitude"]), float(r["longitude"])) for r in rows]


class DocsDataTest(unittest.TestCase):
    def test_expected_files_exist(self):
        self.assertTrue(TILE_DIR.is_dir(), f"missing {TILE_DIR}")
        for name in EXPECTED_TRACES:
            self.assertTrue((TRACE_DIR / f"{name}.csv").is_file(), f"missing trace {name}")
        tiles = sorted(TILE_DIR.glob("*/USGS_13_*.tif"))
        self.assertTrue(tiles, "no cropped tiles committed under docs/data/tiles")

    def test_traces_have_expected_length(self):
        for name, count in EXPECTED_TRACES.items():
            with self.subTest(trace=name):
                self.assertEqual(len(load_trace(name)), count)

    def test_every_point_has_elevation(self):
        """The crop must cover its trace under both sampling modes."""
        for name in EXPECTED_TRACES:
            for sampling in ("bilinear", "nearest"):
                with self.subTest(trace=name, sampling=sampling):
                    coords = load_trace(name)
                    model = USGSLocal(TILE_DIR, sampling=sampling)
                    elevation = np.asarray(model.get_elevation(coords), dtype=float)
                    missing = int(np.isnan(elevation).sum())
                    self.assertEqual(
                        missing,
                        0,
                        f"{missing} of {len(coords)} points fell outside the {name} crop; "
                        "regenerate with scripts/make_docs_data.py",
                    )

    def test_end_to_end_produces_finite_grade(self):
        for name in EXPECTED_TRACES:
            with self.subTest(trace=name):
                result = gradeit(load_trace(name), elevation_model=USGSLocal(TILE_DIR))
                self.assertTrue(np.isfinite(result.elevation_ft_unfiltered).all())
                self.assertTrue(np.isfinite(result.grade_dec_unfiltered).all())
                self.assertIsNotNone(result.elevation_ft_filtered)
                self.assertIsNotNone(result.grade_dec_filtered)
                self.assertTrue(np.isfinite(result.elevation_ft_filtered).all())
                self.assertTrue(np.isfinite(result.grade_dec_filtered).all())

    def test_artifacts_are_still_present(self):
        """The examples' narratives depend on these artifacts surviving the crop.

        If a slice is ever renarrowed and these stop holding, the prose on the
        docs pages becomes wrong -- which is worse than a build failure, because
        nothing else would catch it.
        """
        golden = gradeit(load_trace("golden_creek"), elevation_model=USGSLocal(TILE_DIR))
        # The bare-earth creek notch at local index 119 (source index 719).
        correction = np.abs(golden.elevation_ft_filtered - golden.elevation_ft_unfiltered)
        self.assertEqual(int(np.argmax(correction)), 119)
        self.assertGreater(correction[119], 30.0)

        carquinez = gradeit(
            load_trace("carquinez"), elevation_model=USGSLocal(TILE_DIR), elevation_filter=None
        )
        # The strait crossing drives the raw grade past 80%.
        self.assertGreater(100 * np.abs(carquinez.grade_dec_unfiltered).max(), 80.0)
        # ...and the DEM reports the water surface, near sea level.
        self.assertLess(carquinez.elevation_ft_unfiltered[232:297].min(), 10.0)


if __name__ == "__main__":
    unittest.main()
