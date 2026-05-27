"""Built-in elevation sources and the factory that resolves them.

``Source`` is a ``str`` enum, so the legacy string API (``source="usgs-api"``)
and the enum members (``Source.USGS_API``) are interchangeable.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional, Union

from gradeit.elevation.elevation_model import ElevationModel
from gradeit.elevation.usgs_api import USGSApi
from gradeit.elevation.usgs_local import USGSLocal
from gradeit.exceptions import InvalidSourceError


class Source(str, Enum):
    """Identifiers for the built-in elevation sources."""

    USGS_API = "usgs-api"
    USGS_LOCAL = "usgs-local"


def resolve_model(
    source: Union[Source, str],
    usgs_db_path: Optional[Union[str, Path]] = None,
    sampling: str = "bilinear",
) -> ElevationModel:
    """Build the :class:`ElevationModel` for a built-in source.

    Parameters
    ----------
    source:
        A :class:`Source` member or its string value (e.g. ``"usgs-api"``).
    usgs_db_path:
        Path to the local raster tiles; required for ``Source.USGS_LOCAL``.
    sampling:
        DEM sampling mode for the local source (``"bilinear"`` or ``"nearest"``).

    Raises
    ------
    InvalidSourceError
        If ``source`` is unknown, or a required option is missing.
    """
    try:
        source = Source(source)
    except ValueError as e:
        valid = ", ".join(repr(s.value) for s in Source)
        raise InvalidSourceError(
            f"Invalid elevation source {source!r}. Valid options are: {valid}."
        ) from e

    if source is Source.USGS_API:
        return USGSApi()

    # source is Source.USGS_LOCAL
    if usgs_db_path is None:
        raise InvalidSourceError(
            "The 'usgs-local' source requires 'usgs_db_path' (the path to the local "
            "USGS raster tiles)."
        )
    return USGSLocal(Path(usgs_db_path), sampling=sampling)
