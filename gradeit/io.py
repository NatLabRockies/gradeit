from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from gradeit.coordinate import Coordinate
from gradeit.exceptions import InvalidInputError, MissingDependencyError

if TYPE_CHECKING:
    import folium
    import pandas as pd

# Anything ``to_coordinates`` knows how to turn into a list of Coordinates.
CoordinateInput = Union[
    "pd.DataFrame",
    Mapping[str, Sequence[float]],
    Sequence[Tuple[float, float]],
    Sequence[Coordinate],
    np.ndarray,
]


def to_coordinates(
    data: CoordinateInput,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
) -> List[Coordinate]:
    """Coerce supported inputs into a list of :class:`Coordinate`.

    Accepts, in order of detection:

    * a numpy array of shape ``(n, 2)`` with ``(latitude, longitude)`` rows;
    * a pandas DataFrame (duck-typed) with ``lat_col`` / ``lon_col`` columns;
    * a mapping (e.g. ``dict``) keyed by ``lat_col`` / ``lon_col``;
    * an iterable of :class:`Coordinate` or ``(latitude, longitude)`` pairs.

    ``lat_col`` / ``lon_col`` apply only to the DataFrame and mapping forms.

    Raises
    ------
    InvalidInputError
        If ``data`` is not one of the supported forms (or has the wrong shape /
        missing columns).
    """
    if isinstance(data, np.ndarray):
        if data.ndim != 2 or data.shape[1] != 2:
            raise InvalidInputError(
                "numpy array input must have shape (n, 2) with (latitude, longitude) "
                f"rows; got shape {data.shape}."
            )
        return [Coordinate.from_lat_lon(lat, lon) for lat, lon in data]

    # DataFrame-like: anything column-indexable that exposes `.columns`.
    if hasattr(data, "columns"):
        return _from_columns(data, lat_col, lon_col)

    if isinstance(data, Mapping):
        return _from_columns(data, lat_col, lon_col)

    if isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
        return _from_iterable(data)

    raise InvalidInputError(
        "Unsupported coordinate input. Provide a pandas DataFrame, a mapping with "
        f"{lat_col!r}/{lon_col!r} keys, a numpy array of shape (n, 2), or an iterable "
        "of Coordinate or (latitude, longitude) pairs."
    )


def _from_columns(data, lat_col: str, lon_col: str) -> List[Coordinate]:
    try:
        lat_values = data[lat_col]
        lon_values = data[lon_col]
    except (KeyError, IndexError) as e:
        raise InvalidInputError(
            f"Input is missing the {lat_col!r} and/or {lon_col!r} column."
        ) from e
    lats = np.asarray(lat_values, dtype=float)
    lons = np.asarray(lon_values, dtype=float)
    return [Coordinate.from_lat_lon(lat, lon) for lat, lon in zip(lats, lons)]


def _from_iterable(data: Iterable) -> List[Coordinate]:
    coordinates: List[Coordinate] = []
    for item in data:
        if isinstance(item, Coordinate):
            coordinates.append(item)
            continue
        try:
            lat, lon = item
        except (TypeError, ValueError) as e:
            raise InvalidInputError(
                "Each item must be a Coordinate or a (latitude, longitude) pair."
            ) from e
        coordinates.append(Coordinate.from_lat_lon(lat, lon))
    return coordinates


@dataclass(frozen=True)
class GradeResult:
    """The output of :func:`gradeit.gradeit`.

    Holds plain numpy arrays (and the source coordinates) so the core stays
    independent of pandas. The optional ``*_filtered`` fields are populated only
    when filtering ran, making the filtered-or-not contract explicit.

    Use :meth:`to_dict` or :meth:`to_dataframe` to materialize the result in a
    tabular form.
    """

    coordinates: List[Coordinate]
    elevation_ft: np.ndarray
    distances_ft: np.ndarray
    grade_dec: np.ndarray
    elevation_ft_filtered: Optional[np.ndarray] = None
    grade_dec_filtered: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, list]:
        """Return the result as a column-name -> list mapping.

        Column names match the historical gradeit output: ``latitude``,
        ``longitude``, ``elevation_ft``, ``distances_ft``, ``grade_dec_unfiltered``,
        plus ``elevation_ft_filtered`` / ``grade_dec_filtered`` when present.
        """
        out: Dict[str, list] = {
            "latitude": [c.latitude for c in self.coordinates],
            "longitude": [c.longitude for c in self.coordinates],
            "elevation_ft": self.elevation_ft.tolist(),
            "distances_ft": self.distances_ft.tolist(),
            "grade_dec_unfiltered": self.grade_dec.tolist(),
        }
        if self.elevation_ft_filtered is not None:
            out["elevation_ft_filtered"] = self.elevation_ft_filtered.tolist()
        if self.grade_dec_filtered is not None:
            out["grade_dec_filtered"] = self.grade_dec_filtered.tolist()
        return out

    def to_dataframe(self) -> "pd.DataFrame":
        """Return the result as a new pandas DataFrame.

        Raises
        ------
        MissingDependencyError
            If pandas is not installed (``pip install gradeit[pandas]``).
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise MissingDependencyError(
                "pandas is required for GradeResult.to_dataframe(); "
                "install it with 'pip install gradeit[pandas]'."
            ) from e
        return pd.DataFrame(self.to_dict())

    def plot_map(self, **kwargs) -> "folium.Map":
        """Render this result on an interactive folium map colored by grade.

        Thin convenience wrapper around :func:`gradeit.plotting.plot_grade_map`;
        all keyword arguments are forwarded. Requires ``gradeit[plot]``.
        """
        from gradeit.plotting import plot_grade_map

        return plot_grade_map(self, **kwargs)
