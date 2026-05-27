from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple, Union

import numpy as np
import tifffile

# GeoTIFF tag numbers. We read tags by number (not by tifffile's parsed
# ``geotiff_metadata``) so behavior is stable across tifffile versions.
_TAG_MODEL_PIXEL_SCALE = 33550
_TAG_MODEL_TIEPOINT = 33922
_TAG_MODEL_TRANSFORMATION = 34264
_TAG_GDAL_NODATA = 42113
_TAG_GEO_KEY_DIRECTORY = 34735

# GTModelTypeGeoKey (key 1024) records the coordinate-system family. This reader
# samples points by longitude/latitude in degrees, so only a geographic CRS is
# valid; projected (1) and geocentric (3) rasters would be sampled at the wrong
# location.
_GTMODELTYPE_KEY = 1024
_MODEL_TYPE_GEOGRAPHIC = 2

# A ModelTransformation's off-diagonal (rotation/skew) terms are rejected if
# they exceed this fraction of the pixel scale; the raster must be north-up and
# axis-aligned (the ModelPixelScale/Tiepoint form cannot encode rotation, so
# only the matrix form needs checking).
_ROTATION_REL_TOL = 1e-6

# USGS uses a large-magnitude negative sentinel for voids/no-data.
_DEFAULT_NODATA = -999999.0
# Anything at or below this is treated as no-data regardless of the tag, to
# guard against undocumented void values.
_NODATA_FLOOR = -1.0e5

VALID_SAMPLING = frozenset({"nearest", "bilinear"})


def validate_sampling(sampling: str) -> str:
    if sampling not in VALID_SAMPLING:
        raise ValueError(f"Invalid sampling {sampling!r}. Choose one of {sorted(VALID_SAMPLING)}.")
    return sampling


@dataclass(frozen=True)
class GeoTransform:
    """Affine mapping between lon/lat (degrees) and fractional pixel coords.

    Assumes a north-up, axis-aligned raster (the USGS 1/3 arc-second case);
    pixel (0, 0) is the top-left corner.
    """

    x_origin: float  # longitude of the top-left corner of pixel (0, 0)
    y_origin: float  # latitude of the top-left corner of pixel (0, 0)
    pixel_width: float  # degrees per pixel in X (> 0)
    pixel_height: float  # degrees per pixel in Y (< 0, rows increase southward)
    width: int  # raster width in pixels
    height: int  # raster height in pixels

    def lonlat_to_pixel(self, lon: np.ndarray, lat: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Return fractional (column, row) for arrays of lon/lat."""
        col = (np.asarray(lon, dtype=np.float64) - self.x_origin) / self.pixel_width
        row = (np.asarray(lat, dtype=np.float64) - self.y_origin) / self.pixel_height
        return col, row


class UsgsTile:
    """A single USGS 1/3 arc-second GeoTIFF, opened lazily for windowed reads."""

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._tif: tifffile.TiffFile | None = None
        self._page: Any = None  # tifffile TiffPage; Any avoids TiffPage/TiffFrame union noise
        self.transform: GeoTransform | None = None
        self.nodata: float = _DEFAULT_NODATA

    def open(self) -> "UsgsTile":
        self._tif = tifffile.TiffFile(self.path)
        try:
            # pages[0] is the full-resolution image; later pages are COG overviews.
            self._page = self._tif.pages[0]
            self._validate_page(self._page)
            self.transform = self._transform_from_tags(self._page)
            self.nodata = self._nodata_from_tags(self._page)
        except Exception:
            # Don't leak the open handle if validation/parsing fails; on Windows
            # an open handle locks the file and blocks any later deletion.
            self.close()
            raise
        return self

    def close(self) -> None:
        if self._tif is not None:
            self._tif.close()
        self._tif = None
        self._page = None

    def __enter__(self) -> "UsgsTile":
        if self._tif is None:
            self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @staticmethod
    def _transform_from_tags(page) -> GeoTransform:
        width = int(page.imagewidth)
        height = int(page.imagelength)
        tags = page.tags
        scale = tags.get(_TAG_MODEL_PIXEL_SCALE)
        tie = tags.get(_TAG_MODEL_TIEPOINT)
        if scale is not None and tie is not None:
            sx, sy = float(scale.value[0]), float(scale.value[1])
            i, j, _k, x, y = (float(v) for v in tie.value[:5])
            return GeoTransform(
                x_origin=x - i * sx,
                y_origin=y + j * sy,
                pixel_width=sx,
                pixel_height=-sy,
                width=width,
                height=height,
            )
        trans = tags.get(_TAG_MODEL_TRANSFORMATION)
        if trans is not None:
            m = trans.value  # 4x4 matrix, row-major (16 doubles)
            pixel_width, pixel_height = float(m[0]), float(m[5])
            if (
                abs(float(m[1])) > abs(pixel_width) * _ROTATION_REL_TOL
                or abs(float(m[4])) > abs(pixel_height) * _ROTATION_REL_TOL
            ):
                raise ValueError(
                    f"{page.parent.filehandle.name}: raster has a rotated/sheared "
                    "ModelTransformation; only north-up, axis-aligned rasters are supported."
                )
            return GeoTransform(
                x_origin=float(m[3]),
                y_origin=float(m[7]),
                pixel_width=pixel_width,
                pixel_height=pixel_height,
                width=width,
                height=height,
            )
        raise ValueError(f"{page.parent.filehandle.name}: missing GeoTIFF georeferencing tags")

    @staticmethod
    def _validate_page(page) -> None:
        """Reject rasters that violate this reader's assumptions.

        Sampling is single-band and indexed by lon/lat in degrees, so a
        multi-band or projected raster would silently return wrong values. We
        fail loudly instead. (Rotation is checked in ``_transform_from_tags``;
        a CRS that is absent from the file cannot be verified and is allowed.)
        """
        name = page.parent.filehandle.name
        spp = int(getattr(page, "samplesperpixel", 1) or 1)
        if spp != 1:
            raise ValueError(
                f"{name}: expected a single-band raster, got samplesperpixel={spp}. "
                "Only single-band (e.g. elevation) GeoTIFFs are supported."
            )
        model_type = UsgsTile._model_type_from_tags(page)
        if model_type is not None and model_type != _MODEL_TYPE_GEOGRAPHIC:
            raise ValueError(
                f"{name}: expected a geographic lon/lat CRS (GTModelTypeGeoKey="
                f"{_MODEL_TYPE_GEOGRAPHIC}), got {model_type}. Points are sampled by "
                "longitude/latitude in degrees; projected rasters are not supported."
            )

    @staticmethod
    def _model_type_from_tags(page) -> int | None:
        """Return GTModelTypeGeoKey from the GeoKeyDirectory, or ``None`` if the
        directory or key is absent (the CRS then cannot be verified).

        The directory is a flat array of SHORTs: a 4-value header
        (version, key_revision, minor_revision, num_keys) followed by ``num_keys``
        4-value entries (key_id, tag_location, count, value_or_offset). A
        ``tag_location`` of 0 means ``value_or_offset`` holds the value inline,
        which is always the case for GTModelTypeGeoKey.
        """
        tag = page.tags.get(_TAG_GEO_KEY_DIRECTORY)
        if tag is None or tag.value is None:
            return None
        keys = tag.value
        if len(keys) < 4:
            return None
        num_keys = int(keys[3])
        for i in range(num_keys):
            base = 4 + i * 4
            if base + 3 >= len(keys):
                break
            key_id, location, _count, value = (int(keys[base + j]) for j in range(4))
            if key_id == _GTMODELTYPE_KEY:
                return value if location == 0 else None
        return None

    @staticmethod
    def _nodata_from_tags(page) -> float:
        tag = page.tags.get(_TAG_GDAL_NODATA)
        if tag is None:
            return _DEFAULT_NODATA
        raw = tag.value
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", "ignore")
        try:
            return float(str(raw).strip().rstrip("\x00").strip())
        except (TypeError, ValueError):
            return _DEFAULT_NODATA

    def read_window(
        self, col0: int, row0: int, ncols: int, nrows: int
    ) -> Tuple[np.ndarray, int, int]:
        """Read a pixel window as float64, decoding only the tiles it overlaps.

        Returns ``(window, c0, r0)`` where ``window[y, x]`` is the elevation at
        pixel ``(r0 + y, c0 + x)``. The requested window is clamped to the
        raster bounds; an empty array is returned if it lies fully outside.
        """
        assert self.transform is not None and self._page is not None
        page = self._page
        w, h = self.transform.width, self.transform.height

        c0 = max(0, int(col0))
        r0 = max(0, int(row0))
        c1 = min(w, int(col0) + int(ncols))
        r1 = min(h, int(row0) + int(nrows))
        if c1 <= c0 or r1 <= r0:
            return np.empty((0, 0), dtype=np.float64), c0, r0

        if not page.is_tiled:
            # USGS tiles are internally tiled; this is a defensive fallback.
            full = np.asarray(page.asarray(), dtype=np.float64)
            return full[r0:r1, c0:c1], c0, r0

        tw, th = int(page.tilewidth), int(page.tilelength)
        tiles_across = (w + tw - 1) // tw
        out = np.empty((r1 - r0, c1 - c0), dtype=np.float64)
        fh = self._tif.filehandle  # type: ignore[union-attr]

        for trow in range(r0 // th, (r1 - 1) // th + 1):
            ty0 = trow * th
            for tcol in range(c0 // tw, (c1 - 1) // tw + 1):
                tx0 = tcol * tw
                idx = trow * tiles_across + tcol
                fh.seek(page.dataoffsets[idx])
                raw = fh.read(page.databytecounts[idx])
                seg, _, _ = page.decode(raw, idx, _fullsize=True)
                tile = np.asarray(seg).reshape(th, tw)
                # intersection of this tile with the requested window
                sr0, sr1 = max(r0, ty0), min(r1, ty0 + th)
                sc0, sc1 = max(c0, tx0), min(c1, tx0 + tw)
                out[sr0 - r0 : sr1 - r0, sc0 - c0 : sc1 - c0] = tile[
                    sr0 - ty0 : sr1 - ty0, sc0 - tx0 : sc1 - tx0
                ]
        return out, c0, r0

    def sample(
        self, lons: np.ndarray, lats: np.ndarray, *, sampling: str = "bilinear"
    ) -> np.ndarray:
        """Sample elevation (in **meters**) for a batch of points in this tile.

        Out-of-bounds points and no-data cells yield ``np.nan``. For bilinear
        sampling, a point whose 2x2 neighborhood would cross the tile boundary
        falls back to nearest-neighbor (a ~1-pixel seam at tile edges); no-data
        among the four neighbors is handled by renormalizing over the valid
        ones.
        """
        validate_sampling(sampling)
        assert self.transform is not None
        lons = np.asarray(lons, dtype=np.float64)
        lats = np.asarray(lats, dtype=np.float64)
        n = lons.shape[0]
        result = np.full(n, np.nan, dtype=np.float64)
        if n == 0:
            return result

        w, h = self.transform.width, self.transform.height
        col, row = self.transform.lonlat_to_pixel(lons, lats)
        ic = np.floor(col).astype(np.int64)
        ir = np.floor(row).astype(np.int64)
        nearest_ok = (ic >= 0) & (ic < w) & (ir >= 0) & (ir < h)
        if not nearest_ok.any():
            return result

        pad = 0 if sampling == "nearest" else 1
        cols_ok, rows_ok = col[nearest_ok], row[nearest_ok]
        c_lo = max(0, int(np.floor(cols_ok.min())) - pad)
        r_lo = max(0, int(np.floor(rows_ok.min())) - pad)
        c_hi = min(w, int(np.floor(cols_ok.max())) + 1 + pad)
        r_hi = min(h, int(np.floor(rows_ok.max())) + 1 + pad)
        window, wc0, wr0 = self.read_window(c_lo, r_lo, c_hi - c_lo, r_hi - r_lo)

        # Mask no-data so it never contaminates a sample.
        invalid = (window == self.nodata) | (window <= _NODATA_FLOOR) | ~np.isfinite(window)
        if invalid.any():
            window = np.where(invalid, np.nan, window)

        if sampling == "nearest":
            result[nearest_ok] = window[ir[nearest_ok] - wr0, ic[nearest_ok] - wc0]
            return result

        # Bilinear where the full 2x2 footprint is inside the tile; otherwise
        # fall back to nearest at the 1-pixel edge seam.
        bilinear_ok = (ic >= 0) & (ic + 1 < w) & (ir >= 0) & (ir + 1 < h)
        edge = nearest_ok & ~bilinear_ok
        if edge.any():
            result[edge] = window[ir[edge] - wr0, ic[edge] - wc0]

        if bilinear_ok.any():
            fc, fr = ic[bilinear_ok], ir[bilinear_ok]
            dx, dy = col[bilinear_ok] - fc, row[bilinear_ok] - fr
            c, r = fc - wc0, fr - wr0
            vals = np.stack(
                [window[r, c], window[r, c + 1], window[r + 1, c], window[r + 1, c + 1]]
            )
            wts = np.stack([(1 - dx) * (1 - dy), dx * (1 - dy), (1 - dx) * dy, dx * dy])
            valid = np.isfinite(vals)
            wts = np.where(valid, wts, 0.0)
            vals = np.where(valid, vals, 0.0)
            wsum = wts.sum(axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                result[bilinear_ok] = np.where(wsum > 0, (wts * vals).sum(axis=0) / wsum, np.nan)
        return result
