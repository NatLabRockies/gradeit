from typing import List, Optional, Sequence, Union

import numpy as np

from gradeit.elevation import ElevationModel, USGSApi
from gradeit.exceptions import InvalidInputError
from gradeit.filters import ElevationFilter, Wood2014Filter
from gradeit.grade import get_distances, get_grade
from gradeit.io import CoordinateInput, GradeResult, to_coordinates

# Applied unless the caller overrides elevation_filter. Wood2014Filter is a
# frozen (immutable) dataclass, so sharing one instance as the default is safe.
_DEFAULT_FILTER = Wood2014Filter()


def gradeit(
    data: CoordinateInput,
    *,
    elevation_model: Optional[ElevationModel] = None,
    elevation_filter: Union[ElevationFilter, Sequence[ElevationFilter], None] = _DEFAULT_FILTER,
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
    elevation_model:
        The :class:`~gradeit.elevation.ElevationModel` that supplies elevation.
        Defaults to :class:`~gradeit.elevation.USGSApi` (the online USGS
        Elevation Point Query Service, no setup required). For bulk traces,
        pass :class:`~gradeit.elevation.USGSLocal` pointed at downloaded raster
        tiles, or any custom ``ElevationModel`` instance.
    elevation_filter:
        Clean up the elevation profile before grade is computed. Pass a single
        :class:`ElevationFilter` instance or a sequence of them (applied in
        order, each consuming the previous filter's output). Defaults to
        :class:`~gradeit.filters.Wood2014Filter`, the filtration routine of
        Wood et al. (2014), NREL/TP-5400-61109: resample onto a uniform
        distance grid, smooth, reject and backfill anomalous points, smooth
        again, and interpolate back. Pass ``None`` (or ``[]``) to skip
        filtering entirely.

        :class:`~gradeit.filters.BridgeFilter` (targeted bare-earth bridge
        correction) remains available for spans the Wood routine declines to
        touch; put it *first* in the sequence.
    lat_col, lon_col:
        Column/key names for the latitude and longitude, used only for the
        DataFrame and mapping input forms.

    Returns
    -------
    GradeResult
        A container of numpy arrays. Elevation and grade each come in an
        ``_unfiltered`` form (the raw lookup) and, when filtering ran, a
        ``_filtered`` form. Use ``.to_dataframe()`` or ``.to_dict()`` to
        materialize it. The input object is never mutated.
    """
    coordinates = to_coordinates(data, lat_col=lat_col, lon_col=lon_col)
    if len(coordinates) < 2:
        raise InvalidInputError("gradeit requires at least 2 coordinates.")

    emodel = elevation_model or USGSApi()

    elevation_list = emodel.get_elevation(coordinates)
    elevation_ft_unfiltered = np.asarray(elevation_list, dtype=np.float64)

    # distances_ft carries a leading 0 so it aligns point-for-point with the
    # elevation/grade arrays; the per-segment distances are distances_ft[1:].
    segment_distances = get_distances(coordinates)
    distances_ft = np.asarray([0.0] + segment_distances, dtype=np.float64)

    grade_dec_unfiltered = np.asarray(
        get_grade(elevation_list, distances=segment_distances), dtype=np.float64
    )

    elevation_ft_filtered: Optional[np.ndarray] = None
    grade_dec_filtered: Optional[np.ndarray] = None
    filters = _resolve_filters(elevation_filter)
    if filters:
        filtered_list = elevation_list
        for f in filters:
            filtered_list = f.filter(filtered_list, coordinates)
        elevation_ft_filtered = np.asarray(filtered_list, dtype=np.float64)
        grade_dec_filtered = np.asarray(
            get_grade(filtered_list, distances=segment_distances), dtype=np.float64
        )

    return GradeResult(
        coordinates=coordinates,
        elevation_ft_unfiltered=elevation_ft_unfiltered,
        distances_ft=distances_ft,
        grade_dec_unfiltered=grade_dec_unfiltered,
        elevation_ft_filtered=elevation_ft_filtered,
        grade_dec_filtered=grade_dec_filtered,
    )


def _resolve_filters(
    elevation_filter: Union[ElevationFilter, Sequence[ElevationFilter], None],
) -> List[ElevationFilter]:
    """Normalize the ``elevation_filter`` argument to a list of filters."""
    if elevation_filter is None:
        return []
    if isinstance(elevation_filter, bool):
        raise InvalidInputError(
            "elevation_filter no longer accepts a boolean; pass an ElevationFilter "
            "instance, e.g. Wood2014Filter(), or a sequence such as "
            "[BridgeFilter(), Wood2014Filter()]."
        )
    if isinstance(elevation_filter, ElevationFilter):
        return [elevation_filter]
    try:
        filters = list(elevation_filter)
    except TypeError as e:
        raise InvalidInputError(
            "elevation_filter must be an ElevationFilter or a sequence of them."
        ) from e
    for f in filters:
        if not isinstance(f, ElevationFilter):
            raise InvalidInputError(
                "Every element of an elevation_filter sequence must be an ElevationFilter."
            )
    return filters
