"""GradeIT — append elevation and road grade to a sequence of GPS points."""

from gradeit.core import gradeit
from gradeit.coordinate import Coordinate
from gradeit.elevation import ElevationModel, USGSApi, USGSLocal
from gradeit.exceptions import (
    ElevationLookupError,
    GradeitError,
    GradeitWarning,
    InvalidInputError,
    MissingDependencyError,
    SparseGridWarning,
)
from gradeit.filters import (
    BridgeFilter,
    ElevationFilter,
    Wood2014Filter,
)
from gradeit.io import GradeResult
from gradeit.plotting import plot_grade_map

__all__ = [
    "gradeit",
    "Coordinate",
    "GradeResult",
    "ElevationModel",
    "USGSApi",
    "USGSLocal",
    "ElevationFilter",
    "Wood2014Filter",
    "BridgeFilter",
    "GradeitError",
    "InvalidInputError",
    "MissingDependencyError",
    "ElevationLookupError",
    "GradeitWarning",
    "SparseGridWarning",
    "plot_grade_map",
]
