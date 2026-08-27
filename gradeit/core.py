from collections.abc import Sequence

import numpy as np

from gradeit.elevation import ElevationModel, USGSApi
from gradeit.exceptions import InvalidInputError
from gradeit.filters import ElevationFilter, Wood2014Filter
from gradeit.grade import get_distances, get_grade
from gradeit.io import CoordinateInput, GradeResult, to_coordinates

# Default filter. Its frozen dataclass can be shared safely.
_DEFAULT_FILTER = Wood2014Filter()


def gradeit(
    data: CoordinateInput,
    *,
    elevation_model: ElevationModel | None = None,
    elevation_filter: ElevationFilter | Sequence[ElevationFilter] | None = _DEFAULT_FILTER,
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
        Model that provides elevation. Defaults to the online
        :class:`~gradeit.elevation.USGSApi` service. Use
        :class:`~gradeit.elevation.USGSLocal` with downloaded tiles, or pass a
        custom ``ElevationModel``.
    elevation_filter:
        Filter elevation before calculating grade. Pass one
        :class:`ElevationFilter` or a sequence, applied in order. Defaults to
        :class:`~gradeit.filters.Wood2014Filter`. Pass ``None`` or ``[]`` to
        skip filtering. Put :class:`~gradeit.filters.BridgeFilter` first when
        using it with other filters.
    lat_col, lon_col:
        Column/key names for the latitude and longitude, used only for the
        DataFrame and mapping input forms.

    Returns
    -------
    GradeResult
        Numpy arrays for the input coordinates, elevation, distance, and
        grade. Raw values use the ``_unfiltered`` suffix. Filtered values use
        ``_filtered`` when a filter runs. The input is not changed.
    """
    coordinates = to_coordinates(data, lat_col=lat_col, lon_col=lon_col)
    if len(coordinates) < 2:
        raise InvalidInputError("gradeit requires at least 2 coordinates.")

    emodel = elevation_model or USGSApi()

    elevation_list = emodel.get_elevation(coordinates)
    elevation_ft_unfiltered = np.asarray(elevation_list, dtype=np.float64)

    # Start with 0 so distances align with the point arrays.
    segment_distances = get_distances(coordinates)
    distances_ft = np.asarray([0.0] + segment_distances, dtype=np.float64)

    grade_dec_unfiltered = np.asarray(
        get_grade(elevation_list, distances=segment_distances), dtype=np.float64
    )

    elevation_ft_filtered: np.ndarray | None = None
    grade_dec_filtered: np.ndarray | None = None
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
    elevation_filter: ElevationFilter | Sequence[ElevationFilter] | None,
) -> list[ElevationFilter]:
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
