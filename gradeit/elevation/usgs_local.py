from pathlib import Path
from typing import List, Union

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.elevation.elevation_model import ElevationModel
from gradeit.elevation.tiff_reader import UsgsTile, validate_sampling

_FT_PER_M = 3.28084


class USGSLocal(ElevationModel):
    """
    An elevation model to look up elevation by latitude, longitude
    coordinates. The source data is a locally downloaded raster database
    containing the USGS 1/3 arc-second Digital Elevation Model.

    Parameters
    ----------
    usgs_db_path:
        Directory holding the downloaded tiles, laid out as
        ``{grid_ref}/USGS_13_{grid_ref}.tif`` (see ``scripts/get_usgs_tiles.py``).
    sampling:
        ``"bilinear"`` (default) interpolates the four surrounding cells;
        ``"nearest"`` returns the containing cell (matching the historical
        behavior). Out-of-bounds points and no-data cells return ``NaN``.
    """

    usgs_db_path: Path

    def __init__(self, usgs_db_path: Union[Path, str], sampling: str = "bilinear"):
        self.usgs_db_path = Path(usgs_db_path)
        self.sampling = validate_sampling(sampling)

    def get_elevation(self, trace: List[Coordinate]) -> List[float]:
        return get_raster_elev_profile(trace, self.usgs_db_path, sampling=self.sampling)


def get_raster_elev_profile(
    coordinates: List[Coordinate], usgs_db_path: Union[Path, str], sampling: str = "bilinear"
) -> List[float]:
    """
    Look up an elevation profile (in feet) for a list of coordinates from a
    local USGS 1/3 arc-second raster database.

    Points are grouped by the 1-degree tile that contains them so each tile is
    opened once; results are returned in the original coordinate order, with
    ``NaN`` for points outside the available tiles or over no-data cells.
    """
    validate_sampling(sampling)
    db_path = Path(usgs_db_path)

    lats = np.array([coord.latitude for coord in coordinates], dtype=np.float64)
    lons = np.array([coord.longitude for coord in coordinates], dtype=np.float64)
    elevation_ft = np.full(len(coordinates), np.nan, dtype=np.float64)

    grid_refs = build_grid_refs(lats, lons)
    for grid_ref in set(grid_refs):
        if grid_ref == "0":
            # Outside the supported (northern/western) hemisphere coverage.
            continue
        mask = grid_refs == grid_ref
        raster_path = db_path / grid_ref / f"USGS_13_{grid_ref}.tif"
        if not raster_path.exists():
            raise FileNotFoundError(f"The raster path {raster_path} does not exist.")

        with UsgsTile(raster_path) as tile:
            meters = tile.sample(lons[mask], lats[mask], sampling=sampling)
        elevation_ft[mask] = meters * _FT_PER_M

    return elevation_ft.tolist()


def build_grid_refs(lats, lons) -> np.ndarray:
    """
    Map latitude/longitude values to USGS tile grid-reference IDs (e.g.
    ``"n40w105"``). Tiles are named for their north-west corner with the
    longitude zero-padded to three digits. Coverage is the northern/western
    hemisphere (the USGS product extent); points elsewhere map to ``"0"``.

    Parameters:
        Two iterables of float latitudes and longitudes.
    Returns:
        A numpy array of grid-reference ID strings, one per input point.
    """
    refs = []
    for lat, lon in zip(lats, lons):
        if lat > 0.0 and lon < 0.0:
            lat_id = int(abs(lat)) + 1
            lon_id = int(abs(lon)) + 1
            refs.append(f"n{lat_id}w{lon_id:03d}")
        else:
            refs.append("0")
    return np.array(refs, dtype=str)
