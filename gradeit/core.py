from pathlib import Path
from typing import Optional, Union

import numpy as np

from gradeit.elevation.elevation_model import ElevationModel
from gradeit.exceptions import InvalidInputError
from gradeit.filters import BridgeGradeFilter, ElevationFilter, GradeFilter, SavitzkyGolayFilter
from gradeit.grade import get_distances, get_grade
from gradeit.io import CoordinateInput, GradeResult, to_coordinates
from gradeit.sources import Source, resolve_model


def gradeit(
    data: CoordinateInput,
    *,
    source: Union[Source, str] = Source.USGS_API,
    usgs_db_path: Optional[Union[str, Path]] = None,
    sampling: str = "bilinear",
    elevation_model: Optional[ElevationModel] = None,
    elevation_filter: Union[ElevationFilter, bool, None] = None,
    grade_filter: Union[GradeFilter, bool, None] = None,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
) -> GradeResult:
    """Append elevation and road grade to a sequence of GPS points.

    Parameters
    ----------
    data:
        The coordinates to grade. Accepts a pandas DataFrame, a mapping keyed by
        ``lat_col`` / ``lon_col``, a numpy array of shape ``(n, 2)``, or an
        iterable of :class:`~gradeit.coordinate.Coordinate` or
        ``(latitude, longitude)`` pairs. See :func:`gradeit.io.to_coordinates`.
    source:
        The built-in elevation source: ``Source.USGS_API`` (default, online) or
        ``Source.USGS_LOCAL`` (local raster tiles). The legacy strings
        ``"usgs-api"`` / ``"usgs-local"`` also work. Ignored when
        ``elevation_model`` is given.
    usgs_db_path:
        Path to the local USGS raster tiles; required for the ``usgs-local`` source.
    sampling:
        DEM sampling mode for the local source: ``"bilinear"`` (default) or
        ``"nearest"``. Ignored by the API source.
    elevation_model:
        A custom :class:`ElevationModel` instance. When provided it takes
        precedence over ``source`` / ``usgs_db_path`` / ``sampling``.
    elevation_filter:
        Smooths the elevation profile *before* grade is computed. Pass an
        :class:`ElevationFilter` instance, ``True`` for a default
        :class:`SavitzkyGolayFilter`, or ``None`` (default) to skip.
    grade_filter:
        Corrects the grade profile *after* it is computed (e.g. bridge
        correction). Pass a :class:`GradeFilter` instance, ``True`` for a default
        :class:`BridgeGradeFilter`, or ``None`` (default) to skip.
    lat_col, lon_col:
        Column/key names for the latitude and longitude, used only for the
        DataFrame and mapping input forms.

    Returns
    -------
    GradeResult
        A container of numpy arrays (raw elevation, distances, grade, and the
        filtered profiles when filtering ran). Use ``.to_dataframe()`` or
        ``.to_dict()`` to materialize it. The input object is never mutated.
    """
    coordinates = to_coordinates(data, lat_col=lat_col, lon_col=lon_col)
    if len(coordinates) < 2:
        raise InvalidInputError("gradeit requires at least 2 coordinates.")

    emodel = elevation_model or resolve_model(source, usgs_db_path, sampling)

    elevation_list = emodel.get_elevation(coordinates)
    elevation_ft = np.asarray(elevation_list, dtype=np.float64)

    # distances_ft carries a leading 0 so it aligns point-for-point with the
    # elevation/grade arrays; the per-segment distances are distances_ft[1:].
    segment_distances = get_distances(coordinates)
    distances_ft = np.asarray([0.0] + segment_distances, dtype=np.float64)

    grade_dec = np.asarray(get_grade(elevation_list, distances=segment_distances), dtype=np.float64)

    # (A) Elevation filtering: smooth elevation, then recompute grade from it.
    elevation_ft_filtered: Optional[np.ndarray] = None
    grade_dec_filtered: Optional[np.ndarray] = None
    if elevation_filter:
        efilter = SavitzkyGolayFilter() if elevation_filter is True else elevation_filter
        filtered_list = efilter.filter(elevation_list, coordinates)
        elevation_ft_filtered = np.asarray(filtered_list, dtype=np.float64)
        grade_dec_filtered = np.asarray(
            get_grade(filtered_list, distances=segment_distances), dtype=np.float64
        )

    # (B) Grade filtering: correct the best available grade. grade_dec stays the
    # pristine raw grade; the corrected profile lands in grade_dec_filtered.
    if grade_filter:
        gfilter = BridgeGradeFilter() if grade_filter is True else grade_filter
        base_grade = grade_dec_filtered if grade_dec_filtered is not None else grade_dec
        base_elev = elevation_ft_filtered if elevation_ft_filtered is not None else elevation_ft
        grade_dec_filtered = gfilter.filter(base_grade, distances_ft, coordinates, base_elev)

    return GradeResult(
        coordinates=coordinates,
        elevation_ft=elevation_ft,
        distances_ft=distances_ft,
        grade_dec=grade_dec,
        elevation_ft_filtered=elevation_ft_filtered,
        grade_dec_filtered=grade_dec_filtered,
    )
