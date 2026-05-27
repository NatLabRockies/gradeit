"""Generate the tiny synthetic USGS-style GeoTIFF used by the test suite.

The fixture mimics the structure of a real USGS 1/3 arc-second tile (LZW
compression, floating-point predictor 3, internal tiling, ModelPixelScale /
ModelTiepoint / GDAL_NODATA tags) but is only a few KB. Elevation is a
deterministic linear ramp ``BASE + A*col + B*row`` so that:

  * nearest-neighbor values are exactly known, and
  * bilinear interpolation of a linear field is analytically exact
    (``BASE + A*col + B*row`` at fractional pixel coordinates).

One cell is set to the no-data sentinel to exercise masking. Internal tiles are
intentionally small (16x16) so windowed reads must stitch several tiles.

Run with the dev environment::

    pixi run -e dev python scripts/make_test_fixture.py
"""

from pathlib import Path

import numpy as np
import tifffile

# Geo placement: NW corner of a "n40w105"-named tile.
GRID_REF = "n40w105"
X_ORIGIN = -105.0  # longitude of pixel (0, 0) top-left corner
Y_ORIGIN = 40.0  # latitude of pixel (0, 0) top-left corner
PIXEL_SIZE = 0.001  # degrees per pixel (both axes)

WIDTH = 64
HEIGHT = 64
TILE = 16

# Elevation ramp (meters): elev[row, col] = BASE + A*col + B*row
BASE = 1000.0
A = 1.5
B = -0.75

NODATA = -999999.0
NODATA_CELL = (10, 10)  # (row, col)


def make_data() -> np.ndarray:
    cols = np.arange(WIDTH, dtype=np.float32)
    rows = np.arange(HEIGHT, dtype=np.float32)
    data = BASE + A * cols[None, :] + B * rows[:, None]
    data = data.astype(np.float32)
    data[NODATA_CELL] = NODATA
    return data


def write_fixture(out_dir: Path) -> Path:
    data = make_data()
    dest_dir = out_dir / GRID_REF
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"USGS_13_{GRID_REF}.tif"

    extratags = [
        # ModelPixelScaleTag (33550): (scaleX, scaleY, scaleZ), 3 doubles
        (33550, 12, 3, (PIXEL_SIZE, PIXEL_SIZE, 0.0), True),
        # ModelTiepointTag (33922): (i, j, k, X, Y, Z), 6 doubles
        (33922, 12, 6, (0.0, 0.0, 0.0, X_ORIGIN, Y_ORIGIN, 0.0), True),
        # GDAL_NODATA (42113): ASCII
        (42113, 2, 0, "-999999", True),
    ]

    tifffile.imwrite(
        dest,
        data,
        compression="lzw",
        predictor=3,
        tile=(TILE, TILE),
        extratags=extratags,
    )
    return dest


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    out = repo_root / "tests" / "fixtures"
    path = write_fixture(out)
    print(f"wrote fixture: {path} ({path.stat().st_size} bytes)")
