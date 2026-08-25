"""GradeIT — append elevation and road grade to a sequence of GPS points."""

from gradeit.coordinate import Coordinate
from gradeit.core import gradeit
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
    "BridgeFilter",
    "Coordinate",
    "ElevationFilter",
    "ElevationLookupError",
    "ElevationModel",
    "GradeResult",
    "GradeitError",
    "GradeitWarning",
    "InvalidInputError",
    "MissingDependencyError",
    "SparseGridWarning",
    "USGSApi",
    "USGSLocal",
    "Wood2014Filter",
    "gradeit",
    "plot_grade_map",
]
