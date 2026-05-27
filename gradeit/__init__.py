"""GradeIT — append elevation and road grade to a sequence of GPS points."""

from gradeit.core import gradeit
from gradeit.coordinate import Coordinate
from gradeit.elevation import ElevationModel, USGSApi, USGSLocal
from gradeit.exceptions import (
    ElevationLookupError,
    GradeitError,
    InvalidInputError,
    InvalidSourceError,
    MissingDependencyError,
)
from gradeit.filters import (
    BridgeGradeFilter,
    ElevationFilter,
    GradeFilter,
    SavitzkyGolayFilter,
)
from gradeit.io import GradeResult
from gradeit.sources import Source

__all__ = [
    "gradeit",
    "Coordinate",
    "GradeResult",
    "Source",
    "ElevationModel",
    "USGSApi",
    "USGSLocal",
    "ElevationFilter",
    "GradeFilter",
    "SavitzkyGolayFilter",
    "BridgeGradeFilter",
    "GradeitError",
    "InvalidInputError",
    "InvalidSourceError",
    "MissingDependencyError",
    "ElevationLookupError",
]
