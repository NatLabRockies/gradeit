"""Generate the small, committed elevation data that the documentation examples use.

The docs are built and executed on CI, so they cannot download the USGS raster
tiles that ``examples/`` relies on -- those run 220-490 MB *each*. This script
crops the real tiles down to a narrow corridor around two short demo traces,
producing tiles small enough to commit (a few hundred KB) that are still real
terrain, with the real bare-earth artifacts the docs are about.

The crop stays a drop-in for :class:`gradeit.USGSLocal` because
``gradeit/elevation/tiff_reader.py`` derives its geotransform from the
``ModelPixelScale`` / ``ModelTiepoint`` tags rather than assuming a tile spans a
full 1x1 degree cell. Points outside the crop simply read back as ``NaN``.

Everything outside ``CORRIDOR_FT`` of the trace is set to the no-data sentinel.
Constant regions cost almost nothing under LZW, and that -- not the bounding box
-- is what keeps the files small.

This is a maintainer tool: it needs the full source tiles, which are not in the
repository. Run it only when the demo traces or the crop parameters change, then
commit the regenerated ``docs/data/``.

Usage::

    pixi run -e dev python scripts/make_docs_data.py \\
        --source-dir dev-data.local/denver-usgs-tiles \\
        --source-dir dev-data.local/sf-usgs-tiles
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import tifffile

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gradeit.coordinate import Coordinate  # noqa: E402
from gradeit.elevation.tiff_reader import (  # noqa: E402
    _TAG_GDAL_NODATA,
    _TAG_GEO_KEY_DIRECTORY,
    _TAG_MODEL_PIXEL_SCALE,
    _TAG_MODEL_TIEPOINT,
    UsgsTile,
)
from gradeit.elevation.usgs_local import get_raster_elev_profile  # noqa: E402

# No-data sentinel, matching what USGS itself writes and what the reader expects.
NODATA = -999999.0

# GeoKeyDirectory (34735) indexes into GeoDoubleParams (34736) and GeoAsciiParams
# (34737), so the three travel together or not at all. gradeit's reader tolerates
# their absence, but a tile without them has no declared CRS and opens badly in
# QGIS/GDAL, so the crop carries them through verbatim.
_TAG_GEO_DOUBLE_PARAMS = 34736
_TAG_GEO_ASCII_PARAMS = 34737

# Half-width of the retained corridor around each trace. This is the size knob:
# shrink it if a crop lands too large, but keep it far above the ~33 ft DEM post
# spacing. At 1/3 arc-second, 500 ft is roughly 15 pixels, which keeps every demo
# point clear of both the new raster edge (where bilinear sampling falls back to
# nearest) and the no-data boundary (where bilinear renormalizes over the valid
# neighbors). verify() proves that margin rather than assuming it.
CORRIDOR_FT = 500.0

# Extra pixels of raster kept beyond the corridor bounding box, so no point's
# bilinear 2x2 footprint can reach the crop edge.
PAD_PX = 8

# Internal tile size of the written GeoTIFF. Smaller than the USGS originals
# because these rasters are small; keeps the windowed-read path exercised.
TILE = 128

# Accepted disagreement between the crop and the full tile, in feet. Far below
# anything physical; see verify() for why it is not exactly zero.
TOLERANCE_FT = 1e-6

FT_PER_DEG_LAT = 364000.0


@dataclass(frozen=True)
class Demo:
    """One documentation demo: a trace slice and the tile that covers it."""

    name: str
    source_csv: str
    start: int
    stop: int
    grid_ref: str
    note: str


# The slice bounds are the reproducible record of what the docs demonstrate.
#
# Both slices are deliberately wider than the artifact they showcase: BridgeFilter
# rejects any candidate run that touches a trace boundary, and needs
# baseline_radius_ft of real road beyond each end of a dip before it will act.
# Golden gives ~23,500 / ~16,900 ft around the creek (clearing the 5,280 ft
# default); Carquinez gives ~11,200 / ~10,800 ft around the strait (clearing the
# 6,000 ft radius its 5,159 ft span requires).
DEMOS: List[Demo] = [
    Demo(
        name="golden_creek",
        source_csv="examples/data/sample_trip_1.csv",
        start=600,
        stop=850,
        grid_ref="n40w106",
        note="US-6 west of Golden, CO. Carries the bare-earth creek notch at "
        "source index 719 and a genuine 172 ft valley around it.",
    ),
    Demo(
        name="carquinez",
        source_csv="examples/data/SF_bridge_trip_segment.csv",
        start=4080,
        stop=4500,
        grid_ref="n39w123",
        note="I-80 across the Carquinez Strait. Carries two bare-earth artifacts "
        "on opposite sides of the default filter's competence: an ~800 ft "
        "crossing it removes by itself, and the 5,159 ft strait crossing it "
        "cannot reach. Starting at 4080 (not 4200) is what keeps the short "
        "crossing in frame; starting at 4050 would pull in a second tile.",
    ),
]


def read_trace(csv_path: Path, start: int, stop: int) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read a slice of a trace CSV, returning rows and the source field order."""
    with csv_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "latitude" not in fieldnames or "longitude" not in fieldnames:
        raise SystemExit(f"{csv_path}: expected 'latitude' and 'longitude' columns")
    if stop > len(rows):
        raise SystemExit(f"{csv_path}: slice {start}:{stop} exceeds {len(rows)} rows")
    return rows[start:stop], fieldnames


def write_trace(rows: Sequence[Dict[str, str]], fieldnames: Sequence[str], dest: Path) -> None:
    """Write the slice with latitude/longitude first, other columns unchanged.

    The two source files disagree on column order and naming, so normalizing the
    lead columns lets every docs example read them the same way.
    """
    rest = [f for f in fieldnames if f not in ("latitude", "longitude")]
    out_fields = ["latitude", "longitude", *rest]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row[f] for f in out_fields})


def densify(cols: np.ndarray, rows: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Interpolate a pixel-space polyline down to sub-pixel steps.

    GPS traces are sampled in time, so consecutive points can be a dozen pixels
    apart on a fast stretch of road. Stamping only the sample points would leave
    scalloped gaps between them; walking the segments closes the corridor.
    """
    out_c: List[np.ndarray] = []
    out_r: List[np.ndarray] = []
    for i in range(len(cols) - 1):
        steps = max(
            2, int(np.ceil(2 * max(abs(cols[i + 1] - cols[i]), abs(rows[i + 1] - rows[i]))))
        )
        out_c.append(np.linspace(cols[i], cols[i + 1], steps))
        out_r.append(np.linspace(rows[i], rows[i + 1], steps))
    if not out_c:
        return cols, rows
    return np.concatenate(out_c), np.concatenate(out_r)


def corridor_mask(
    shape: Tuple[int, int],
    cols: np.ndarray,
    rows: np.ndarray,
    radius_px_x: int,
    radius_px_y: int,
) -> np.ndarray:
    """Boolean mask of pixels within an elliptical radius of the trace.

    A degree of longitude is shorter than a degree of latitude, so a circular
    corridor on the ground is an ellipse in pixel space; the two radii keep the
    retained band the same physical width in both directions.
    """
    cols, rows = densify(cols, rows)

    mask = np.zeros(shape, dtype=bool)
    yy = np.arange(-radius_px_y, radius_px_y + 1)[:, None] / float(radius_px_y)
    xx = np.arange(-radius_px_x, radius_px_x + 1)[None, :] / float(radius_px_x)
    disc = (yy**2 + xx**2) <= 1.0

    height, width = shape
    for col, row in zip(cols, rows):
        c, r = int(round(col)), int(round(row))
        r0, r1 = r - radius_px_y, r + radius_px_y + 1
        c0, c1 = c - radius_px_x, c + radius_px_x + 1
        # Clip the stamp against the raster bounds.
        sr0, sr1 = max(0, r0), min(height, r1)
        sc0, sc1 = max(0, c0), min(width, c1)
        if sr1 <= sr0 or sc1 <= sc0:
            continue
        mask[sr0:sr1, sc0:sc1] |= disc[sr0 - r0 : sr1 - r0, sc0 - c0 : sc1 - c0]
    return mask


def copy_geo_tags(tile: UsgsTile) -> List[tuple]:
    """Carry the source tile's CRS declaration into the crop, if it has one.

    The three tags are a unit: GeoKeyDirectory entries reference offsets into
    GeoDoubleParams and GeoAsciiParams, so copying one without the others would
    produce a file that names parameters it does not contain.
    """
    page = tile._page
    assert page is not None
    specs = [
        (_TAG_GEO_KEY_DIRECTORY, 3),  # SHORT
        (_TAG_GEO_DOUBLE_PARAMS, 12),  # DOUBLE
        (_TAG_GEO_ASCII_PARAMS, 2),  # ASCII
    ]
    out: List[tuple] = []
    for code, dtype in specs:
        tag = page.tags.get(code)
        if tag is None or tag.value is None:
            return []  # all or nothing
        value = tag.value
        if dtype == 2:
            if isinstance(value, bytes):
                value = value.decode("ascii", "ignore")
            out.append((code, dtype, 0, str(value), True))
        else:
            seq = tuple(value)
            out.append((code, dtype, len(seq), seq, True))
    return out


def check_footprints(keep: np.ndarray, cols: np.ndarray, rows: np.ndarray) -> None:
    """Fail if any point's bilinear 2x2 footprint leaves the kept region.

    ``UsgsTile.sample`` shifts by half a pixel for bilinear, so a point at
    fractional column ``c`` reads columns ``floor(c - 0.5)`` and that plus one.
    If either lands outside the raster, sampling silently drops to nearest
    neighbor; if either is masked, the bilinear weights renormalize. Both would
    make the crop disagree with the source, so catch it before writing.
    """
    height, width = keep.shape
    base_c = np.floor(cols - 0.5).astype(int)
    base_r = np.floor(rows - 0.5).astype(int)
    inside = (base_c >= 0) & (base_c + 1 < width) & (base_r >= 0) & (base_r + 1 < height)
    if not inside.all():
        raise SystemExit(
            f"{int((~inside).sum())} point(s) have a bilinear footprint outside the crop; "
            f"increase PAD_PX (currently {PAD_PX})."
        )
    masked = 0
    for dr in (0, 1):
        for dc in (0, 1):
            masked += int((~keep[base_r + dr, base_c + dc]).sum())
    if masked:
        raise SystemExit(
            f"corridor mask clipped {masked} bilinear footprint cell(s); "
            f"increase CORRIDOR_FT (currently {CORRIDOR_FT:g} ft)."
        )


def crop_tile(source_tile: Path, dest_tile: Path, lats: np.ndarray, lons: np.ndarray) -> None:
    """Write a corridor-masked crop of ``source_tile`` covering the given points."""
    with UsgsTile(source_tile) as tile:
        transform = tile.transform
        assert transform is not None

        # Pad the bounding box by the corridor radius, in degrees.
        pad_lat = CORRIDOR_FT / FT_PER_DEG_LAT
        pad_lon = pad_lat / max(np.cos(np.radians(float(np.mean(lats)))), 1e-6)

        cols, rows = transform.lonlat_to_pixel(
            np.array([lons.min() - pad_lon, lons.max() + pad_lon]),
            np.array([lats.max() + pad_lat, lats.min() - pad_lat]),
        )
        col0 = max(0, int(np.floor(cols.min())) - PAD_PX)
        col1 = min(transform.width, int(np.ceil(cols.max())) + 1 + PAD_PX)
        row0 = max(0, int(np.floor(rows.min())) - PAD_PX)
        row1 = min(transform.height, int(np.ceil(rows.max())) + 1 + PAD_PX)

        window, c0, r0 = tile.read_window(col0, row0, col1 - col0, row1 - row0)
        if window.size == 0:
            raise SystemExit(f"{source_tile}: demo points fall outside the tile")

        # Trace pixel coordinates, relative to the cropped window.
        pcols, prows = transform.lonlat_to_pixel(lons, lats)
        radius_px_y = max(1, int(round(pad_lat / abs(transform.pixel_height))))
        radius_px_x = max(1, int(round(pad_lon / transform.pixel_width)))
        keep = corridor_mask(window.shape, pcols - c0, prows - r0, radius_px_x, radius_px_y)

        check_footprints(keep, pcols - c0, prows - r0)

        data = window.astype(np.float32)
        data[~keep] = NODATA

        new_x = transform.x_origin + c0 * transform.pixel_width
        new_y = transform.y_origin + r0 * transform.pixel_height
        pixel_scale = (transform.pixel_width, abs(transform.pixel_height), 0.0)
        geo_tags = copy_geo_tags(tile)
        kept_pct = 100.0 * float(keep.mean())

    extratags = [
        (_TAG_MODEL_PIXEL_SCALE, 12, 3, pixel_scale, True),
        (_TAG_MODEL_TIEPOINT, 12, 6, (0.0, 0.0, 0.0, new_x, new_y, 0.0), True),
        (_TAG_GDAL_NODATA, 2, 0, str(int(NODATA)), True),
        *geo_tags,
    ]
    print(f"    window {data.shape[1]}x{data.shape[0]} px, {kept_pct:.1f}% kept")
    dest_tile.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        dest_tile,
        data,
        compression="lzw",
        predictor=3,
        tile=(TILE, TILE),
        extratags=extratags,
    )


def verify(source_root: Path, docs_tiles: Path, coords: List[Coordinate], label: str) -> None:
    """Assert the crop reproduces the full tile at every demo point.

    Cropping introduces raster edges that did not exist before, and masking
    introduces no-data neighbors -- both change how ``sample()`` behaves near
    them. This is the check that the corridor padding is actually sufficient.

    The tolerance is not zero because the crop carries a different tiepoint
    origin, so ``(lon - x_origin) / pixel_width`` rounds differently in the last
    bit or two and the bilinear weights shift by ~1e-16. That is float noise,
    around a trillionth of a foot. A genuinely insufficient corridor does not
    fail subtly -- it returns NaN, or reads a neighboring cell and misses by
    feet -- so anything above TOLERANCE_FT is a real defect.
    """
    for sampling in ("bilinear", "nearest"):
        full = np.asarray(get_raster_elev_profile(coords, source_root, sampling=sampling))
        crop = np.asarray(get_raster_elev_profile(coords, docs_tiles, sampling=sampling))
        if np.isnan(full).any():
            raise SystemExit(f"{label}: source tile returned NaN; wrong tile or bad trace slice")
        if np.isnan(crop).any():
            n = int(np.isnan(crop).sum())
            raise SystemExit(
                f"{label}: crop returned NaN at {n} point(s) under {sampling} sampling. "
                f"Increase CORRIDOR_FT (currently {CORRIDOR_FT:g} ft)."
            )
        diff = float(np.max(np.abs(full - crop)))
        if diff > TOLERANCE_FT:
            raise SystemExit(
                f"{label}: crop disagrees with the full tile by up to {diff:g} ft under "
                f"{sampling} sampling. Increase CORRIDOR_FT (currently {CORRIDOR_FT:g} ft)."
            )
        print(
            f"    verified {sampling:<9} max|full - crop| = {diff:.3g} ft over {len(coords)} points"
        )


def find_source_tile(source_dirs: Sequence[Path], grid_ref: str) -> Path:
    for root in source_dirs:
        candidate = root / grid_ref / f"USGS_13_{grid_ref}.tif"
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(d) for d in source_dirs)
    raise SystemExit(
        f"Could not find {grid_ref}/USGS_13_{grid_ref}.tif under: {searched}\n"
        "Download it with scripts/get_usgs_tiles.py, or pass --source-dir."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source-dir",
        action="append",
        type=Path,
        default=None,
        help="Directory of full USGS tiles, laid out {grid_ref}/USGS_13_{grid_ref}.tif. "
        "Repeatable; all are searched.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "data",
        help="Where to write tiles/ and traces/ (default: docs/data).",
    )
    args = parser.parse_args()

    source_dirs = args.source_dir or [
        REPO_ROOT / "dev-data.local" / "denver-usgs-tiles",
        REPO_ROOT / "dev-data.local" / "sf-usgs-tiles",
    ]

    tiles_dir = args.output_dir / "tiles"
    traces_dir = args.output_dir / "traces"

    total_bytes = 0
    for demo in DEMOS:
        print(f"\n{demo.name}  ({demo.source_csv}[{demo.start}:{demo.stop}] -> {demo.grid_ref})")
        rows, fieldnames = read_trace(REPO_ROOT / demo.source_csv, demo.start, demo.stop)
        lats = np.array([float(r["latitude"]) for r in rows])
        lons = np.array([float(r["longitude"]) for r in rows])
        coords = [Coordinate.from_lat_lon(la, lo) for la, lo in zip(lats, lons)]

        trace_path = traces_dir / f"{demo.name}.csv"
        write_trace(rows, fieldnames, trace_path)
        print(
            f"    trace  {trace_path.relative_to(REPO_ROOT)}  "
            f"{len(rows)} points, {trace_path.stat().st_size:,} bytes"
        )

        source_tile = find_source_tile(source_dirs, demo.grid_ref)
        dest_tile = tiles_dir / demo.grid_ref / f"USGS_13_{demo.grid_ref}.tif"
        crop_tile(source_tile, dest_tile, lats, lons)
        size = dest_tile.stat().st_size
        total_bytes += size
        print(
            f"    tile   {dest_tile.relative_to(REPO_ROOT)}  "
            f"{size:,} bytes (from {source_tile.stat().st_size:,})"
        )

        verify(source_tile.parent.parent, tiles_dir, coords, demo.name)

    print(f"\nTotal committed tile bytes: {total_bytes:,}")


if __name__ == "__main__":
    main()
